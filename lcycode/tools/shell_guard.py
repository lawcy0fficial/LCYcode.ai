"""
shell_guard.py
Defense-in-depth for run_shell, not a sandbox. Be clear-eyed about
what this actually is: a regex-based blocklist can always be evaded
by a sufficiently motivated adversarial input (base64-encoded
payloads, unusual binary names, creative quoting). That is NOT the
threat model this exists for. The realistic risk here is a model
that loses context over a long auto-continue chain and emits an
obviously destructive command it didn't "mean" to — `rm -rf ~`,
`sudo` something, a fork bomb — not a malicious actor crafting
evasions. This raises that bar; it does not eliminate the fact that
run_shell gives a model a real shell with real OS permissions. If you
need a real sandbox (untrusted input, adversarial context), put this
whole project inside a container/VM with its own filesystem — that's
what actually contains a shell, not a Python regex.

Two layers:
  - check_command(): pattern-match against a blocklist BEFORE
    executing anything. Returns a reason string if blocked, else None.
  - resource limits: best-effort memory/CPU ceiling on the subprocess
    via the stdlib `resource` module (POSIX only — silently skipped
    elsewhere), so a command that isn't blocked outright still can't
    exhaust the host.
"""
import re
import sys

# Each pattern is checked case-insensitively against the raw command
# string. Grouped by what they're actually defending against, since
# "one big list" makes it hard to reason about coverage or add to.
_DANGEROUS_PATTERNS = [
    # Escaping the workspace tree entirely — the single biggest lever:
    # once outside workspace/, a later RELATIVE command (rm -rf *,
    # chmod -R 777 .) becomes dangerous in a way no static pattern
    # can fully enumerate. Blocking the escape itself is more robust
    # than trying to catch every destructive thing that could follow it.
    (r"\bcd\s+(/|~|\$HOME)", "cd to an absolute path outside the workspace"),
    (r"\bcd\s+\.\./\.\./\.\.", "cd chain that likely escapes the workspace"),

    # Destructive deletes targeting root-ish paths even without a prior cd
    (r"\brm\s+(-\w*[rf]\w*\s+)+(-\w*[rf]\w*\s+)*(/|~|\$HOME)(\s|$)", "rm targeting a root/home path"),
    (r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*\s+/\*", "rm -rf on a root-level glob"),

    # Privilege escalation — nothing this agent does should ever need it
    (r"\bsudo\b", "privilege escalation (sudo)"),
    (r"\bsu\s+-", "privilege escalation (su)"),

    # Fork bomb
    (r":\(\)\s*\{[^}]*:\|:[^}]*\}\s*;?\s*:", "fork bomb"),

    # Raw disk / device access
    (r"\bdd\s+[^\n]*of=/dev/", "raw write to a block device"),
    (r"\bmkfs\.", "filesystem format command"),
    (r">\s*/dev/sd[a-z]\b", "raw write to a disk device"),

    # System file tampering
    (r">\s*/etc/(passwd|shadow|sudoers)\b", "overwriting a system auth file"),

    # Recursive permission changes on root-ish paths
    (r"\bchmod\s+-R\s+\S+\s+(/|~|\$HOME)(\s|$)", "recursive chmod on a root/home path"),
    (r"\bchown\s+-R\s+\S+\s+(/|~|\$HOME)(\s|$)", "recursive chown on a root/home path"),

    # Power state
    (r"\b(shutdown|reboot|halt|poweroff)\b", "system power state change"),

    # Piping a remote download straight into an interpreter — a common
    # real-world compromise vector. Flagged distinctly (not merged into
    # another category above) so it's easy to find and deliberately
    # loosen in this file if a project genuinely wants curl|bash-style
    # installers to work — that's a real tradeoff to make on purpose,
    # not something to silently allow by default.
    (r"\b(curl|wget)\b[^\n|]*\|\s*(sudo\s+)?(bash|sh|zsh|python[23]?)\b", "piping a remote download into an interpreter"),
]

_COMPILED = [(re.compile(pattern, re.IGNORECASE), reason) for pattern, reason in _DANGEROUS_PATTERNS]


def check_command(command: str) -> str | None:
    """Returns a human-readable reason if `command` matches a blocked
    pattern, otherwise None. Callers should refuse to execute the
    command at all when this returns non-None."""
    for pattern, reason in _COMPILED:
        if pattern.search(command):
            return reason
    return None


def apply_resource_limits(max_memory_mb: int = 1024, max_cpu_seconds: int = 120):
    """Returns a preexec_fn for subprocess.run that caps the child
    process's address space and CPU time — best-effort, POSIX only.
    On platforms without the `resource` module (Windows), returns None
    and callers should skip preexec_fn entirely rather than fail."""
    if sys.platform == "win32":
        return None

    def _limit():
        import resource
        try:
            max_bytes = max_memory_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (max_bytes, max_bytes))
        except (ValueError, OSError):
            pass  # some platforms/containers don't allow lowering this — degrade quietly
        try:
            resource.setrlimit(resource.RLIMIT_CPU, (max_cpu_seconds, max_cpu_seconds))
        except (ValueError, OSError):
            pass

    return _limit
