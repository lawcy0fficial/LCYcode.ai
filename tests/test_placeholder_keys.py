import json
import logging

from lcycode.config.key_manager import KeyRing, is_placeholder_key, KeyManager


def test_is_placeholder_key_detects_marker():
    assert is_placeholder_key("sk-or-v1-REPLACE_WITH_KEY_1") is True
    assert is_placeholder_key("sk-ant-REPLACE_WITH_YOUR_ANTHROPIC_KEY") is True


def test_is_placeholder_key_false_for_real_looking_key():
    assert is_placeholder_key("sk-or-v1-abc123realkeylookingstring") is False


def test_keyring_filters_out_placeholders():
    ring = KeyRing(["sk-REPLACE_WITH_KEY_1", "sk-real-actual-key"])
    assert ring.keys == ["sk-real-actual-key"]
    assert ring.placeholder_count == 1


def test_keyring_all_placeholders_leaves_empty_ring():
    ring = KeyRing(["sk-REPLACE_WITH_KEY_1", "sk-REPLACE_WITH_KEY_2"])
    assert ring.keys == []
    assert ring.get() is None
    assert ring.placeholder_count == 2


def test_keyring_status_reports_placeholder_entries():
    ring = KeyRing(["sk-REPLACE_WITH_KEY_1", "sk-real-key"])
    status = ring.status()
    assert any(s.get("placeholder") for s in status)
    assert any(not s.get("placeholder", False) for s in status)


def test_key_manager_never_rotates_in_a_placeholder_key(tmp_path):
    path = tmp_path / "key.json"
    path.write_text(json.dumps({
        "openrouter": {"keys": ["sk-or-v1-REPLACE_WITH_KEY_1", "sk-or-v1-REPLACE_WITH_KEY_2"], "models": ["m"]},
        "ollama": {"enabled": True, "offline_only": False},
        "routing": {"order": ["openrouter", "ollama"]},
    }))
    km = KeyManager(path=path)
    assert km.get_key("openrouter") is None  # both keys were placeholders, filtered entirely


def test_offline_only_true_suppresses_placeholder_warning(tmp_path, caplog):
    path = tmp_path / "key.json"
    path.write_text(json.dumps({
        "openrouter": {"keys": ["sk-or-v1-REPLACE_WITH_KEY_1"], "models": ["m"]},
        "ollama": {"enabled": True, "offline_only": True},
        "routing": {"order": ["ollama", "openrouter"]},
    }))
    with caplog.at_level(logging.WARNING):
        KeyManager(path=path)
    assert not any("placeholder keys" in r.message for r in caplog.records)


def test_offline_only_false_with_only_placeholders_warns(tmp_path, caplog):
    path = tmp_path / "key.json"
    path.write_text(json.dumps({
        "openrouter": {"keys": ["sk-or-v1-REPLACE_WITH_KEY_1"], "models": ["m"]},
        "ollama": {"enabled": True, "offline_only": False},
        "routing": {"order": ["ollama", "openrouter"]},
    }))
    with caplog.at_level(logging.WARNING):
        KeyManager(path=path)
    assert any("placeholder keys" in r.message for r in caplog.records)
