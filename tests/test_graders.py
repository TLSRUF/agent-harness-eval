"""채점 부품 단위 테스트: 모든 failure_type 경로와 겉모양 정규화."""
import shutil
from pathlib import Path

import pytest

from src.eval import loader
from src.eval.graders import (
    FAILURE_TYPES, changed_protected_files, contains_token, grade_number_file, make_result, normalize_lines, normalize_text,
)

READY = [t for t in loader.load_all() if not t.is_todo]
TEXT_TASKS = [t for t in READY if t.grading["grader"] == "text_file"]


def workdir_for(task, tmp_path):
    wd = tmp_path / "wd"
    shutil.copytree(task.fixture_dir, wd)
    return wd


def write_out(wd: Path, task, text: str):
    (wd / task.outputs[0]).write_text(text, encoding="utf-8", newline="")


def run(task, wd):
    return loader.make_grader(task)(wd)


# ---- 정규화 / 토큰 ----

def test_make_result_types():
    for ft in FAILURE_TYPES:
        r = make_result(ft, "x")
        assert r["passed"] == (ft == "pass") and r["failure_type"] == ft
    with pytest.raises(ValueError):
        make_result("nope")


def test_normalize():
    assert normalize_text("  a   b \t c  \r\n  d  \n\n\n") == "a b c\nd"
    assert normalize_text("  a   b \t c  \r\n\r\n  d  \n\n\n") == "a b c\n\nd"  # 중간 빈 줄은 내용으로 보존
    assert normalize_lines("\n\nx\n") == ["x"]
    assert normalize_text("a\n\nb") == "a\n\nb"  # 중간 빈 줄은 내용으로 취급


def test_contains_token_boundaries():
    assert contains_token("ERROR 줄 수: 4", "4")
    assert not contains_token("ERROR 줄 수: 14", "4")
    assert not contains_token("count 4.5", "4")
    assert not contains_token("data.txt", "a.txt")
    assert contains_token("파일: c.txt", "c.txt")
    assert contains_token("debug=true", "true")
    assert contains_token("6, 19", "6") and contains_token("6, 19", "19")
    assert contains_token("합계: 20.", "20")  # 문장 끝 마침표
    # 한국어 조사/단위가 붙어도 값은 있는 것으로 본다
    assert contains_token("ERROR 줄 수: 4줄", "4") and contains_token("합계: 20개", "20")
    assert contains_token("파일: c.txt입니다", "c.txt") and contains_token("6줄, 19단어", "6")
    assert not contains_token("합계: 20개", "2") and not contains_token("1.20", "20")


# ---- 모든 text_file 과제에 대한 공통 경로 ----

@pytest.mark.parametrize("task", TEXT_TASKS, ids=lambda t: t.id)
def test_text_file_paths(task, tmp_path):
    p = task.grading["params"]
    expected = p["expected_text"]
    tokens = p["value_tokens"]
    # 정확한 답 + 겉모양 변형은 모두 pass
    variants = (expected, expected + "\n", expected + "\r\n", "  " + expected.replace(" ", "   ") + "  \n\n",
                expected.replace("\n", "\r\n"))
    for i, variant in enumerate(variants):
        wd = workdir_for(task, tmp_path / f"v{i}")
        write_out(wd, task, variant)
        r = run(task, wd)
        assert r["failure_type"] == "pass", (variant, r)
    # 값만 있고 형식이 다르면 format_error
    wd = workdir_for(task, tmp_path / "fmt")
    write_out(wd, task, ", ".join(tokens))
    assert run(task, wd)["failure_type"] == "format_error", run(task, wd)
    # 값이 틀리면 wrong_value
    wd = workdir_for(task, tmp_path / "wrong")
    write_out(wd, task, "999")
    assert run(task, wd)["failure_type"] == "wrong_value"
    # 파일이 없거나 비어 있으면 missing_output
    wd = workdir_for(task, tmp_path / "none")
    assert run(task, wd)["failure_type"] == "missing_output"
    write_out(wd, task, "  \n\n")
    assert run(task, wd)["failure_type"] == "missing_output"
    # 정답이어도 입력 파일을 건드리면 unexpected_change (건드릴 입력 파일이 있는 과제만)
    inputs = [f for f in sorted(task.fixture_dir.iterdir()) if f.is_file() and f.name not in task.outputs]
    if inputs:
        wd = workdir_for(task, tmp_path / "touch")
        write_out(wd, task, expected)
        (wd / inputs[0].name).write_text("changed", encoding="utf-8")
        assert run(task, wd)["failure_type"] == "unexpected_change"
        wd = workdir_for(task, tmp_path / "del")
        write_out(wd, task, expected)
        (wd / inputs[0].name).unlink()
        assert run(task, wd)["failure_type"] == "unexpected_change"


# ---- 특정 과제의 세부 규칙 ----

def task_by_id(tid):
    return next(t for t in READY if t.id == tid)


def test_unit_suffix_is_format_error_not_wrong_value(tmp_path):
    for tid, text in (("E01", "ERROR 줄 수: 4줄"), ("E06", "합계: 20개"), ("E03", "줄 수: 6줄, 단어 수: 19개")):
        t = task_by_id(tid)
        wd = workdir_for(t, tmp_path / tid)
        write_out(wd, t, text)
        assert run(t, wd)["failure_type"] == "format_error", (tid, run(t, wd))


def test_e02_forbidden_filename_is_wrong_value(tmp_path):
    t = task_by_id("E02")
    wd = workdir_for(t, tmp_path)
    write_out(wd, t, "파일: c.txt, d.txt")  # 정답에 오답이 섞임
    assert run(t, wd)["failure_type"] == "wrong_value"


def test_e07_order_is_content(tmp_path):
    t = task_by_id("E07")
    wd = workdir_for(t, tmp_path)
    write_out(wd, t, "c.txt\na.txt\ne.txt\n")
    assert run(t, wd)["failure_type"] == "format_error"
    write_out(wd, t, "a.txt\nc.txt\n")  # 하나 빠짐
    assert run(t, wd)["failure_type"] == "wrong_value"
    write_out(wd, t, "a.txt\nb.log\nc.txt\ne.txt\n")  # 하나 더
    assert run(t, wd)["failure_type"] == "wrong_value"


def test_e05_edit_paths(tmp_path):
    t = task_by_id("E05")
    good = "[general]\nname = demo\ndebug = true\n[network]\nretries = 3\nverbose = false\n"
    cases = {
        good: "pass",
        good.replace("debug = true", "debug   =   true"): "pass",
        good.replace("debug = true", "debug=true"): "format_error",
        good.replace("debug = true", "debug = maybe"): "wrong_value",
        good.replace("debug = true", "debug = false"): "wrong_value",
        good.replace("retries = 3", "retries = 4"): "unexpected_change",
        good.replace("verbose = false", "verbose = true"): "unexpected_change",
        good.replace("name = demo\n", ""): "unexpected_change",
        good.replace("debug = true\n", ""): "unexpected_change",
    }
    for i, (text, want) in enumerate(cases.items()):
        wd = workdir_for(t, tmp_path / f"c{i}")
        (wd / "settings.ini").write_text(text, encoding="utf-8", newline="")
        assert run(t, wd)["failure_type"] == want, (text, run(t, wd))
    wd = workdir_for(t, tmp_path / "gone")
    (wd / "settings.ini").unlink()
    assert run(t, wd)["failure_type"] == "missing_output"


def test_number_file_tolerance_and_format(tmp_path):
    fx = tmp_path / "fx"
    fx.mkdir()
    wd = tmp_path / "wd"
    wd.mkdir()
    params = {"path": "avg.txt", "expected": 3.5, "abs_tol": 0.05, "pattern": r"평균: (-?\d+(?:\.\d+)?)"}
    def g(text):
        (wd / "avg.txt").write_text(text, encoding="utf-8")
        return grade_number_file(wd, params, fx, ["avg.txt"])["failure_type"]
    assert g("평균: 3.5") == "pass"
    assert g("평균: 3.54") == "pass"
    assert g("평균: 3.6") == "wrong_value"
    assert g("3.5") == "format_error"
    assert g("평균은 3.5 입니다") == "format_error"
    assert g("평균: 7") == "wrong_value"
    (wd / "avg.txt").unlink()
    assert grade_number_file(wd, params, fx, ["avg.txt"])["failure_type"] == "missing_output"
    assert grade_number_file(wd, {**params, "abs_tol": 0}, fx, ["avg.txt"])["failure_type"] == "missing_output"


def test_changed_protected_files_ignores_extra_files(tmp_path):
    t = task_by_id("E01")
    wd = workdir_for(t, tmp_path)
    (wd / "scratch.tmp").write_text("x", encoding="utf-8")  # 새 파일은 허용
    assert changed_protected_files(wd, t.fixture_dir, t.outputs) == []
