import json

from lcycode.core.session import Session, SESSIONS_DIR
from lcycode.core.compaction import KEEP_RECENT_LOG_ENTRIES, MAX_TEXT_LENGTH


def _cleanup(session_id):
    path = SESSIONS_DIR / f"{session_id}.json"
    if path.exists():
        path.unlink()


def _big_log_entry(i):
    return {
        "step_id": i, "tool": "write_file",
        "args": {"path": f"f{i}.txt", "content": "x" * 5000},
        "result": {"ok": True, "diff": {"before": None, "after": "x" * 5000}},
    }


def test_set_pending_compacts_a_long_log_before_persisting():
    _cleanup("compaction-integration-1")
    session = Session("compaction-integration-1")
    long_log = [_big_log_entry(i) for i in range(KEEP_RECENT_LOG_ENTRIES + 15)]

    session.set_pending("build something big", {"summary": "s"}, [{"id": 1}], long_log)

    on_disk = json.loads(session.path.read_text())
    stored_log = on_disk["pending"]["log"]
    assert len(stored_log) == len(long_log)  # length preserved, content is not
    old_entries = stored_log[: -KEEP_RECENT_LOG_ENTRIES]
    assert all(e.get("_compacted") for e in old_entries)
    assert "x" * 5000 not in json.dumps(stored_log[: -KEEP_RECENT_LOG_ENTRIES])
    assert on_disk["pending"]["iterations"] == len(long_log)  # true count, not compacted length
    _cleanup("compaction-integration-1")


def test_set_pending_with_short_log_is_unaffected():
    _cleanup("compaction-integration-2")
    session = Session("compaction-integration-2")
    short_log = [_big_log_entry(i) for i in range(3)]

    session.set_pending("small task", {"summary": "s"}, [{"id": 1}], short_log)

    on_disk = json.loads(session.path.read_text())
    assert on_disk["pending"]["log"] == short_log  # untouched, well under the threshold
    _cleanup("compaction-integration-2")


def test_add_turn_truncates_long_summary_and_task_text():
    _cleanup("compaction-integration-3")
    session = Session("compaction-integration-3")
    huge_task = "describe this: " + ("a" * 2000)
    huge_summary = "b" * 2000

    session.add_turn(huge_task, {"description": {"summary": huge_summary}, "iterations": 1})

    turn = session.data["turns"][-1]
    assert len(turn["user_task"]) <= MAX_TEXT_LENGTH + 1
    assert len(turn["summary"]) <= MAX_TEXT_LENGTH + 1
    assert turn["user_task"].endswith("…")
    assert turn["summary"].endswith("…")
    _cleanup("compaction-integration-3")


def test_history_context_stays_bounded_even_with_max_turns_of_long_text():
    _cleanup("compaction-integration-4")
    session = Session("compaction-integration-4")
    for i in range(20):  # more than MAX_HISTORY_TURNS, each with long text
        session.add_turn(f"task {i}: " + ("x" * 1000),
                          {"description": {"summary": "y" * 1000}, "iterations": 1})

    context = session.history_context()
    # 12 turns (the cap) * (~240 chars truncated summary + ~240 truncated
    # task + formatting) stays comfortably bounded regardless of how long
    # the raw text originally was
    assert len(context) < 12 * 600
    _cleanup("compaction-integration-4")
