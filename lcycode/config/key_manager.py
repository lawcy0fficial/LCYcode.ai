"""
key_manager.py
Loads key.json and rotates API keys per-provider. When a key fails
(rate limit, auth error, timeout) it is put on cooldown and the next
key in the ring is used, so one dead key never stalls the agent.

Placeholder keys (the "REPLACE_WITH_..." strings key.demo.json ships
with) are filtered out at load time, never rotated in. This matters
for the free-by-default guarantee: if offline_only ever gets flipped
to false without real cloud keys actually being added, the ring for
that provider is simply empty — get_key() returns None, the provider
raises "no keys configured", and the router cleanly falls through to
the next one (Ollama, first in the default order) instead of firing
an API call with an obviously-fake key.
"""
import json
import time
import threading

from lcycode.config.settings import KEY_FILE, DEMO_KEY_FILE, DEFAULT_ROUTING
from lcycode.config.schema import validate_config
from lcycode.core.logging_utils import get_logger

log = get_logger(__name__)

COOLDOWN_SECONDS = 60
PLACEHOLDER_MARKER = "REPLACE_WITH"


def is_placeholder_key(key: str) -> bool:
    return PLACEHOLDER_MARKER in key.upper()


class KeyRing:
    def __init__(self, keys):
        real_keys = [k for k in (keys or []) if not is_placeholder_key(k)]
        self.keys = real_keys
        self.placeholder_count = len(keys or []) - len(real_keys)
        self.index = 0
        self.cooldown_until = {k: 0 for k in self.keys}
        self.lock = threading.Lock()

    def get(self):
        with self.lock:
            if not self.keys:
                return None
            n = len(self.keys)
            now = time.time()
            for _ in range(n):
                key = self.keys[self.index]
                self.index = (self.index + 1) % n
                if self.cooldown_until.get(key, 0) <= now:
                    return key
            return min(self.cooldown_until, key=self.cooldown_until.get)

    def mark_failed(self, key, seconds=COOLDOWN_SECONDS):
        with self.lock:
            self.cooldown_until[key] = time.time() + seconds

    def status(self):
        now = time.time()
        return [
            {
                "key": f"{k[:8]}...{k[-4:]}" if len(k) > 12 else "***",
                "cooling_down": self.cooldown_until.get(k, 0) > now,
            }
            for k in self.keys
        ] + ([{"placeholder": True}] * self.placeholder_count if self.placeholder_count else [])


class KeyManager:
    def __init__(self, path=KEY_FILE):
        self.path = path
        if not self.path.exists():
            if DEMO_KEY_FILE.exists():
                self.path.write_text(DEMO_KEY_FILE.read_text())
            else:
                raise FileNotFoundError(
                    "key.json not found and no key.demo.json to fall back to."
                )
        self.reload()

    def reload(self):
        raw = json.loads(self.path.read_text())
        validate_config(raw)  # raises with a clear message on a malformed key.json
        self.config = raw
        self.rings = {
            provider: KeyRing(self.config.get(provider, {}).get("keys", []))
            for provider in ("openrouter", "grok", "deepseek")
        }
        self._warn_if_cloud_fallback_configured_without_real_keys()

    def _warn_if_cloud_fallback_configured_without_real_keys(self):
        if self.offline_only():
            return  # ollama-only by design — cloud rings being empty is expected, not a problem
        order = self.config.get("routing", DEFAULT_ROUTING).get("order", [])
        cloud_providers_in_order = [p for p in order if p != "ollama" and p in self.rings]
        all_empty = cloud_providers_in_order and all(
            not self.rings[p].keys for p in cloud_providers_in_order
        )
        if all_empty:
            log.warning(
                "offline_only is false but every cloud provider in routing.order "
                "(%s) still has only placeholder keys — calls will silently fall "
                "through to ollama anyway. Add real keys to key.json if you actually "
                "want cloud fallback, or set offline_only back to true.",
                cloud_providers_in_order,
            )

    def get_key(self, provider):
        ring = self.rings.get(provider)
        return ring.get() if ring else None

    def mark_failed(self, provider, key):
        ring = self.rings.get(provider)
        if ring and key:
            ring.mark_failed(key)

    def provider_config(self, provider):
        return self.config.get(provider, {})

    def offline_only(self) -> bool:
        return bool(self.config.get("ollama", {}).get("offline_only", False))

    def routing(self):
        routing = self.config.get("routing", DEFAULT_ROUTING)
        if self.offline_only():
            # Hard override: no cloud provider is ever consulted, regardless
            # of what routing.order says — this is what "fully offline"
            # actually has to mean.
            routing = dict(routing)
            routing["order"] = ["ollama"]
        return routing

    def status(self):
        out = {p: ring.status() for p, ring in self.rings.items()}
        ollama_cfg = self.config.get("ollama", {})
        out["ollama"] = {
            "enabled": ollama_cfg.get("enabled", False),
            "host": ollama_cfg.get("host"),
            "model": ollama_cfg.get("model"),
        }
        return out
