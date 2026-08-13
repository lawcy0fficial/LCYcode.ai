import asyncio

from lcycode.tools import registry


def _execute(tool_name, args):
    return asyncio.run(registry.execute(tool_name, args))


def test_write_file_new_file_has_none_before():
    result = _execute("write_file", {"path": "diff_new.txt", "content": "line1\nline2"})
    assert result["diff"]["before"] is None
    assert result["diff"]["after"] == "line1\nline2"


def test_write_file_overwrite_captures_before_and_after():
    _execute("write_file", {"path": "diff_overwrite.txt", "content": "old content"})
    result = _execute("write_file", {"path": "diff_overwrite.txt", "content": "new content"})
    assert result["diff"]["before"] == "old content"
    assert result["diff"]["after"] == "new content"


def test_edit_file_captures_before_and_after():
    _execute("write_file", {"path": "diff_edit.txt", "content": "foo bar"})
    result = _execute("edit_file", {"path": "diff_edit.txt", "find": "foo", "replace": "baz"})
    assert result["diff"]["before"] == "foo bar"
    assert result["diff"]["after"] == "baz bar"


def test_append_file_captures_before_and_after():
    _execute("write_file", {"path": "diff_append.txt", "content": "line1\n"})
    result = _execute("append_file", {"path": "diff_append.txt", "content": "line2\n"})
    assert result["diff"]["before"] == "line1\n"
    assert result["diff"]["after"] == "line1\nline2\n"


def test_delete_file_captures_before_and_none_after():
    _execute("write_file", {"path": "diff_delete.txt", "content": "gone soon"})
    result = _execute("delete_file", {"path": "diff_delete.txt"})
    assert result["diff"]["before"] == "gone soon"
    assert result["diff"]["after"] is None


def test_non_mutating_tool_has_no_diff_key():
    _execute("write_file", {"path": "diff_readonly.txt", "content": "x"})
    result = _execute("read_file", {"path": "diff_readonly.txt"})
    assert "diff" not in result
