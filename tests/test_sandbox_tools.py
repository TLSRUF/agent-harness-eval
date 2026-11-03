import os

import pytest

from src.agent.sandbox import SandboxError, check_builtin_tool_input, resolve_in_sandbox
from src.agent.tools import check_result_impl, file_stats_impl, search_text_impl


@pytest.fixture
def box(tmp_path):
    root = tmp_path / "box"
    root.mkdir()
    (root / "a.txt").write_text("hello world\nsecond line\n", encoding="utf-8", newline="\n")
    (root / "sub").mkdir()
    (root / "sub" / "b.txt").write_text("hello again\n", encoding="utf-8", newline="\n")
    (tmp_path / "secret.txt").write_text("TOPSECRET\n", encoding="utf-8")
    return root


def text(r):
    return r["content"][0]["text"]


def test_search_finds_matches(box):
    out = text(search_text_impl(box, "hello"))
    assert "a.txt:1:hello world" in out and "sub/b.txt:1:hello again" in out


def test_search_no_match(box):
    assert text(search_text_impl(box, "zzz")) == "no matches"


def test_file_stats(box):
    assert text(file_stats_impl(box, "a.txt")) == "lines=2 words=4 bytes=24"


def test_check_result(box):
    assert text(check_result_impl(box, "a.txt", "hello", 2)) == "PASS"
    assert text(check_result_impl(box, "a.txt", "nope")).startswith("FAIL")
    assert text(check_result_impl(box, "missing.txt")).startswith("FAIL")


@pytest.mark.parametrize("p", ["../secret.txt", "sub/../../secret.txt", "..", "../box/../secret.txt"])
def test_relative_escape_blocked(box, p):
    with pytest.raises(SandboxError):
        resolve_in_sandbox(box, p)
    for fn in (lambda: file_stats_impl(box, p), lambda: check_result_impl(box, p), lambda: search_text_impl(box, "TOP", p)):
        r = fn()
        assert r.get("is_error") and "access denied" in text(r)


def test_absolute_escape_blocked(box, tmp_path):
    p = str(tmp_path / "secret.txt")
    with pytest.raises(SandboxError):
        resolve_in_sandbox(box, p)
    assert file_stats_impl(box, p).get("is_error")


def test_absolute_inside_allowed(box):
    assert resolve_in_sandbox(box, str(box / "a.txt")) == (box / "a.txt").resolve()


def test_windows_drive_and_unc_blocked(box):
    for p in ["C:\\Windows\\win.ini", "\\\\server\\share\\x", "C:/Windows/win.ini"]:
        with pytest.raises(SandboxError):
            resolve_in_sandbox(box, p)


def test_invalid_paths(box):
    for p in ["", "  ", "a\x00b"]:
        with pytest.raises(SandboxError):
            resolve_in_sandbox(box, p)


def test_symlink_escape_blocked(box, tmp_path):
    link = box / "link.txt"
    try:
        os.symlink(tmp_path / "secret.txt", link)
    except (OSError, NotImplementedError):
        pytest.skip("symlink not permitted on this system")
    with pytest.raises(SandboxError):
        resolve_in_sandbox(box, "link.txt")
    assert "TOPSECRET" not in text(search_text_impl(box, "TOPSECRET"))


def test_builtin_hook_check(box, tmp_path):
    outside = str(tmp_path / "secret.txt")
    assert check_builtin_tool_input(box, "Read", {"file_path": outside})
    assert check_builtin_tool_input(box, "Write", {"file_path": "../x.txt"})
    assert check_builtin_tool_input(box, "Grep", {"pattern": "x", "path": ".."})
    assert check_builtin_tool_input(box, "Glob", {"pattern": "../*"})
    assert check_builtin_tool_input(box, "Glob", {"pattern": "/etc/*"})
    assert check_builtin_tool_input(box, "Read", {"file_path": "a.txt"}) is None
    assert check_builtin_tool_input(box, "Grep", {"pattern": "a:b"}) is None
    assert check_builtin_tool_input(box, "Glob", {"pattern": "**/*.txt"}) is None
