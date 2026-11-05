import json
from pathlib import Path

from src.eval.report import MIN_SAMPLE, build_report, chart_title, load_run, sample_label


def write_run(path: Path, task, calls, subtype="success", passed=True, errors=0, num_turns=3, max_turns=20, is_error=False):
    rows = [{"kind": "config", "task_id": task, "config": {"model": "claude-haiku-5-5", "prompt_version": "v1",
                                                            "max_turns": max_turns, "tool_desc_version": "default"}}]
    rows.append({"kind": "message", "message": {"_type": "AssistantMessage", "content": [
        {"_type": "ToolUseBlock", "id": str(i), "name": n, "input": {}} for i, n in enumerate(calls)]}})
    rows.append({"kind": "message", "message": {"_type": "UserMessage", "content": [
        {"_type": "ToolResultBlock", "tool_use_id": "x", "content": "e", "is_error": True} for _ in range(errors)]}})
    graded = None if passed is None else {"passed": passed}
    rows.append({"kind": "summary", "subtype": subtype, "is_error": is_error, "num_turns": num_turns,
                 "total_cost_usd": 0.01, "exception": None, "graded": graded})
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return load_run(path)


def test_sample_label_formats():
    assert sample_label({"a": 3, "b": 3}) == "N=2, 과제당 3회 / 총 6건"
    assert sample_label({"a": 2, "b": 3, "c": 3}) == "N=3, 과제당 2~3회(최소 2회) / 총 8건"
    assert sample_label({}) == "N=0, 과제당 0회 / 총 0건"
    assert chart_title("선택률", {"a": 3}) == "선택률 (N=1, 과제당 3회 / 총 3건)"


def test_categories_and_rates(tmp_path):
    runs = [
        write_run(tmp_path / "1.jsonl", "t1", ["mcp__t__search_text"], passed=True),
        write_run(tmp_path / "2.jsonl", "t1", ["Grep"], passed=False),
        write_run(tmp_path / "3.jsonl", "t2", ["Grep"], subtype="error_max_turns", passed=True, is_error=True, num_turns=6, max_turns=5),
        write_run(tmp_path / "4.jsonl", "t2", ["Grep"], subtype="error_max_turns", passed=False, is_error=True, num_turns=6, max_turns=5),
        write_run(tmp_path / "5.jsonl", "t3", [], subtype="error_during_execution", passed=False, is_error=True),
    ]
    assert [r.category for r in runs] == ["success_pass", "success_fail", "maxturns_pass", "maxturns_fail", "other_error"]
    overlap = {"t1": ["search_text|Grep"], "t2": ["search_text|Grep"]}
    rep = build_report(runs, overlap)
    assert "성공률 40% (N=3, 과제당 1~2회(최소 1회) / 총 5건)" in rep  # 통과 = 1 + 1(maxturns_pass)
    assert "선택률 25% (N=2, 과제당 2회 / 총 4건)" in rep
    assert "search_text 대 Grep: 25% (N=2, 과제당 2회 / 총 4건)" in rep
    assert "error_max_turns + 채점 통과 | 1" in rep
    assert "표본이 작아 해석에 주의" in rep
    assert "(overlap_with가 없는 과제의 실행 1건은 제외)" in rep
    assert "보정값" in rep


def test_no_warning_at_30(tmp_path):
    runs = [write_run(tmp_path / f"{i}.jsonl", f"t{i % 10}", ["mcp__t__file_stats"]) for i in range(MIN_SAMPLE)]
    overlap = {f"t{i}": ["file_stats|Read"] for i in range(10)}
    rep = build_report(runs, overlap)
    assert "선택률 100% (N=10, 과제당 3회 / 총 30건)" in rep
    assert "표본이 작아" not in rep


def test_tool_table_and_errors(tmp_path):
    r = write_run(tmp_path / "a.jsonl", "t1", ["mcp__t__check_result", "Read", "Read", "mcp__claude_ai_Gmail__x"], errors=1)
    rep = build_report([r], {})
    assert "check_result 1 | Read 2 | mcp__claude_ai_Gmail__x 1" in rep
    assert "도구 오류율: 1/4 = 25.0%" in rep
    assert "선택률 n/a (N=0, 과제당 0회 / 총 0건)" in rep


def test_ungraded_excluded_from_success(tmp_path):
    r = write_run(tmp_path / "a.jsonl", "t1", [], passed=None)
    rep = build_report([r], {})
    assert "성공률 n/a (N=0, 과제당 0회 / 총 0건)" in rep and "채점 없는 실행 1건" in rep
