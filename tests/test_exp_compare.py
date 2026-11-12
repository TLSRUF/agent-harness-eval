"""exp_compare 테스트 (구현보다 먼저 작성). 출력 형식과 계산을 여기서 고정한다. 모델 호출 없음, 읽기 전용.

설정 4개(default=baseline, short, long, long_directive)를 열로 놓는 비교표와 정보 효과/지시 효과/우연 범위 판정.
"""
import csv
import json
import re
from pathlib import Path

import pytest

from src.eval import exp_compare as ec
from src.eval import loader, report

TASKS = {t.id: t for t in loader.load_all() if not t.is_todo}
SEARCH = sorted(t.id for t in TASKS.values() if "search_text|Grep" in t.overlap_with)
FILE = sorted(t.id for t in TASKS.values() if "file_stats|Read" in t.overlap_with)
OTHER = sorted(t.id for t in TASKS.values() if not t.overlap_with)
COLS = ["default", "short", "long", "long_directive"]
PREFIX = {"default": "baseline_haiku_default", "short": "expA_haiku_short", "long": "expA_haiku_long",
          "long_directive": "expA_haiku_longDirective"}
S_CUSTOM, S_BUILTIN = "mcp__t__search_text", "Grep"
F_CUSTOM, F_BUILTIN = "mcp__t__file_stats", "Read"
CHECK = "mcp__t__check_result"


def make(d: Path, col, task, run, rounds=(), *, passed=True, subtype="success", cost=0.01, usage=(10, 100, 1000), ts=None, suffix=".jsonl"):
    """rounds: 응답 하나당 [도구 이름 또는 (이름, 입력 dict)] 목록. usage = (input, cache_creation, cache_read)."""
    rows = [{"kind": "config", "task_id": task, "config": {"model": "claude-haiku-5-5", "max_turns": 20, "tool_desc_version": col}},
            {"kind": "message", "message": {"_type": "SystemMessage", "subtype": "init", "data": {"cwd": "C:/x", "tools": []}}}]
    n = 0
    for i, names in enumerate(rounds):
        for item in names:
            name, inp = item if isinstance(item, tuple) else (item, {})
            rows.append({"kind": "message", "message": {"_type": "AssistantMessage", "message_id": f"msg_{i}",
                                                        "content": [{"_type": "ToolUseBlock", "id": f"tu{n}", "name": name, "input": inp}]}})
            n += 1
    rows.append({"kind": "message", "message": {"_type": "AssistantMessage", "message_id": "msg_final",
                                                "content": [{"_type": "TextBlock", "text": "done"}]}})
    summ = {"kind": "summary", "subtype": subtype, "is_error": subtype != "success", "num_turns": n + 1, "total_cost_usd": cost,
            "usage": {"input_tokens": usage[0], "cache_creation_input_tokens": usage[1], "cache_read_input_tokens": usage[2]},
            "exception": None, "graded": {"passed": passed, "failure_type": "pass" if passed else "wrong_value"}}
    if ts:
        summ["ts"] = ts
    rows.append(summ)
    p = d / f"{PREFIX[col]}_{task}_run{run}{suffix}"
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return p


def fill_all(d, col, **kw):
    for t in TASKS:
        for r in (1, 2, 3):
            make(d, col, t, r, **kw)


def cells(text, label):
    sec1 = text[text.index(ec.SECTION_TITLES[0]):text.index(ec.SECTION_TITLES[1])]      # 1절의 행만 (3, 4절에도 같은 이름의 행이 있다)
    lines = [ln for ln in sec1.splitlines() if ln.startswith(f"| {label}")]
    assert len(lines) == 1, (label, lines)
    return [c.strip() for c in lines[0].strip().strip("|").split("|")]


def build(d):
    return ec.build_from_dir(d)


# ---------------- 형식 고정 ----------------

def test_columns_headings_and_row_labels_are_fixed(tmp_path):
    for c in COLS:
        fill_all(tmp_path, c)
    text = build(tmp_path)
    assert ec.COLUMNS == COLS
    assert text.startswith("# 실험 A 비교표 (exp_compare)\n")
    heads = ["## 1. 설정 4개 비교", "## 2. 과제별 선택률 (과제 x 설정, 3회 중 커스텀 도구를 쓴 횟수)",
             "## 3. 반복별 선택률과 우연 범위", "## 4. 정보 효과와 지시 효과 (선택률 차이, 퍼센트 포인트)", "## 5. 한도와 배치별 비용"]
    assert ec.SECTION_TITLES == heads
    pos = [text.index(h) for h in heads]
    assert pos == sorted(pos)
    assert "| 지표 | default | short | long | long_directive | 표본 |" in text
    for label in ["성공률", "error_max_turns 건수", "search_text 선택률", "Grep 사용률", "file_stats 선택률", "Read 사용률",
                  "check_result 사용률", "평균 num_turns", "평균 모델 응답 수", "평균 도구 호출 수", "실행당 평균 비용", "실행당 평균 입력 토큰",
                  "일관성 (a) 도구 순서", "일관성 (b) 핵심 인자"]:
        sec1 = text[text.index(heads[0]):text.index(heads[1])]
        assert len([ln for ln in sec1.splitlines() if ln.startswith(f"| {label}")]) == 1, label


def test_every_row_carries_sample_size_n_m_and_total(tmp_path):
    for c in COLS:
        fill_all(tmp_path, c)
    text = build(tmp_path)
    sec = text[text.index(ec.SECTION_TITLES[0]):text.index(ec.SECTION_TITLES[1])]
    rows = [ln for ln in sec.splitlines() if ln.startswith("| ") and not ln.startswith("| 지표") and not ln.startswith("|---")]
    assert len(rows) == 14
    for ln in rows:
        assert re.search(r"N=\d+, 과제당 [\d~]+회.*총 \d+건", ln), ln


def test_sample_sizes_by_row(tmp_path):
    for c in COLS:
        fill_all(tmp_path, c)
    text = build(tmp_path)
    assert f"N={len(SEARCH)}, 과제당 3회 / 총 {3 * len(SEARCH)}건" in cells(text, "search_text 선택률")[-1]
    assert f"N={len(FILE)}, 과제당 3회 / 총 {3 * len(FILE)}건" in cells(text, "file_stats 선택률")[-1]
    assert f"N={len(TASKS)}, 과제당 3회 / 총 {3 * len(TASKS)}건" in cells(text, "check_result 사용률")[-1]
    assert f"N={len(TASKS)}, 과제당 3회 / 총 {3 * len(TASKS)}건" in cells(text, "성공률")[-1]


def test_warning_added_only_when_fewer_than_30_runs(tmp_path):
    for c in COLS:
        fill_all(tmp_path, c)
    text = build(tmp_path)
    warn = report.SMALL_SAMPLE_WARNING
    assert 3 * len(FILE) < 30 and 3 * len(SEARCH) >= 30
    assert warn in cells(text, "file_stats 선택률")[-1] and warn in cells(text, "Read 사용률")[-1]
    assert warn not in cells(text, "search_text 선택률")[-1]
    assert warn not in cells(text, "성공률")[-1]


# ---------------- 1. 성공률, error_max_turns ----------------

def test_success_and_error_max_turns(tmp_path):
    for c in COLS:
        fill_all(tmp_path, c)
    make(tmp_path, "short", OTHER[0], 1, passed=False)                                    # 짧음: 실패 1
    make(tmp_path, "short", OTHER[1], 1, passed=False, subtype="error_max_turns")         # 실패 + max_turns
    make(tmp_path, "short", OTHER[2], 1, passed=True, subtype="error_max_turns")          # max_turns인데 통과
    text = build(tmp_path)
    total = 3 * len(TASKS)
    assert cells(text, "성공률")[1] == f"100% ({total}/{total})"
    assert cells(text, "성공률")[2] == f"98% ({total - 2}/{total})"
    mt = cells(text, "error_max_turns 건수")
    assert mt[1] == f"0 (통과 0)" and mt[2] == "2 (통과 1)"


# ---------------- 2~4. 선택률과 사용률 ----------------

def _fill_pair(d, col, tasks, custom, builtin, used_custom_runs, also_builtin=()):
    """tasks의 각 과제를 3회 실행. used_custom_runs: (과제, run) 중 커스텀 사용. also_builtin: 내장도 쓴 (과제, run)."""
    for t in tasks:
        for r in (1, 2, 3):
            uc = (t, r) in used_custom_runs
            names = [[custom]] if uc else [[builtin]]
            if (t, r) in also_builtin:
                names.append([builtin])
            make(d, col, t, r, names)


def test_search_text_selection_and_grep_usage_only_over_search_pair_tasks(tmp_path):
    for c in COLS:
        fill_all(tmp_path, c)
    # long: 검색 쌍 과제 12개 x 3회 중 9건에서 search_text 사용, 그중 3건은 Grep도 사용
    used = {(t, r) for t in SEARCH[:3] for r in (1, 2, 3)}
    both = {(SEARCH[0], 1), (SEARCH[1], 1), (SEARCH[2], 1)}
    _fill_pair(tmp_path, "long", SEARCH, S_CUSTOM, S_BUILTIN, used, both)
    # 쌍이 아닌 과제에서 search_text를 써도 선택률에 들어가지 않는다
    make(tmp_path, "long", OTHER[0], 1, [[S_CUSTOM]])
    text = build(tmp_path)
    n = 3 * len(SEARCH)
    assert cells(text, "search_text 선택률")[3] == f"25% (9/{n})"
    assert cells(text, "Grep 사용률")[3] == f"{100 * (n - 9 + 3) / n:.0f}% ({n - 9 + 3}/{n})"
    assert cells(text, "search_text 선택률")[1] == f"0% (0/{n})"          # 다른 설정은 영향 없음


def test_file_stats_selection_and_read_usage_and_check_result_over_all_tasks(tmp_path):
    for c in COLS:
        fill_all(tmp_path, c)
    used = {(FILE[0], 1), (FILE[0], 2), (FILE[1], 3)}
    _fill_pair(tmp_path, "short", FILE, F_CUSTOM, F_BUILTIN, used)
    make(tmp_path, "short", OTHER[0], 1, [[CHECK]])
    make(tmp_path, "short", FILE[2], 1, [[F_BUILTIN], [CHECK]])
    text = build(tmp_path)
    n = 3 * len(FILE)
    assert cells(text, "file_stats 선택률")[2] == f"{100 * 3 / n:.0f}% (3/{n})"
    assert cells(text, "Read 사용률")[2] == f"{100 * (n - 3) / n:.0f}% ({n - 3}/{n})"
    total = 3 * len(TASKS)
    assert cells(text, "check_result 사용률")[2] == f"{100 * 2 / total:.0f}% (2/{total})"


# ---------------- 5~6. 평균 ----------------

def test_means_for_turns_responses_tool_calls_cost_and_input_tokens(tmp_path):
    make(tmp_path, "long", OTHER[0], 1, [[S_CUSTOM], [F_CUSTOM]], cost=0.02, usage=(10, 100, 1000))        # 호출 2, 응답 3, num_turns 3
    make(tmp_path, "long", OTHER[0], 2, [[S_CUSTOM, F_CUSTOM, CHECK]], cost=0.04, usage=(20, 200, 2000))   # 호출 3, 응답 2, num_turns 4
    text = build(tmp_path)
    assert cells(text, "평균 num_turns")[3] == "3.5"
    assert cells(text, "평균 모델 응답 수")[3] == "2.5"
    assert cells(text, "평균 도구 호출 수")[3] == "2.5"
    assert cells(text, "실행당 평균 비용")[3] == "$0.0300"
    assert cells(text, "실행당 평균 입력 토큰")[3] == f"{(1110 + 2220) / 2:.0f}"       # input + cache_creation + cache_read 합계


def test_missing_config_shows_na_without_crashing(tmp_path):
    fill_all(tmp_path, "default")
    text = build(tmp_path)
    assert cells(text, "성공률")[2] == "n/a" and cells(text, "평균 num_turns")[4] == "n/a"
    assert "N=0" in cells(text, "성공률")[-1] or "default" in cells(text, "성공률")[-1]


# ---------------- 7. 일관성 ----------------

def test_consistency_matches_report_py_and_counts_pairs(tmp_path):
    for c in COLS:
        fill_all(tmp_path, c)
    t = OTHER[0]
    make(tmp_path, "long", t, 1, [[(S_CUSTOM, {"query": "a"})], [(CHECK, {"path": "x"})]])
    make(tmp_path, "long", t, 2, [[(S_CUSTOM, {"query": "b"})], [(CHECK, {"path": "x"})]])      # 이름 순서 같음, 핵심 인자 다름
    make(tmp_path, "long", t, 3, [[(F_CUSTOM, {"path": "x"})]])                                   # 이름 순서도 다름
    text = build(tmp_path)
    from src.eval import baseline_report as br
    runs = [br.load_item(p).run for p in sorted(tmp_path.glob(f"{PREFIX['long']}_*_run*.jsonl"))]
    line = report.consistency_line(runs)
    a, b = re.search(r"\(a\)[^0-9]*(\d+)%", line).group(1), re.search(r"\(b\)[^0-9]*(\d+)%", line).group(1)
    assert cells(text, "일관성 (a) 도구 순서")[3].startswith(f"{a}%")
    assert cells(text, "일관성 (b) 핵심 인자")[3].startswith(f"{b}%")
    assert "쌍" in cells(text, "일관성 (a) 도구 순서")[3]               # 비교한 쌍 수가 함께 보인다


# ---------------- 8. 과제별 ----------------

def test_per_task_table_counts_custom_use_out_of_three(tmp_path):
    for c in COLS:
        fill_all(tmp_path, c)
    for r in (1, 2):
        make(tmp_path, "short", SEARCH[0], r, [[S_CUSTOM]])
    make(tmp_path, "long", FILE[0], 3, [[F_CUSTOM]])
    for r in (1, 2, 3):
        make(tmp_path, "long_directive", SEARCH[1], r, [[S_CUSTOM]])
    text = build(tmp_path)
    sec = text[text.index(ec.SECTION_TITLES[1]):text.index(ec.SECTION_TITLES[2])]
    assert "| 과제 | 쌍 | default | short | long | long_directive |" in sec
    row = lambda t: [c.strip() for c in next(ln for ln in sec.splitlines() if ln.startswith(f"| {t} |")).strip().strip("|").split("|")]
    assert row(SEARCH[0])[1:] == ["search_text vs Grep", "0/3", "2/3", "0/3", "0/3"]
    assert row(FILE[0])[1:] == ["file_stats vs Read", "0/3", "0/3", "1/3", "0/3"]
    assert row(SEARCH[1])[5] == "3/3"
    assert OTHER[0] not in sec                                          # 쌍 과제만
    assert sec.count("\n| ") >= len(SEARCH) + len(FILE) + 1
    assert report.SMALL_SAMPLE_WARNING in sec                          # 셀 표본은 3회뿐이라 경고


# ---------------- 3~4. 반복별 선택률, 효과, 판정 ----------------

def test_repetition_rates_and_range(tmp_path):
    for c in COLS:
        fill_all(tmp_path, c)
    # long: run1에서만 검색 쌍 과제 12개 중 6개가 search_text, run2는 3개, run3은 0개
    for i, t in enumerate(SEARCH):
        make(tmp_path, "long", t, 1, [[S_CUSTOM]] if i < 6 else [[S_BUILTIN]])
        make(tmp_path, "long", t, 2, [[S_CUSTOM]] if i < 3 else [[S_BUILTIN]])
    text = build(tmp_path)
    sec = text[text.index(ec.SECTION_TITLES[2]):text.index(ec.SECTION_TITLES[3])]
    assert "| 지표 | 설정 | run1 | run2 | run3 | 범위(최대-최소, pp) | 표본 |" in sec
    n = len(SEARCH)
    line = next(ln for ln in sec.splitlines() if ln.startswith("| search_text 선택률 | long |"))
    c = [x.strip() for x in line.strip().strip("|").split("|")]
    assert c[2:5] == [f"50% (6/{n})", f"25% (3/{n})", "0% (0/12)".replace("12", str(n))]
    assert c[5] == "50.0"


def test_effects_info_and_directive_in_percentage_points(tmp_path):
    for c in COLS:
        fill_all(tmp_path, c)
    n = len(SEARCH)
    # default 0/12*3, long 12건 중 일부... 36건 중 9건(25%), long_directive 18건(50%)
    _fill_pair(tmp_path, "long", SEARCH, S_CUSTOM, S_BUILTIN, {(t, r) for t in SEARCH[:3] for r in (1, 2, 3)})
    _fill_pair(tmp_path, "long_directive", SEARCH, S_CUSTOM, S_BUILTIN, {(t, r) for t in SEARCH[:6] for r in (1, 2, 3)})
    text = build(tmp_path)
    sec = text[text.index(ec.SECTION_TITLES[3]):text.index(ec.SECTION_TITLES[4])]
    assert "| 지표 | 정보 효과(long - default) | 지시 효과(long_directive - long) | 우연 범위(pp) | 판정 |" in sec
    line = next(ln for ln in sec.splitlines() if ln.startswith("| search_text 선택률 |"))
    assert "+25.0pp" in line and "+25.0pp" in line.split("|")[3]
    assert "정보 효과" in sec and "지시 효과" in sec
    assert 3 * n >= 30


def test_judge_larger_smaller_and_undecidable():
    assert ec.judge(30.0, 10.0, 5.0, 3, 3).startswith("큼")
    assert ec.judge(-30.0, 10.0, 5.0, 3, 3).startswith("큼")           # 부호와 상관없이 크기로 비교
    assert ec.judge(5.0, 10.0, 5.0, 3, 3).startswith("작음")
    assert ec.judge(0.0, 0.0, 0.0, 3, 3).startswith("작음")
    assert ec.judge(10.0, 10.0, 5.0, 3, 3) == "확인 불가"              # 경계(같음)
    assert ec.judge(30.0, 10.0, 5.0, 1, 3) == "확인 불가"              # 반복이 2개 미만이라 범위를 못 구함
    assert ec.judge(None, 10.0, 5.0, 3, 3) == "확인 불가"              # 비교 대상 없음
    assert ec.judge(30.0, None, 5.0, 3, 3) == "확인 불가"


def test_judge_uses_larger_of_the_two_ranges_in_section_4(tmp_path):
    for c in COLS:
        fill_all(tmp_path, c)
    # default는 반복 간 차이 없음(0%), long은 run별 0%, 25%, 50% (범위 50pp), 평균 25%
    for i, t in enumerate(SEARCH):
        make(tmp_path, "long", t, 2, [[S_CUSTOM]] if i < 3 else [[S_BUILTIN]])
        make(tmp_path, "long", t, 3, [[S_CUSTOM]] if i < 6 else [[S_BUILTIN]])
    text = build(tmp_path)
    sec = text[text.index(ec.SECTION_TITLES[3]):text.index(ec.SECTION_TITLES[4])]
    line = next(ln for ln in sec.splitlines() if ln.startswith("| search_text 선택률 |"))
    # 정보 효과 +25pp, 두 설정 범위 중 큰 값 50pp -> 작음
    assert "+25.0pp" in line and "작음" in line


def test_effects_table_has_na_when_a_config_is_missing(tmp_path):
    fill_all(tmp_path, "default")
    text = build(tmp_path)
    sec = text[text.index(ec.SECTION_TITLES[3]):text.index(ec.SECTION_TITLES[4])]
    assert "n/a" in sec and "확인 불가" in sec


# ---------------- 로그 읽기 규칙 ----------------

def test_only_final_run_logs_are_read_and_long_vs_longdirective_are_not_mixed(tmp_path):
    fill_all(tmp_path, "long")
    fill_all(tmp_path, "long_directive")
    make(tmp_path, "long", OTHER[0], 1, suffix=".jsonl.partial1")
    (tmp_path / "expA_haiku_long_summary.jsonl").write_text("{}", encoding="utf-8")
    snap = tmp_path / "expA_haiku_long_E01_run1_final"
    snap.mkdir()
    (snap / "x.jsonl").write_text("{}", encoding="utf-8")
    cols = ec.collect(tmp_path)
    total = 3 * len(TASKS)
    assert len(cols["long"]) == total and len(cols["long_directive"]) == total and cols["default"] == [] and cols["short"] == []
    assert not any("longDirective" in r.item.run.path for r in cols["long"])


def test_baseline_default_only_matches_default_config(tmp_path):
    fill_all(tmp_path, "default")
    (tmp_path / "baseline_haiku_short_E01_run1.jsonl").write_text("{}", encoding="utf-8")
    (tmp_path / "day7check_haiku_default_E01_run1.jsonl").write_text("{}", encoding="utf-8")
    assert len(ec.collect(tmp_path)["default"]) == 3 * len(TASKS)


# ---------------- 5. 한도와 배치별 비용 ----------------

def _probe(d, name, which, five, seven, ts):
    rows = [{"kind": "config", "ts": ts, "task_id": "probe"}, {"kind": "summary", "ts": ts, "five_hour": five, "seven_day": seven}]
    (d / f"probe_haiku_{name}_inv1_{which}.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")


def test_limits_and_batch_costs_from_probes_and_run_timestamps(tmp_path):
    t0, t1 = "2026-11-12T03:00:00.000+00:00", "2026-11-12T03:30:00.000+00:00"
    _probe(tmp_path, "expA-short", "start", 0.30, 0.20, t0)
    _probe(tmp_path, "expA-short", "end", 0.34, 0.20, t1)
    make(tmp_path, "short", OTHER[0], 1, cost=0.10, ts="2026-11-12T03:10:00.000+00:00")
    make(tmp_path, "short", OTHER[1], 1, cost=0.20, ts="2026-11-12T03:20:00.000+00:00")
    make(tmp_path, "short", OTHER[2], 1, cost=0.50, ts="2026-11-12T05:00:00.000+00:00")     # 탐침 창 밖
    text = build(tmp_path)
    sec = text[text.index(ec.SECTION_TITLES[4]):]
    assert "| 설정 | 호출 | five_hour 시작 | five_hour 종료 | five_hour 델타 | seven_day 시작 | seven_day 종료 | 실행 수 | 비용 합계 |" in sec
    line = next(ln for ln in sec.splitlines() if ln.startswith("| short |"))
    assert "0.3" in line and "0.34" in line and "+0.04" in line and "| 2 | $0.3000 |" in line
    assert "탐침 창 밖 1건 $0.5000" in sec.replace("(", "").replace(")", "") or "창 밖" in sec


def test_missing_probe_is_reported_not_guessed(tmp_path):
    make(tmp_path, "long", OTHER[0], 1, cost=0.1, ts="2026-11-12T03:10:00.000+00:00")
    text = build(tmp_path)
    sec = text[text.index(ec.SECTION_TITLES[4]):]
    assert "탐침 없음" in sec


# ---------------- 파일 출력, 읽기 전용 ----------------

def test_main_writes_md_and_csv_and_does_not_touch_raw(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    for c in COLS:
        fill_all(raw, c)
    before = {p.name: p.read_bytes() for p in raw.iterdir()}
    out = tmp_path / "out"
    out.mkdir()
    rc = ec.main(["--raw-dir", str(raw), "--out-md", str(out / "cmp.md"), "--out-csv", str(out / "cmp.csv")])
    assert rc == 0
    assert {p.name: p.read_bytes() for p in raw.iterdir()} == before
    assert (out / "cmp.md").read_text(encoding="utf-8").startswith("# 실험 A 비교표")
    rows = list(csv.DictReader((out / "cmp.csv").open(encoding="utf-8")))
    assert set(rows[0]) == {"metric", "config", "task", "numerator", "denominator", "value", "sample"}
    got = {(r["metric"], r["config"]) for r in rows}
    assert ("search_text 선택률", "long") in got and ("성공률", "default") in got
    assert any(r["task"] == SEARCH[0] for r in rows)


def test_main_returns_1_when_no_logs(tmp_path):
    assert ec.main(["--raw-dir", str(tmp_path), "--out-md", str(tmp_path / "a.md"), "--out-csv", str(tmp_path / "a.csv")]) == 1


def test_module_does_not_import_anything_that_calls_the_model():
    src = (Path(__file__).resolve().parents[1] / "src" / "eval" / "exp_compare.py").read_text(encoding="utf-8")
    assert "runner_agent" not in src and "claude_agent_sdk" not in src and "ClaudeSDKClient" not in src


def test_every_markdown_table_row_has_the_same_cell_count_as_its_header(tmp_path):
    """표 칸 안에 | 가 들어가면 표가 깨진다(쌍 이름 search_text|Grep, 판정 문구의 |효과| 에서 실제로 발생했다)."""
    for c in COLS:
        fill_all(tmp_path, c)
    for r in range(1, 4):
        make(tmp_path, "long", SEARCH[0], r, [[S_CUSTOM]])
    _probe(tmp_path, "expA-long", "start", 0.3, 0.2, "2026-11-12T03:00:00.000+00:00")
    _probe(tmp_path, "expA-long", "end", 0.4, 0.2, "2026-11-12T03:30:00.000+00:00")
    text = build(tmp_path)
    width = None
    checked = 0
    for ln in text.splitlines():
        if not ln.startswith("|"):
            width = None
            continue
        n = len(ln.strip().strip("|").split("|"))
        if width is None:
            width = n
        assert n == width, ln
        checked += 1
    assert checked > 60
