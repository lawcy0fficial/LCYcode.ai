from lcycode.config.key_manager import KeyRing


def test_keyring_round_robins():
    ring = KeyRing(["a", "b", "c"])
    seen = [ring.get() for _ in range(6)]
    assert seen == ["a", "b", "c", "a", "b", "c"]


def test_keyring_skips_cooling_down_key():
    ring = KeyRing(["a", "b"])
    ring.get()          # returns "a", advances index to "b"
    ring.mark_failed("b", seconds=999)
    # next call should skip "b" (cooling down) and return "a" again
    assert ring.get() == "a"


def test_keyring_empty_returns_none():
    ring = KeyRing([])
    assert ring.get() is None
