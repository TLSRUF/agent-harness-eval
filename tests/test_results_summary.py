"""results_summary 테스트 (구현보다 먼저 작성). 합성 로그만 쓴다. 모델 호출 없음, results/raw는 읽기 전용.

docs/results.md의 수치는 results/raw 로그에서 스크립트가 만든다. 여기서는 그 계산과 문서 형식을 고정한다.
"""
import json
import re
from pathlib import Path

import pytest

from src.eval import exp_compare as ec
from src.eval import loader, results_summary as rs

TASKS = {t.id: t for t in loader.load_all() if not t.is_todo}
F_TASKS = ["E01", "M01", "M05", "M07"]
EXPECTED = {"E01": 4, "M01": 23, "M05": 17, "M07": 14}
OUTFILE = {"E01": "result.txt", "M01": "result.txt", "M05": "both.out", "M07": "total.out"}
CUSTOM = "mcp__t__search_text"
HEAD = "gateway.log"
USER_NAME = "zzuser"


def _lines(n, with_total=None):
    body = "\n".join(f"{HEAD}:{i + 1}:dev-017 line" for i in range(n)) if n else "no matches"
    return f"total matches: {with_total}\n{body}" if with_total is not None else body


def mk(d: Path, prefix, task, run, calls=(), *, passed=True, failure_type=None, subtype="success", cost=0.002, final=True, ts=None, err=()):
    """calls: (이름, 입력 dict, 결과 텍스트 또는 None) 목록. 호출마다 응답 하나."""
    rows = [{"kind": "config", "task_id": task, "config": {"model": "claude-haiku-5-5", "max_turns": 20, "tool_desc_version": "long"}},
            {"kind": "message", "message": {"_type": "SystemMessage", "subtype": "init",
                                            "data": {"cwd": f"C:\\Users\\{USER_NAME}\\AppData\\Local\\Temp\\task_abc", "tools": []}}}]
    for i, (name, inp, res) in enumerate(calls):
        rows.append({"kind": "message", "message": {"_type": "AssistantMessage", "message_id": f"m{i}",
                                                    "content": [{"_type": "ToolUseBlock", "id": f"t{i}", "name": name, "input": inp}]}})
        if res is not None:
            content = [{"type": "text", "text": res}] if name.startswith("mcp__") else res
            rows.append({"kind": "message", "message": {"_type": "UserMessage", "content": [
                {"_type": "ToolResultBlock", "tool_use_id": f"t{i}", "content": content, "is_error": i in err}]}})
    if final:
        rows.append({"kind": "message", "message": {"_type": "AssistantMessage", "message_id": "mf", "content": [{"_type": "TextBlock", "text": "done"}]}})
    rows.append({"kind": "summary", "subtype": subtype, "is_error": subtype != "success", "num_turns": len(calls) + 1, "total_cost_usd": cost,
                 "usage": {"input_tokens": 10, "cache_creation_input_tokens": 100, "cache_read_input_tokens": 1000}, "exception": None,
                 "graded": {"passed": passed, "failure_type": "pass" if passed else (failure_type or "wrong_value")}, **({"ts": ts} if ts else {})})
    (d / f"{prefix}_{task}_run{run}.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")


NL = "\n"


def write_call(task, value):
    path = f"C:\\Users\\{USER_NAME}\\AppData\\Local\\Temp\\task_abc\\{OUTFILE[task]}"
    return ("Write", {"file_path": path, "content": f"줄 수: {value}\n"}, "File created successfully")


def search_call(task, n, total=None):
    return (CUSTOM, {"query": "x", "path": "."}, _lines(n, total))


def grep_count(task, n):
    return ("Grep", {"pattern": "x", "output_mode": "count"}, f"{HEAD}:{n}\n\nFound {n} total occurrences across 1 file.")


def grep_content(task, n):
    return ("Grep", {"pattern": "x", "output_mode": "content", "-n": True}, "\n".join(f"{i + 1}:dev line" for i in range(n)))


F_CTL, F_VAR = ec.PREFIXES_F["long"], ec.PREFIXES_F["long_countline"]


REAL_REACH = {("M01", 1), ("M01", 2), ("M01", 3), ("M07", 4), ("M07", 5)}       # 실제 실험 F처럼 조건당 5/20
ALL_CELLS = {(t, r) for t in F_TASKS for r in range(1, 6)}


def fill_f(d, ctl_fail=(), var_fail=(), st_cells=REAL_REACH):
    """4과제 x 5회. st_cells 의 (과제, run)에서는 search_text를 쓰고(run 1, 2 는 Grep count 모드도), 나머지는 Grep content만."""
    for pre, fails, with_total in ((F_CTL, ctl_fail, False), (F_VAR, var_fail, True)):
        for t in F_TASKS:
            for r in range(1, 6):
                exp = EXPECTED[t]
                bad = (t, r) in fails
                val = exp + 2 if bad else exp
                if (t, r) in st_cells:
                    calls = [search_call(t, exp, exp if with_total else None)]
                    if r <= 2:
                        calls.append(grep_count(t, exp))
                else:
                    calls = [grep_content(t, exp)]
                calls.append(write_call(t, val))
                mk(d, pre, t, r, calls, passed=not bad)


def fill_all_experiments(d):
    """A~E 각 열에 과제 몇 개를 채운다(섹션이 비지 않을 정도)."""
    for table in (ec.PREFIXES, ec.PREFIXES_B, ec.PREFIXES_C, ec.PREFIXES_D, ec.PREFIXES_E):
        for pre in table.values():
            for t in ("E01", "M01", "E03"):
                for r in (1, 2, 3):
                    mk(d, pre, t, r, [grep_count(t, EXPECTED.get(t, 3)), write_call("E01" if t == "E03" else t, 1)])


EXPS = ["A", "B", "C", "D", "E", "F"]


# ---------------- 문서 형식 ----------------

def test_document_has_one_section_per_experiment_with_fixed_subsections(tmp_path):
    fill_all_experiments(tmp_path)
    fill_f(tmp_path)
    text = rs.build(tmp_path, TASKS)
    pos = [text.index(f"## 실험 {e}") for e in EXPS]
    assert pos == sorted(pos)
    for i, e in enumerate(EXPS):
        sec = text[pos[i]:pos[i + 1] if i + 1 < len(pos) else len(text)]
        for sub in ("### 질문", "### 설정", "### 표본", "### 핵심 지표", "### 해석", "### 한계"):
            assert sub in sec, (e, sub)
        assert "관찰:" in sec and "가설:" in sec, e


def test_table_of_contents_lists_every_section(tmp_path):
    fill_all_experiments(tmp_path)
    fill_f(tmp_path)
    text = rs.build(tmp_path, TASKS)
    toc = text[:text.index("## 실험 A")]
    for e in EXPS:
        assert f"실험 {e}" in toc


def test_each_core_table_carries_sample_size_text(tmp_path):
    fill_all_experiments(tmp_path)
    fill_f(tmp_path)
    text = rs.build(tmp_path, TASKS)
    for e in EXPS:
        sec = text[text.index(f"## 실험 {e}"):]
        sec = sec[:sec.index("### 해석")]
        assert re.search(r"N=\d+, 과제당 \d+(~\d+)?회", sec), e
        assert "총 " in sec


def test_missing_experiment_is_marked_not_crashing(tmp_path):
    fill_f(tmp_path)
    text = rs.build(tmp_path, TASKS)
    sec = text[text.index("## 실험 D"):text.index("## 실험 E")]
    assert "로그 없음" in sec


# ---------------- 수치는 로그에서 ----------------

def test_core_table_numbers_come_from_logs(tmp_path):
    fill_f(tmp_path, ctl_fail={("M01", 2), ("M05", 1)}, var_fail={("M07", 1)})
    text = rs.build(tmp_path, TASKS)
    sec = text[text.index("## 실험 F"):]
    assert "90% (18/20)" in sec
    assert "95% (19/20)" in sec


def test_f_states_effect_not_confirmed_and_reach_5_of_20(tmp_path):
    fill_f(tmp_path, ctl_fail={("M01", 2)}, var_fail={("M07", 1)})
    sec = rs.build(tmp_path, TASKS)
    sec = sec[sec.index("## 실험 F"):]
    assert "효과를 확인하지 못함" in sec
    assert "개입이 닿은 실행이 조건당 5/20" in sec


def test_f_reach_differs_by_condition_are_both_named(tmp_path):
    fill_f(tmp_path, st_cells=ALL_CELLS)
    for t in F_TASKS:                                                  # expFctl 쪽만 run 5 에서 search_text를 쓰지 않게 바꾼다
        mk(tmp_path, F_CTL, t, 5, [grep_content(t, EXPECTED[t]), write_call(t, EXPECTED[t])])
    sec = rs.build(tmp_path, TASKS)
    sec = sec[sec.index("## 실험 F"):]
    assert "expFctl 16/20" in sec and "expF 20/20" in sec


# ---------------- 실험 F 메커니즘 ----------------

def test_mechanism_rows_only_for_runs_that_used_search_text(tmp_path):
    fill_f(tmp_path, st_cells={(t, r) for t in F_TASKS for r in (2, 4)})
    cols = ec.collect(tmp_path, ec.PREFIXES_F)
    rows = rs.mechanism_rows(cols, TASKS)
    assert len(rows) == 16                                             # 4과제 x 2회 x 2조건
    assert {r["run"] for r in rows} == {2, 4}


def test_mechanism_row_values(tmp_path):
    mk(tmp_path, F_CTL, "M01", 3, [search_call("M01", 23), write_call("M01", 23)])
    mk(tmp_path, F_VAR, "M01", 3, [search_call("M01", 23, 23), grep_count("M01", 23), write_call("M01", 25)], passed=False)
    cols = ec.collect(tmp_path, ec.PREFIXES_F)
    by = {r["condition"]: r for r in rs.mechanism_rows(cols, TASKS)}
    c, v = by["long"], by["long_countline"]
    assert (c["task"], c["run"], c["search_lines"], c["total_matches"], c["agent_value"], c["expected"], c["passed"], c["grep_count_mode"]) == \
           ("M01", 3, 23, None, 23, 23, True, False)
    assert (v["search_lines"], v["total_matches"], v["agent_value"], v["expected"], v["passed"], v["grep_count_mode"]) == (23, 23, 25, 23, False, True)


def test_search_lines_counts_returned_lines_and_ignores_truncation_note_and_no_matches(tmp_path):
    body = "\n".join(f"{HEAD}:{i}:x" for i in range(1, 51)) + "\n(truncated at 50)"
    mk(tmp_path, F_CTL, "M01", 1, [(CUSTOM, {}, body), write_call("M01", 23)])
    mk(tmp_path, F_CTL, "M05", 1, [(CUSTOM, {}, "no matches"), write_call("M05", 17)])
    mk(tmp_path, F_VAR, "M05", 1, [(CUSTOM, {}, "total matches: 0\nno matches"), write_call("M05", 17)])
    cols = ec.collect(tmp_path, ec.PREFIXES_F)
    got = {(r["condition"], r["task"]): (r["search_lines"], r["total_matches"]) for r in rs.mechanism_rows(cols, TASKS)}
    assert got[("long", "M01")] == (50, None)
    assert got[("long", "M05")] == (0, None)
    assert got[("long_countline", "M05")] == (0, 0)


def test_failure_rows_list_order_diff_and_cause_agent_mistake_when_tool_output_was_right(tmp_path):
    fill_f(tmp_path, ctl_fail={("M01", 2)}, var_fail={("M07", 1)})
    cols = ec.collect(tmp_path, ec.PREFIXES_F)
    rows = {(r["condition"], r["task"], r["run"]): r for r in rs.failure_rows(cols, TASKS)}
    assert len(rows) == 2
    r = rows[("long", "M01", 2)]
    assert r["order"] == ["search_text", "Grep", "Write"] and (r["agent_value"], r["expected"], r["diff"]) == (25, 23, 2)
    assert r["cause"].startswith("에이전트 실수")
    v = rows[("long_countline", "M07", 1)]
    assert v["order"] == ["search_text", "Grep", "Write"] or v["order"] == ["Grep", "Write"]
    assert v["cause"].startswith("에이전트 실수")


def test_failure_cause_is_unclassified_when_no_tool_gave_the_right_count(tmp_path):
    mk(tmp_path, F_CTL, "M01", 1, [grep_content("M01", 21), write_call("M01", 21)], passed=False)
    cols = ec.collect(tmp_path, ec.PREFIXES_F)
    (row,) = rs.failure_rows(cols, TASKS)
    assert "확인 불가" in row["cause"] and not row["cause"].startswith("에이전트 실수")


def test_failure_rows_cover_all_failures_even_without_search_text(tmp_path):
    mk(tmp_path, F_VAR, "M07", 1, [grep_content("M07", 14), write_call("M07", 13)], passed=False)
    cols = ec.collect(tmp_path, ec.PREFIXES_F)
    assert [(r["task"], r["agent_value"]) for r in rs.failure_rows(cols, TASKS)] == [("M07", 13)]


# ---------------- H01 네 조건 ----------------

H01 = {"default": "baseline_haiku_default", "long": "expA_haiku_long", "long_filename": "expE_haiku_longFilename", "expEctl": "expEctl_haiku_long"}


def _h01(d, pre, run, lines, passed):
    path = f"C:\\Users\\{USER_NAME}\\Temp\\top_words.out"
    mk(d, pre, "H01", run, [("mcp__t__file_stats", {"path": "app_07.log"}, "lines=1 words=2675 bytes=1"),
                            ("Write", {"file_path": path, "content": "\n".join(lines) + "\n"}, "ok")], passed=passed)


RIGHT = ["app_07.log: 2675", "app_03.log: 2493", "app_05.log: 2306"]
PAIR = ["app_08.log: 2675", "app_03.log: 2493", "app_05.log: 2306"]
OTHER = ["app_09.log: 2270", "app_03.log: 2493", "app_05.log: 2306"]


def test_h01_four_condition_table_and_pair_error_detection(tmp_path):
    for r in (1, 2, 3):
        _h01(tmp_path, H01["default"], r, RIGHT, True)
        _h01(tmp_path, H01["long"], r, PAIR, False)
        _h01(tmp_path, H01["long_filename"], r, RIGHT, True)
    _h01(tmp_path, H01["expEctl"], 1, PAIR, False)
    _h01(tmp_path, H01["expEctl"], 2, OTHER, False)
    _h01(tmp_path, H01["expEctl"], 3, RIGHT, True)
    res = rs.h01_rows(tmp_path, TASKS)
    assert [(r["condition"], r["passed"], r["n"], r["pair_errors"]) for r in res] == [
        ("default", 3, 3, 0), ("long", 0, 3, 3), ("long_filename", 3, 3, 0), ("expEctl", 1, 3, 1)]
    md = NL.join(rs.render_h01(res))
    assert "| default | 3/3 |" in md and "| expEctl | 1/3 |" in md


def test_h01_missing_condition_is_na(tmp_path):
    _h01(tmp_path, H01["default"], 1, RIGHT, True)
    res = rs.h01_rows(tmp_path, TASKS)
    assert [r["n"] for r in res] == [1, 0, 0, 0]
    assert "n/a" in NL.join(rs.render_h01(res))


# ---------------- 실험 D 과제별 비용 비율 ----------------

def test_cost_ratio_per_task_sonnet_over_haiku(tmp_path):
    for t, h, s in (("E01", 0.001, 0.010), ("M01", 0.002, 0.030)):
        mk(tmp_path, ec.PREFIXES_D["haiku"], t, 1, [grep_count(t, 4)], cost=h)
        mk(tmp_path, ec.PREFIXES_D["sonnet"], t, 1, [grep_count(t, 4)], cost=s)
    mk(tmp_path, ec.PREFIXES_D["haiku"], "E02", 1, [grep_count("E01", 4)], cost=0.001)       # sonnet 쪽에 없는 과제는 제외
    cols = ec.collect(tmp_path, ec.PREFIXES_D)
    rows = rs.cost_ratio_rows(cols)
    assert [(r["task"], round(r["ratio"], 1)) for r in rows] == [("E01", 10.0), ("M01", 15.0)]
    md = NL.join(rs.render_cost_ratio(rows))
    assert "| E01 |" in md and "10.0" in md and "15.0" in md
    assert "중앙값" in md


def test_cost_ratio_with_no_common_pairs_is_empty_not_crashing(tmp_path):
    assert rs.cost_ratio_rows({"haiku": [], "sonnet": []}) == []
    assert "로그 없음" in NL.join(rs.render_cost_ratio([]))


# ---------------- 안전성 ----------------

def test_no_personal_paths_or_user_names_in_output(tmp_path):
    fill_all_experiments(tmp_path)
    fill_f(tmp_path, ctl_fail={("M01", 2)})
    for r in (1, 2, 3):
        _h01(tmp_path, H01["default"], r, RIGHT, True)
    text = rs.build(tmp_path, TASKS)
    assert USER_NAME not in text
    assert "C:\\" not in text and "AppData" not in text and "/Users/" not in text
    assert str(tmp_path) not in text


def test_read_only_and_main_writes_only_the_requested_file(tmp_path, capsys):
    raw = tmp_path / "raw"
    raw.mkdir()
    fill_f(raw)
    before = {p.name: p.read_bytes() for p in raw.iterdir()}
    out = tmp_path / "out" / "results.md"
    out.parent.mkdir()
    assert rs.main(["--raw-dir", str(raw), "--out", str(out)]) == 0
    assert out.read_text(encoding="utf-8").startswith("# ")
    assert {p.name: p.read_bytes() for p in raw.iterdir()} == before
    assert [p.name for p in out.parent.iterdir()] == ["results.md"]


def test_main_returns_1_when_there_are_no_logs(tmp_path):
    assert rs.main(["--raw-dir", str(tmp_path), "--out", str(tmp_path / "x.md")]) == 1
    assert not (tmp_path / "x.md").exists()


def test_module_does_not_import_anything_that_calls_the_model():
    src = Path(rs.__file__).read_text(encoding="utf-8")
    for bad in ("claude_agent_sdk", "runner_agent", "anthropic", "subprocess"):
        assert not re.search(rf"^\s*(import|from)\s+\S*{bad}", src, re.M), bad


def test_every_table_row_has_the_same_cell_count_as_its_header(tmp_path):
    fill_all_experiments(tmp_path)
    fill_f(tmp_path, ctl_fail={("M01", 2)}, var_fail={("M07", 1)})
    for r in (1, 2, 3):
        _h01(tmp_path, H01["default"], r, RIGHT, True)
    lines = rs.build(tmp_path, TASKS).splitlines()
    header = None
    for ln in lines:
        if ln.startswith("|"):
            n = len(ln.strip().strip("|").split("|"))
            if header is None:
                header = n
            assert n == header, ln
        else:
            header = None


# ---------------- README 링크 ----------------

ROOT = Path(__file__).resolve().parent.parent
FIGS = ["fig1_expA_selection.png", "fig2_expB_check_result.png", "fig3_expC_pass_vs_normal.png", "fig4_expD_cost_responses.png",
        "fig5_expEF_pass_by_task.png", "fig6_consistency.png"]


@pytest.mark.parametrize("name,heading", [("README.md", "## 주요 결과"), ("README.en.md", "## Key results")])
def test_readme_key_results_links_results_md_and_all_six_figures(name, heading):
    text = (ROOT / name).read_text(encoding="utf-8")
    assert heading in text
    sec = text[text.index(heading):]
    sec = sec[:sec.index("\n## ", 5)]
    assert "docs/results.md" in sec
    for f in FIGS:
        assert f"results/figures/{f}" in sec and (ROOT / "results" / "figures" / f).is_file(), f
    assert len(re.findall(r"N=\d+", sec)) >= 6                         # 주장마다 표본 크기가 붙는다
    assert "C:" + chr(92) not in sec and USER_NAME not in sec


def test_readme_f_claim_says_effect_not_confirmed_and_reach_5_of_20():
    ko = (ROOT / "README.md").read_text(encoding="utf-8")
    en = (ROOT / "README.en.md").read_text(encoding="utf-8")
    assert "효과를 확인하지 못함" in ko and "조건당 5/20" in ko
    assert "Effect not confirmed" in en and "5/20 per condition" in en


def test_failure_with_the_right_number_is_not_called_an_agent_miscount(tmp_path):
    mk(tmp_path, F_CTL, "M01", 1, [grep_count("M01", 23), write_call("M01", 23)], passed=False, failure_type="format_error")
    cols = ec.collect(tmp_path, ec.PREFIXES_F)
    (row,) = rs.failure_rows(cols, TASKS)
    assert row["agent_value"] == row["expected"] == 23 and row["diff"] == 0
    assert not row["cause"].startswith("에이전트 실수")


def test_agent_value_is_the_last_integer_of_the_last_write_to_the_output_file(tmp_path):
    calls = [("Write", {"file_path": "x/other.txt", "content": "줄 수: 1"}, "ok"),
             ("Write", {"file_path": "x/result.txt", "content": "dev-017 줄 수: 9"}, "ok"),
             ("Write", {"file_path": "x" + chr(92) + "result.txt", "content": "dev-017 줄 수: 23\n"}, "ok")]
    assert rs.agent_value(calls, TASKS["M01"]) == 23
    assert rs.agent_value([], TASKS["M01"]) is None


# ---------------- 실험 E: 주 비교(expEctl 대 expE)와 보조 비교(expA long) ----------------

E_PRE = {"ctl": "expEctl_haiku_long", "var": "expE_haiku_longFilename", "a_long": "expA_haiku_long"}
E_TIME = "expEctl과 expE는 2026-11-15에 2분 간격으로 연달아 실행, expA long은 2026-11-12 실행(3일 전)"


def fill_e(d):
    for r in (1, 2, 3):
        mk(d, E_PRE["a_long"], "H01", r, [], passed=False, ts="2026-11-12T03:30:00.000+00:00")
        mk(d, E_PRE["var"], "H01", r, [], passed=True, ts="2026-11-15T06:09:12.000+00:00")
        mk(d, E_PRE["ctl"], "H01", r, [], passed=(r == 3), ts="2026-11-15T06:11:30.000+00:00")
    for t in ("E03", "E10"):                                                    # expE와 expA long에만 있는 과제(보조 비교에만 들어간다)
        for r in (1, 2, 3):
            mk(d, E_PRE["a_long"], t, r, [], passed=True, ts="2026-11-12T03:30:00.000+00:00")
            mk(d, E_PRE["var"], t, r, [], passed=True, ts="2026-11-15T06:09:12.000+00:00")


def _section_text(text, e):
    nxt = {"A": "B", "B": "C", "C": "D", "D": "E", "E": "F"}.get(e)
    a = text.index(f"## 실험 {e}")
    return text[a:text.index(f"## 실험 {nxt}", a) if nxt and f"## 실험 {nxt}" in text else len(text)]


def test_e_core_table_is_expEctl_vs_expE_with_h01_only_and_time_note(tmp_path):
    fill_e(tmp_path)
    sec = _section_text(rs.build(tmp_path, TASKS), "E")
    core = sec[sec.index("### 핵심 지표"):sec.index("### 해석")]
    first_table = core[:core.index("**")] if "**" in core else core
    assert "| 지표 | expEctl | long_filename | 표본 |" in first_table
    assert "33% (1/3)" in first_table and "100% (3/3)" in first_table
    assert "N=1, 과제당 3회" in first_table and "총 3건" in first_table
    assert E_TIME in sec
    assert "H01 한 과제" in sec


def test_e_expA_long_comparison_is_demoted_to_an_auxiliary_table(tmp_path):
    fill_e(tmp_path)
    sec = _section_text(rs.build(tmp_path, TASKS), "E")
    core = sec[sec.index("### 핵심 지표"):sec.index("### 해석")]
    assert "**보조: expA long vs expE" in core
    aux = core[core.index("**보조: expA long vs expE"):]
    assert "| 지표 | long | long_filename | 표본 |" in aux
    assert core.index("| 지표 | expEctl | long_filename | 표본 |") < core.index("**보조: expA long vs expE")
    assert "67% (6/9)" in aux                                   # expA long H01 0/3 + E03 3/3 + E10 3/3 = 6/9


def test_e_section_limits_name_the_same_day_control_and_the_time_gap(tmp_path):
    fill_e(tmp_path)
    sec = _section_text(rs.build(tmp_path, TASKS), "E")
    lim = sec[sec.index("### 한계"):]
    assert "H01 한 과제" in lim and "3회" in lim and "30건 미만" in lim
    assert "3일" in lim or "다른 시기" in lim


# ---------------- 실험 C: 제한에 걸렸지만 통과한 실행의 쓰기 시점 ----------------

C_PRE = ec.PREFIXES_C
CHECK = "mcp__t__check_result"


def fill_cut(d):
    mt = dict(subtype="error_max_turns", final=False)
    # max_turns 3: 쓰기 직후 1, 쓰기 뒤 check_result 1, H05 Edit 뒤 Grep 1, 쓰기 기록 없음 2(하나는 쓰기가 오류 결과), 걸렸지만 실패 1, 정상 종료 1
    mk(d, C_PRE["3"], "E01", 1, [("Grep", {}, "x"), write_call("E01", 4)], **mt)
    mk(d, C_PRE["3"], "E01", 2, [("Grep", {}, "x"), write_call("E01", 4), (CHECK, {}, "ok")], **mt)
    mk(d, C_PRE["3"], "H05", 1, [("Glob", {}, "x"), ("Edit", {"file_path": "a"}, "ok"), ("Edit", {"file_path": "b"}, "ok"), ("Grep", {}, "x")], **mt)
    mk(d, C_PRE["3"], "E02", 1, [("Grep", {}, "x")], **mt)
    mk(d, C_PRE["3"], "E02", 2, [("Grep", {}, "x"), write_call("E01", 4)], err=(1,), **mt)
    mk(d, C_PRE["3"], "E03", 1, [("Grep", {}, "x")], passed=False, **mt)
    mk(d, C_PRE["3"], "E03", 2, [("Grep", {}, "x"), write_call("E01", 4)])
    mk(d, C_PRE["4"], "E01", 1, [write_call("E01", 4)], **mt)
    mk(d, C_PRE["5"], "E01", 1, [write_call("E01", 4)])
    mk(d, C_PRE["7"], "E01", 1, [write_call("E01", 4)])


def test_cut_pass_stats_classify_each_cut_but_passed_run_by_write_timing(tmp_path):
    fill_cut(tmp_path)
    s = rs.cut_pass_stats(tmp_path)
    assert list(s) == ["3", "4", "5", "7"]
    s3 = s["3"]
    assert (s3["cut"], s3["cut_pass"], s3["write_before_cut"], s3["no_write"]) == (6, 5, 3, 2)
    assert (s3["right_after_write"], s3["after_write"]) == (1, 2)
    assert s3["after_names"] == {CHECK: 1, "Grep": 1}
    assert s3["after_tasks"]["Grep"] == {"H05"} and s3["after_tasks"][CHECK] == {"E01"}
    s4 = s["4"]
    assert (s4["cut"], s4["cut_pass"], s4["write_before_cut"], s4["no_write"], s4["right_after_write"], s4["after_write"]) == (1, 1, 1, 0, 1, 0)
    for k in ("5", "7"):
        assert (s[k]["cut"], s[k]["cut_pass"], s[k]["write_before_cut"], s[k]["no_write"]) == (0, 0, 0, 0)


def test_failed_write_result_does_not_count_as_a_write(tmp_path):
    mk(tmp_path, C_PRE["3"], "E02", 2, [("Grep", {}, "x"), write_call("E01", 4)], err=(1,), subtype="error_max_turns", final=False)
    s = rs.cut_pass_stats(tmp_path)["3"]
    assert (s["cut_pass"], s["write_before_cut"], s["no_write"]) == (1, 0, 1)


def test_cut_pass_stats_with_no_logs_is_all_zero_not_crashing(tmp_path):
    s = rs.cut_pass_stats(tmp_path)
    assert all(v["cut"] == 0 and v["cut_pass"] == 0 and v["no_write"] == 0 for v in s.values())
    obs, hyp = rs.render_cut_summary(s)
    assert "없음" in obs and "직접 증거" in hyp


def _stats(total_by, right_by, after_by, names=None, tasks=None, no_write=0):
    out = {}
    for k in ("3", "4", "5", "7"):
        t, r, a = total_by.get(k, 0), right_by.get(k, 0), after_by.get(k, 0)
        out[k] = {"cut": t, "cut_pass": t, "write_before_cut": r + a, "no_write": no_write if k == "3" else 0,
                  "right_after_write": r, "after_write": a, "max_after": 1 if a else 0,
                  "after_names": dict(names or {}) if k == "3" else {}, "after_tasks": dict(tasks or {}) if k == "3" else {}}
    return out


def test_summary_sentence_has_all_counts_and_the_not_evidence_hypothesis():
    s = _stats({"3": 71, "4": 29, "5": 8}, {"3": 44, "4": 3, "5": 1}, {"3": 27, "4": 26, "5": 7}, names={CHECK: 3, "Grep": 1}, tasks={"Grep": {"H05"}, CHECK: {"E01"}})
    s["3"]["write_before_cut"], s["4"]["write_before_cut"], s["5"]["write_before_cut"] = 71, 29, 8
    obs, hyp = rs.render_cut_summary(s)
    assert obs.startswith("error_max_turns인데 통과한 108건(max_turns 3: 71, 4: 29, 5: 8)은 모두 결과 파일 쓰기가 성공한 뒤에 잘렸다.")
    assert "쓰기 직후에 잘린 것은 48건(44, 3, 1)이고" in obs
    assert "60건(27, 26, 7)은 쓰기 뒤에 도구가 한 번 더 호출됐다" in obs
    assert "check_result 3건" in obs and "Grep 1건" in obs and "H05" in obs
    assert hyp == "마무리 응답에서 잘렸다는 직접 증거는 없다(가설)."


def test_summary_sentence_does_not_say_all_when_there_are_exceptions():
    s = _stats({"3": 5, "4": 1}, {"3": 1, "4": 1}, {"3": 2}, names={CHECK: 2}, tasks={CHECK: {"E01"}}, no_write=2)
    obs, _ = rs.render_cut_summary(s)
    assert "모두 결과 파일 쓰기가 성공한 뒤에 잘렸다" not in obs
    assert "쓰기 성공 기록이 없다" in obs and "2건" in obs
    assert "(max_turns 3: 5, 4: 1)" in obs                                           # 걸린 설정만 적는다(5, 7은 0건이라 뺀다)


def test_section_c_uses_the_generated_sentence_and_drops_the_old_causal_claim(tmp_path):
    fill_all_experiments(tmp_path)
    fill_cut(tmp_path)
    sec = _section_text(rs.build(tmp_path, TASKS), "C")
    assert "- 관찰: error_max_turns인데 통과한 6건(max_turns 3: 5, 4: 1)" in sec
    assert "- 가설: 마무리 응답에서 잘렸다는 직접 증거는 없다(가설)." in sec
    assert "써 두기 때문이다" not in sec
    table = sec[sec.index("**제한에 걸렸지만 통과한 실행의 쓰기 시점"):]
    row3 = next(ln for ln in table.splitlines() if ln.startswith("| 3 |"))
    assert [c.strip() for c in row3.strip().strip("|").split("|")] == ["3", "6", "5", "3", "1", "2", "2"]


def test_cut_table_rows_have_the_same_cell_count_as_header(tmp_path):
    fill_all_experiments(tmp_path)
    fill_cut(tmp_path)
    sec = _section_text(rs.build(tmp_path, TASKS), "C")
    table = sec[sec.index("**제한에 걸렸지만 통과한 실행의 쓰기 시점"):]
    rows = [ln for ln in table.splitlines() if ln.startswith("|")]
    assert len(rows) == 2 + 4 and len({len(r.strip().strip("|").split("|")) for r in rows}) == 1


# ---------------- 문서 표현 정정(마무리 응답에서 잘렸다는 단정 제거) ----------------

KO_DOCS = ["README.md", "docs/sdk_notes.md", "docs/failure_analysis.md"]
CUT_KO = ("error_max_turns인데 통과한 108건(max_turns 3: 71, 4: 29, 5: 8)은 모두 결과 파일 쓰기가 성공한 뒤에 잘렸다. "
          "쓰기 직후에 잘린 것은 48건(44, 3, 1)이고, 60건(27, 26, 7)은 쓰기 뒤에 도구가 한 번 더 호출됐다(대부분 check_result, H05는 Edit 뒤 Grep). "
          "마무리 응답에서 잘렸다는 직접 증거는 없다(가설).")
CUT_EN = ("Of the 108 runs that ended with error_max_turns yet passed (max_turns 3: 71, 4: 29, 5: 8), all were cut off after the result-file write had succeeded. "
          "48 (44, 3, 1) were cut right after the write; in 60 (27, 26, 7) one more tool call followed the write (mostly check_result; Grep after an Edit for H05). "
          "There is no direct evidence that the cut happened in the wrap-up response (hypothesis).")


@pytest.mark.parametrize("name", KO_DOCS)
def test_korean_docs_carry_the_corrected_cut_sentence(name):
    text = (ROOT / name).read_text(encoding="utf-8")
    assert CUT_KO in text.replace("\r\n", "\n"), name


def test_english_readme_carries_the_corrected_cut_sentence():
    assert CUT_EN in (ROOT / "README.en.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("name", KO_DOCS + ["README.en.md", "docs/results.md"])
def test_no_doc_states_the_wrapup_cut_as_fact(name):
    for ln in (ROOT / name).read_text(encoding="utf-8").splitlines():
        if "마무리 응답" in ln or "wrap-up" in ln.lower():
            assert "직접 증거" in ln or "direct evidence" in ln, (name, ln[:160])
        assert "쓴 뒤였다" not in ln and "had already written" not in ln and "써 두기 때문이다" not in ln, (name, ln[:160])


def _real_c_logs():
    raw = ROOT / "results" / "raw"
    return raw if any(raw.glob("expC_haiku_maxTurns3_*_run1.jsonl")) else None


def test_corrected_numbers_match_the_real_logs_when_present():
    raw = _real_c_logs()
    if raw is None:
        pytest.skip("results/raw의 실험 C 로그가 없다(gitignore 대상)")
    s = rs.cut_pass_stats(raw)
    assert [s[k]["cut_pass"] for k in ("3", "4", "5")] == [71, 29, 8]
    assert all(s[k]["no_write"] == 0 for k in s)
    assert [s[k]["right_after_write"] for k in ("3", "4", "5")] == [44, 3, 1]
    assert [s[k]["after_write"] for k in ("3", "4", "5")] == [27, 26, 7]
    names = {}
    for k in s:
        for n, c in s[k]["after_names"].items():
            names[n.split("__")[-1]] = names.get(n.split("__")[-1], 0) + c
    assert max(names, key=names.get) == "check_result" and names.get("Grep") == 2
    assert {t for k in s for t in s[k]["after_tasks"].get("Grep", set())} == {"H05"}
