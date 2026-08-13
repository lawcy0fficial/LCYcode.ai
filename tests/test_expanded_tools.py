import pytest

from lcycode.tools.filesystem import write_file, append_file, delete_file, read_file
from lcycode.tools.search import search_files
from lcycode.tools.base import ToolError
from lcycode.config.schema import validate_config


def test_append_file_adds_to_existing_content():
    write_file("log.txt", "line1\n")
    append_file("log.txt", "line2\n")
    assert read_file("log.txt")["content"] == "line1\nline2\n"


def test_delete_file_removes_it():
    write_file("temp.txt", "x")
    delete_file("temp.txt")
    with pytest.raises(ToolError):
        read_file("temp.txt")


def test_search_files_finds_substring():
    write_file("needle.py", "def find_me():\n    pass\n")
    result = search_files("find_me")
    assert any("needle.py" in m["path"] for m in result["matches"])


def test_validate_config_accepts_demo_shape():
    demo = {
        "openrouter": {"keys": ["a"], "models": ["m"]},
        "grok": {"keys": ["b"], "model": "grok-2-latest"},
        "deepseek": {"keys": ["c"], "model": "deepseek-chat"},
        "ollama": {"host": "http://localhost:11434", "model": "x", "enabled": True},
        "routing": {"order": ["ollama"], "max_iterations": 10, "tool_timeout_seconds": 30},
    }
    cfg = validate_config(demo)
    assert cfg.routing.max_iterations == 10


def test_validate_config_rejects_bad_types():
    with pytest.raises(ValueError):
        validate_config({"routing": {"max_iterations": "not-a-number"}})
