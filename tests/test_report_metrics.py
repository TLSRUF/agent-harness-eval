"""report.py 새 지표 단위 테스트 (구현보다 먼저 작성): pass^k, 일관성, 도구 오류율(커스텀/내장 구분), min_steps 구간별 성공률.

모든 새 지표는 표본 크기 문구(N, 과제당 M회 / 총 K건)를 자동으로 붙이고, K가 30건 미만이면 경고도 붙인다.
"""
import json
import re
from pathlib import Path

import pytest

from src.eval import report
from src.eval.report import build_report, load_run, normalize_args

WARN = "표본이 작아 해석에 주의"


def write_run(path: Path, task, calls=(), *, passed=True, cwd=r"C:\w\task_a", graded=True):
    """calls: (도구 이름, 입력 dict, 오류 여부) 목록. ToolUseBlock id와 ToolResultBlock의 tool_use_id를 짝지어 기록한다."""
    rows = [{"kind": "config", "task_id": task, "config": {"model": "claude-haiku-5-5", "prompt_version": "v1", "max_turns": 20,
                                                           "tool_desc_version": "default"}},
            {"kind": "message", "message": {"_type": "SystemMessage", "subtype": "init", "data": {"cwd": cwd, "tools": []}}}]
    for i, (name, inp, is_err) in enumerate(calls):
        rows.append({"kind": "message", "message": {"_type": "AssistantMessage", "content": [
            {"_type": "ToolUseBlock", "id": f"tu{i}", "name": name, "input": inp}]}})
        rows.append({"kind": "message", "message": {"_type": "UserMessage", "content": [
            {"_type": "ToolResultBlock", "tool_use_id": f"tu{i}", "content": "x", "is_error": True if is_err else None}]}})
    rows.append({"kind": "summary", "subtype": "success", "is_error": False, "num_turns": 3, "total_cost_usd": 0.01,
                 "exception": None, "graded": ({"passed": passed} if graded else None)})
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    return load_run(path)


def line(text: str, prefix: str) -> str:
    found = [ln for ln in text.splitlines() if re.sub(r"^- ", "", ln).startswith(prefix)]  # '기타 지표'의 불릿(- )은 허용
    assert len(found) == 1, (prefix, found, text)
    return found[0]


def runs_of(tmp_path, spec):
    """spec: {과제: [통과 여부(True/False/None=채점없음), ...]} -> Run 목록."""
    out = []
    for task, results in spec.items():
        for i, res in enumerate(results):
            out.append(write_run(tmp_path / f"{task}_{i}.jsonl", task, passed=bool(res), graded=res is not None))
    return out


# ---------------- pass^k ----------------

def test_pass_k_with_sample_size_and_single_run_average_on_the_same_line(tmp_path):
    runs = runs_of(tmp_path, {"t1": [True, True], "t2": [True, False], "t3": [True], "t4": [True, True, True], "t5": [None, True]})
    ln = line(build_report(runs), "pass^k")
    # 대상: 반복 2회 이상(채점된 실행 기준)인 t1, t2, t4. t3은 1회, t5는 채점된 실행이 1회뿐이라 제외
    assert "pass^k 67%" in ln                                                    # t1, t4만 모두 성공 -> 2/3
    assert "단일 실행 평균 성공률 86%" in ln                                       # 통과 6 / 실행 7
    assert "N=3, 과제당 2~3회(최소 2회) / 총 7건" in ln
    assert WARN in ln


def test_pass_k_equal_repeat_counts_and_all_fail(tmp_path):
    runs = runs_of(tmp_path, {"a": [False, False], "b": [True, False], "c": [True, True]})
    ln = line(build_report(runs), "pass^k")
    assert "pass^k 33%" in ln and "단일 실행 평균 성공률 50%" in ln and "N=3, 과제당 2회 / 총 6건" in ln


def test_pass_k_without_repeated_tasks_is_not_available(tmp_path):
    ln = line(build_report(runs_of(tmp_path, {"a": [True], "b": [False]})), "pass^k")
    assert "pass^k n/a" in ln and "N=0, 과제당 0회 / 총 0건" in ln


def test_pass_k_no_warning_at_30_runs(tmp_path):
    runs = runs_of(tmp_path, {f"t{i}": [True, i % 2 == 0] for i in range(15)})        # 15과제 x 2회 = 30건
    ln = line(build_report(runs), "pass^k")
    assert "N=15, 과제당 2회 / 총 30건" in ln and WARN not in ln


def test_pass_k_counts_ungraded_runs_out(tmp_path):
    runs = runs_of(tmp_path, {"a": [True, None, True], "b": [None, None]})
    ln = line(build_report(runs), "pass^k")
    assert "pass^k 100%" in ln and "N=1, 과제당 2회 / 총 2건" in ln                     # a는 채점된 2회, b는 제외


# ---------------- 일관성 ----------------

def test_normalize_args_ignores_key_order_and_path_separators():
    a = normalize_args({"file_path": r"C:\w\task_a\out.txt", "content": "x", "n": [1, {"z": 1, "y": 2}]}, r"C:\w\task_a")
    b = normalize_args({"n": [1, {"y": 2, "z": 1}], "content": "x", "file_path": "C:/w/task_b/out.txt"}, "C:/w/task_b")
    assert a == b
    assert a != normalize_args({"file_path": r"C:\w\task_a\other.txt", "content": "x", "n": [1, {"z": 1, "y": 2}]}, r"C:\w\task_a")
    assert a != normalize_args({"file_path": r"C:\w\task_a\out.txt", "content": "y", "n": [1, {"z": 1, "y": 2}]}, r"C:\w\task_a")


def test_normalize_args_cwd_prefix_needs_a_path_boundary_and_handles_missing_cwd():
    assert normalize_args({"p": r"C:\w\task_ab\f.txt"}, r"C:\w\task_a") != normalize_args({"p": r"C:\w\task_a\f.txt"}, r"C:\w\task_a")
    assert normalize_args({"p": r"C:\w\task_a"}, r"C:\w\task_a") == normalize_args({"p": "C:/w/task_a/"[:-1]}, "C:/w/task_a")
    assert normalize_args({"p": "x"}, None) == normalize_args({"p": "x"}, "")
    assert normalize_args({"k": None, "b": True, "n": 1.5, "s": "한글"}, None)  # 비문자열 값도 처리


def test_core_args_exclude_content_args_and_keep_selection_args():
    from src.eval.report import CONTENT_ARG_NAMES, core_args
    assert CONTENT_ARG_NAMES == {"content", "old_string", "new_string", "contains"}
    assert core_args({"file_path": "f", "content": "x"}) == {"file_path": "f"}                      # Write
    assert core_args({"file_path": "f", "old_string": "a", "new_string": "b", "replace_all": True}) == {"file_path": "f", "replace_all": True}  # Edit
    assert core_args({"pattern": "ERROR", "path": "p", "output_mode": "content", "-n": True}) == {
        "pattern": "ERROR", "path": "p", "output_mode": "content", "-n": True}                      # Grep
    assert core_args({"path": "p", "contains": "x", "min_lines": 1}) == {"path": "p", "min_lines": 1}  # check_result
    assert core_args({"query": "q", "path": "p"}) == {"query": "q", "path": "p"}                    # search_text
    # 로그에서 이름을 확인하지 못한 인자(Glob, Read의 offset/limit, Grep의 glob/type/-i)는 핵심으로 취급한다
    assert core_args({"glob": "*.log", "type": "py", "-i": True, "offset": 3, "limit": 10, "head_limit": 5}) == {
        "glob": "*.log", "type": "py", "-i": True, "offset": 3, "limit": 10, "head_limit": 5}
    assert core_args({}) == {}


def test_consistency_core_args_versus_full_args(tmp_path):
    def calls(cwd, content="x", pattern="ERROR"):
        sep = "\\" if "\\" in cwd else "/"
        return [("Grep", {"pattern": pattern, "path": cwd, "output_mode": "content"}, False),
                ("Write", {"file_path": cwd + sep + "result.txt", "content": content}, False)]
    runs = [
        write_run(tmp_path / "a1.jsonl", "A", calls(r"C:\w\task_1"), cwd=r"C:\w\task_1"),
        write_run(tmp_path / "a2.jsonl", "A", calls("C:/w/task_2"), cwd="C:/w/task_2"),               # 경로 구분자와 임시 폴더만 다름
        write_run(tmp_path / "a3.jsonl", "A", calls(r"C:\w\task_3", content="y"), cwd=r"C:\w\task_3"),  # Write 내용만 다름
        write_run(tmp_path / "b1.jsonl", "B", [("Read", {"file_path": "f"}, False), ("Write", {"file_path": "g", "content": "1"}, False)]),
        write_run(tmp_path / "b2.jsonl", "B", [("Write", {"file_path": "g", "content": "1"}, False), ("Read", {"file_path": "f"}, False)]),  # 순서 다름
        write_run(tmp_path / "d1.jsonl", "D", calls(r"C:\w\task_1"), cwd=r"C:\w\task_1"),
        write_run(tmp_path / "d2.jsonl", "D", calls(r"C:\w\task_1", pattern="WARN"), cwd=r"C:\w\task_1"),  # 검색어(핵심 인자)가 다름
        write_run(tmp_path / "c1.jsonl", "C", calls(r"C:\w\task_1"), cwd=r"C:\w\task_1"),              # 1회뿐이라 제외
    ]
    ln = line(build_report(runs), "일관성")
    # 쌍: A 3개(1-2, 1-3, 2-3), B 1개, D 1개 = 5개
    # (a) 이름 순서: A 3/3, B 0/1, D 1/1 -> 4/5 = 80%
    # (b) 이름+핵심 인자: A 3/3(Write 내용은 제외하므로 a3도 같음), B 0, D 0(검색어 다름) -> 3/5 = 60%
    # (c) 이름+전체 인자(참고): A는 1-2만 같음(내용이 다른 a3 제외), B 0, D 0 -> 1/5 = 20%
    assert "(a) 도구 이름 순서 일치 80%" in ln
    assert "(b) 이름과 핵심 인자까지 일치 60%" in ln
    assert "(c) 참고: 전체 인자까지 일치 20%" in ln
    assert "비교한 쌍 5개" in ln and "N=3, 과제당 2~3회(최소 2회) / 총 7건" in ln and WARN in ln
    assert ln.index("(a)") < ln.index("(b)") < ln.index("(c)")


def test_consistency_edit_strings_are_content_args(tmp_path):
    def run(i, old, new, replace_all=False):
        return write_run(tmp_path / f"e{i}.jsonl", "E", [
            ("Read", {"file_path": "f"}, False),
            ("Edit", {"file_path": "f", "old_string": old, "new_string": new, "replace_all": replace_all}, False)])
    same_core = [run(1, "a", "b"), run(2, "cat", "dog")]                    # old/new_string만 다름
    ln = line(build_report(same_core), "일관성")
    assert "(b) 이름과 핵심 인자까지 일치 100%" in ln and "(c) 참고: 전체 인자까지 일치 0%" in ln
    diff_core = [run(1, "a", "b", False), run(2, "a", "b", True)]            # replace_all은 편집 방식을 정하는 옵션이라 핵심으로 본다
    ln = line(build_report(diff_core), "일관성")
    assert "(b) 이름과 핵심 인자까지 일치 0%" in ln and "(c) 참고: 전체 인자까지 일치 0%" in ln


def test_consistency_all_identical_and_no_repeats(tmp_path):
    same = [("Read", {"file_path": r"C:\w\task_a\f"}, False), ("Write", {"file_path": r"C:\w\task_a\o", "content": "z"}, False)]
    runs = [write_run(tmp_path / f"r{i}.jsonl", "T", same) for i in range(3)]
    ln = line(build_report(runs), "일관성")
    assert "(a) 도구 이름 순서 일치 100%" in ln and "(b) 이름과 핵심 인자까지 일치 100%" in ln
    assert "(c) 참고: 전체 인자까지 일치 100%" in ln and "비교한 쌍 3개" in ln
    ln2 = line(build_report([write_run(tmp_path / "solo.jsonl", "S", same)]), "일관성")
    assert ln2.count("n/a") == 3 and "N=0, 과제당 0회 / 총 0건" in ln2 and "비교한 쌍 0개" in ln2


def test_consistency_without_tool_calls_counts_as_identical(tmp_path):
    runs = [write_run(tmp_path / f"e{i}.jsonl", "E", []) for i in range(2)]
    ln = line(build_report(runs), "일관성")
    assert "(a) 도구 이름 순서 일치 100%" in ln and "(b) 이름과 핵심 인자까지 일치 100%" in ln


# ---------------- 도구 오류율 (커스텀/내장 구분) ----------------

def test_tool_error_rate_split_between_custom_and_builtin(tmp_path):
    calls = [("mcp__t__file_stats", {"path": "a"}, True), ("mcp__t__file_stats", {"path": "b"}, False),
             ("Read", {"file_path": "a"}, False), ("Read", {"file_path": "b"}, False), ("Read", {"file_path": "c"}, False),
             ("Write", {"file_path": "o", "content": "x"}, True), ("mcp__claude_ai_Example__x", {}, True)]
    text = build_report([write_run(tmp_path / "r.jsonl", "T", calls)])
    assert "도구 오류율: 3/7 = 42.9%" in text                                    # 기존 전체 비율 줄은 그대로
    ln = line(text, "도구 오류율(구분)")
    assert "커스텀 1/2 = 50.0%" in ln and "내장 1/4 = 25.0%" in ln and "기타 1/1 = 100.0%" in ln


def test_tool_error_rate_split_handles_zero_calls_and_unmatched_ids(tmp_path):
    ln = line(build_report([write_run(tmp_path / "z.jsonl", "T", [])]), "도구 오류율(구분)")
    assert "커스텀 0/0 = n/a" in ln and "내장 0/0 = n/a" in ln
    # tool_use_id가 짝이 안 맞는 오류 결과는 어느 도구인지 알 수 없으므로 구분 집계에서 빼고 개수만 따로 표시한다
    rows = [{"kind": "config", "task_id": "T", "config": {}},
            {"kind": "message", "message": {"_type": "UserMessage", "content": [{"_type": "ToolResultBlock", "tool_use_id": "nope", "is_error": True}]}},
            {"kind": "summary", "subtype": "success", "graded": {"passed": True}}]
    p = tmp_path / "u.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    ln = line(build_report([load_run(p)]), "도구 오류율(구분)")
    assert "기타 0/0 = n/a" in ln and "짝 없는 오류 결과 1건" in ln


# ---------------- min_steps 구간별 성공률 (주: 2구간, 보조: 3구간) ----------------

AUX = "보조(3구간) min_steps "


def test_bins_are_two_primary_and_three_auxiliary():
    from src.eval import report
    assert report.MIN_STEPS_BINS == [("1~2", 1, 2), ("3 이상", 3, None)]
    assert report.MIN_STEPS_BINS_AUX == [("1~2", 1, 2), ("3~7", 3, 7), ("8 이상", 8, None)]


def test_success_rate_by_min_steps_primary_two_bins_and_auxiliary_three_bins(tmp_path):
    runs = runs_of(tmp_path, {"s1": [True], "s2": [True, False], "s3": [True], "s4": [False], "s5": [True, True], "s9": [False],
                              "x": [True], "g": [None]})
    ms = {"s1": 1, "s2": 2, "s3": 3, "s4": 4, "s5": 5, "s9": 9, "g": 2}
    text = build_report(runs, min_steps=ms)
    assert "min_steps 1~2: 성공률 67% (N=2, 과제당 1~2회(최소 1회) / 총 3건)" in line(text, "min_steps 1~2: 성공률")
    assert "min_steps 3 이상: 성공률 60% (N=4, 과제당 1~2회(최소 1회) / 총 5건)" in line(text, "min_steps 3 이상: 성공률")
    assert "성공률 67% (N=2, 과제당 1~2회(최소 1회) / 총 3건)" in line(text, AUX + "1~2")
    assert "성공률 75% (N=3, 과제당 1~2회(최소 1회) / 총 4건)" in line(text, AUX + "3~7")
    assert "성공률 0% (N=1, 과제당 1회 / 총 1건)" in line(text, AUX + "8 이상")
    assert "min_steps 없는 과제 1개 제외(실행 1건)" in text                       # x는 목록에 없음. g는 채점이 없어 성공률에서만 빠짐
    assert all(WARN in line(text, p) for p in ("min_steps 1~2: 성공률", "min_steps 3 이상: 성공률", AUX + "1~2", AUX + "3~7", AUX + "8 이상"))
    assert text.index("min_steps 3 이상: 성공률") < text.index(AUX + "1~2")      # 주 지표가 먼저, 보조가 뒤


def test_old_three_bins_are_gone(tmp_path):
    runs = runs_of(tmp_path, {"a": [True], "b": [True]})
    text = build_report(runs, min_steps={"a": 2, "b": 6})
    assert "3~4" not in text and "5 이상" not in text


def test_min_steps_bin_boundaries_and_empty_bins(tmp_path):
    runs = runs_of(tmp_path, {"a": [True], "b": [True], "c": [False], "d": [True], "e": [True]})
    text = build_report(runs, min_steps={"a": 2, "b": 3, "c": 7, "d": 8, "e": 11})
    assert "min_steps 1~2: 성공률 100% (N=1, 과제당 1회 / 총 1건)" in line(text, "min_steps 1~2: 성공률")   # 2는 1~2 구간
    assert "min_steps 3 이상: 성공률 75% (N=4" in line(text, "min_steps 3 이상: 성공률")                   # 3, 7, 8, 11
    assert "성공률 50% (N=2" in line(text, AUX + "3~7")                                                     # 3과 7은 3~7 구간
    assert "성공률 100% (N=2" in line(text, AUX + "8 이상")                                                 # 8과 11은 8 이상
    empty = build_report([], min_steps={})
    for label in ("min_steps 1~2: 성공률", "min_steps 3 이상: 성공률", AUX + "1~2", AUX + "3~7", AUX + "8 이상"):
        assert "성공률 n/a (N=0, 과제당 0회 / 총 0건)" in line(empty, label), label


def test_min_steps_unknown_means_no_binning(tmp_path):
    text = build_report(runs_of(tmp_path, {"a": [True]}))
    assert "min_steps 정보가 없어 구간별 성공률을 계산하지 않음" in text and "3 이상" not in text


def test_min_steps_invalid_values_are_treated_as_missing(tmp_path):
    runs = runs_of(tmp_path, {"a": [True], "b": [True], "c": [True]})
    text = build_report(runs, min_steps={"a": 0, "b": None, "c": 2})
    assert text.count("min_steps 없는 과제 2개 제외(실행 2건)") == 1               # 제외 안내는 한 번만
    assert "min_steps 1~2: 성공률 100% (N=1" in line(text, "min_steps 1~2: 성공률")


# ---------------- 공통 규칙: 표본 크기 문구 자동 출력 ----------------

def test_every_new_metric_line_carries_a_sample_label(tmp_path):
    runs = runs_of(tmp_path, {"a": [True, False], "b": [True, True]})
    text = build_report(runs, min_steps={"a": 2, "b": 6})
    label = re.compile(r"N=\d+, 과제당 \d+(~\d+회\(최소 \d+회\)|회) / 총 \d+건")
    for prefix in ("pass^k", "일관성", "min_steps 1~2: 성공률", "min_steps 3 이상: 성공률", AUX + "1~2", AUX + "3~7", AUX + "8 이상"):
        assert label.search(line(text, prefix)), prefix


# ---------------- 기존 로그로 실행 ----------------

def test_report_on_existing_demo_logs_includes_new_sections():
    files = sorted((Path(__file__).resolve().parents[1] / "results" / "raw").glob("day3demo_haiku_normal_run*.jsonl"))
    if len(files) < 2:
        pytest.skip("Day 3 데모 로그가 로컬에 없음")
    text = build_report([load_run(f) for f in files])
    assert "pass^k 100%" in line(text, "pass^k") and "N=1, 과제당 2회 / 총 2건" in line(text, "pass^k")
    assert "일관성" in text and "도구 오류율(구분)" in text and WARN in line(text, "pass^k")
