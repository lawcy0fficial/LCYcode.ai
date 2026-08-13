import json

import pytest

from lcycode.config.key_manager import KeyManager


def _write_key_json(tmp_path, ollama_overrides=None):
    cfg = {
        "openrouter": {"keys": ["or-key"], "models": ["m"]},
        "grok": {"keys": ["grok-key"]},
        "deepseek": {"keys": ["ds-key"]},
        "ollama": {"host": "http://127.0.0.1:11434", "model": "deepseek-coder:1.3b",
                   "enabled": True, **(ollama_overrides or {})},
        "routing": {"order": ["ollama", "openrouter", "deepseek", "grok"], "max_iterations": 5},
    }
    path = tmp_path / "key.json"
    path.write_text(json.dumps(cfg))
    return path


def test_offline_only_forces_ollama_only_routing(tmp_path):
    path = _write_key_json(tmp_path, {"offline_only": True})
    km = KeyManager(path=path)
    assert km.routing()["order"] == ["ollama"]


def test_not_offline_only_keeps_configured_order(tmp_path):
    path = _write_key_json(tmp_path, {"offline_only": False})
    km = KeyManager(path=path)
    assert km.routing()["order"] == ["ollama", "openrouter", "deepseek", "grok"]


def test_offline_only_flag_reads_correctly(tmp_path):
    path = _write_key_json(tmp_path, {"offline_only": True})
    km = KeyManager(path=path)
    assert km.offline_only() is True


def test_demo_key_json_ships_offline_only_by_default():
    """The shipped key.demo.json is the out-of-the-box config, and the
    whole point of this project is unlimited free building via a local
    model — so offline_only must default to True, not opt-in."""
    import json
    from lcycode.config.settings import DEMO_KEY_FILE

    demo = json.loads(DEMO_KEY_FILE.read_text())
    assert demo["ollama"]["offline_only"] is True
