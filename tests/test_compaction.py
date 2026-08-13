from lcycode.core.compaction import compact_log, truncate, KEEP_RECENT_LOG_ENTRIES, MAX_TEXT_LENGTH


def _fake_entry(i, big_content=True):
    return {
        "step_id": i,
        "tool": "write_file",
        "args": {"path": f"file{i}.txt", "content": ("x" * 5000) if big_content else "small"},
        "result": {"ok": True, "path": f"file{i}.txt",
                   "diff": {"before": None, "after": ("x" * 5000) if big_content else "small"}},
    }


def test_short_log_is_returned_unchanged():
    log = [_fake_entry(i) for i in range(5)]
    assert compact_log(log) == log


def test_long_log_keeps_recent_entries_full():
    log = [_fake_entry(i) for i in range(KEEP_RECENT_LOG_ENTRIES + 10)]
    result = compact_log(log)
    assert len(result) == len(log)
    recent = result[-KEEP_RECENT_LOG_ENTRIES:]
    assert all("args" in e and e["args"].get("content") for e in recent)
    assert all(not e.get("_compacted") for e in recent)


def test_long_log_summarizes_old_entries_dropping_content():
    log = [_fake_entry(i) for i in range(KEEP_RECENT_LOG_ENTRIES + 10)]
    result = compact_log(log)
    old = result[: -KEEP_RECENT_LOG_ENTRIES]
    assert all(e.get("_compacted") is True for e in old)
    assert all("args" not in e for e in old)  # the bulky content is actually gone
    assert all("content" not in str(e) for e in old)
    # but the essential shape survives
    assert all(e["tool"] == "write_file" for e in old)
    assert all(e["path"] == f"file{i}.txt" for i, e in enumerate(old))
    assert all(e["ok"] is True for e in old)


def test_compact_log_is_idempotent():
    log = [_fake_entry(i) for i in range(KEEP_RECENT_LOG_ENTRIES + 10)]
    once = compact_log(log)
    twice = compact_log(once)
    assert once == twice


def test_compact_log_significantly_shrinks_serialized_size():
    import json
    log = [_fake_entry(i) for i in range(100)]
    before_size = len(json.dumps(log))
    after_size = len(json.dumps(compact_log(log)))
    assert after_size < before_size * 0.3  # the whole point: real, large reduction


def test_truncate_leaves_short_text_alone():
    assert truncate("short") == "short"


def test_truncate_shortens_long_text_with_ellipsis():
    long_text = "a" * 1000
    result = truncate(long_text)
    assert len(result) == MAX_TEXT_LENGTH + 1  # +1 for the ellipsis character
    assert result.endswith("…")


def test_truncate_handles_empty_and_none():
    assert truncate("") == ""
    assert truncate(None) is None
