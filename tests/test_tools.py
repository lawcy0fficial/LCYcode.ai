import pytest

from lcycode.tools.filesystem import write_file, read_file, edit_file, list_dir
from lcycode.tools.base import resolve, ToolError


def test_write_and_read_roundtrip():
    write_file("example.txt", "hello world")
    result = read_file("example.txt")
    assert result["content"] == "hello world"


def test_edit_file_replaces_first_match():
    write_file("edit_me.txt", "foo foo")
    edit_file("edit_me.txt", "foo", "bar")
    assert read_file("edit_me.txt")["content"] == "bar foo"


def test_list_dir_reflects_written_files():
    write_file("listed.txt", "x")
    entries = list_dir(".")["entries"]
    assert "listed.txt" in entries


def test_path_escape_is_blocked():
    with pytest.raises(ToolError):
        resolve("../../etc/passwd")
