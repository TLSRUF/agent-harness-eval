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


def make(d: Path, col, task, run, rounds=(), *, passed=True, subtype="success", cost=0.01, usage=(10, 100, 1000), ts=None, suffix=".jsonl",
         max_turns=20, final=True):
    """rounds: 응답 하나당 [도구 이름 또는 (이름, 입력 dict)] 목록. usage = (input, cache_creation, cache_read)."""
    rows = [{"kind": "config", "task_id": task, "config": {"model": "claude-haiku-5-5", "max_turns": max_turns, "tool_desc_version": col}},
            {"kind": "message", "message": {"_type": "SystemMessage", "subtype": "init", "data": {"cwd": "C:/x", "tools": []}}}]
    n = 0
    for i, names in enumerate(rounds):
        for item in names:
            name, inp = item if isinstance(item, tuple) else (item, {})
            rows.append({"kind": "message", "message": {"_type": "AssistantMessage", "message_id": f"msg_{i}",
                                                        "content": [{"_type": "ToolUseBlock", "id": f"tu{n}", "name": name, "input": inp}]}})
            n += 1
    if final:
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
             "## 3. 반복별 선택률과 우연 범위", "## 4. 정보 효과와 지시 효과 (선택률 차이, 퍼센트 포인트)", "## 5. 한도와 배치별 비용",
             "## 6. 견고성: 과제 단위 사용 과제 수와 선택 변화"]
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


# ---------------- 6. 견고성 ----------------

def _sec6(text):
    return text[text.index(ec.SECTION_TITLES[5]):]


def _setup_robust(tmp_path):
    for c in COLS:
        fill_all(tmp_path, c)
    # default: SEARCH[2]만 2/3 사용
    for r in (1, 2):
        make(tmp_path, "default", SEARCH[2], r, [[S_CUSTOM]])
    # long: SEARCH[0] 3/3, SEARCH[1] 1/3 (SEARCH[2]는 0/3으로 줄어듦), FILE[0] 3/3
    for r in (1, 2, 3):
        make(tmp_path, "long", SEARCH[0], r, [[S_CUSTOM]])
        make(tmp_path, "long", FILE[0], r, [[F_CUSTOM]])
    make(tmp_path, "long", SEARCH[1], 1, [[S_CUSTOM]])
    # long_directive: SEARCH[0] 3/3, SEARCH[2] 3/3, FILE[0] 3/3, FILE[1] 2/3
    for r in (1, 2, 3):
        make(tmp_path, "long_directive", SEARCH[0], r, [[S_CUSTOM]])
        make(tmp_path, "long_directive", SEARCH[2], r, [[S_CUSTOM]])
        make(tmp_path, "long_directive", FILE[0], r, [[F_CUSTOM]])
    for r in (1, 2):
        make(tmp_path, "long_directive", FILE[1], r, [[F_CUSTOM]])


def test_robustness_counts_tasks_that_used_the_custom_tool_at_least_once(tmp_path):
    _setup_robust(tmp_path)
    sec = _sec6(build(tmp_path))
    assert "| 지표 | default | short | long | long_directive | 표본 |" in sec
    ns, nf = len(SEARCH), len(FILE)
    row = lambda label: [c.strip() for c in next(ln for ln in sec.splitlines() if ln.startswith(f"| {label}")).strip().strip("|").split("|")]
    s = row("search_text 쌍 과제 중 한 번이라도 쓴 과제 수")
    assert s[1:5] == [f"1/{ns} (3회 모두 0)", f"0/{ns} (3회 모두 0)", f"2/{ns} (3회 모두 1)", f"2/{ns} (3회 모두 2)"]
    f = row("file_stats 쌍 과제 중 한 번이라도 쓴 과제 수")
    assert f[1:5] == [f"0/{nf} (3회 모두 0)", f"0/{nf} (3회 모두 0)", f"1/{nf} (3회 모두 1)", f"2/{nf} (3회 모두 1)"]
    assert f"N={ns}, 과제당 3회" in s[5] and f"N={nf}, 과제당 3회" in f[5]
    assert report.SMALL_SAMPLE_WARNING in s[5] and report.SMALL_SAMPLE_WARNING in f[5]     # 과제 수가 30 미만


def test_robustness_lists_tasks_with_more_and_less_custom_use_than_default(tmp_path):
    _setup_robust(tmp_path)
    sec = _sec6(build(tmp_path))
    line = lambda prefix: next(ln for ln in sec.splitlines() if ln.startswith(prefix))
    up = line("- long vs default 늘어난 과제")
    assert f"{SEARCH[0]}(0/3→3/3)" in up and f"{SEARCH[1]}(0/3→1/3)" in up and f"{FILE[0]}(0/3→3/3)" in up and "3개" in up
    down = line("- long vs default 줄어든 과제")
    assert f"{SEARCH[2]}(2/3→0/3)" in down and "1개" in down
    up2 = line("- long_directive vs default 늘어난 과제")
    assert f"{SEARCH[2]}(2/3→3/3)" in up2 and f"{FILE[1]}(0/3→2/3)" in up2
    assert line("- long_directive vs default 줄어든 과제").endswith("0개: 없음")
    assert "- long vs default 같은 과제" in sec                                            # 변화 없는 과제 수도 센다


def test_robustness_unchanged_count_and_per_task_noise_note(tmp_path):
    _setup_robust(tmp_path)
    sec = _sec6(build(tmp_path))
    total = len(SEARCH) + len(FILE)
    line = next(ln for ln in sec.splitlines() if ln.startswith("- long vs default 같은 과제"))
    assert f"{total - 4}개" in line                                                        # 늘어난 3 + 줄어든 1 = 4개가 아닌 나머지
    assert "한 과제 3회" in sec or "3회 중" in sec                                         # 칸 단위 표본이 3회임을 알린다


def test_robustness_with_missing_config_does_not_crash(tmp_path):
    fill_all(tmp_path, "default")
    sec = _sec6(build(tmp_path))
    assert "n/a" in sec


# ---------------- 실험 B 비교 (default, verify, verify_tool) ----------------

PREFIX_B = {"default": "baseline_haiku_default", "verify": "expB_haiku_verify", "verify_tool": "expB_haiku_verifyTool"}
COLS_B = ["default", "verify", "verify_tool"]


def make_b(d, col, task, run, rounds=(), **kw):
    PREFIX[col] = PREFIX_B[col]                       # make()가 쓰는 접두 표에 B 설정을 등록
    return make(d, col, task, run, rounds, **kw)


def fill_b(d, col, **kw):
    for t in TASKS:
        for r in (1, 2, 3):
            make_b(d, col, t, r, **kw)


def cells_b(text, label):
    sec = text[text.index(ec.SECTION_TITLES_B[0]):text.index(ec.SECTION_TITLES_B[1])]
    lines = [ln for ln in sec.splitlines() if ln.startswith(f"| {label}")]
    assert len(lines) == 1, (label, lines)
    return [c.strip() for c in lines[0].strip().strip("|").split("|")]


def test_b_columns_titles_rows_are_fixed(tmp_path):
    for c in COLS_B:
        fill_b(tmp_path, c)
    text = ec.build_from_dir_b(tmp_path)
    assert ec.COLUMNS_B == COLS_B
    assert text.startswith("# 실험 B 비교표 (exp_compare)\n")
    assert ec.SECTION_TITLES_B == ["## 1. 설정 3개 비교", "## 2. 한도와 배치별 비용"]
    assert "| 지표 | default | verify | verify_tool | 표본 |" in text
    sec = text[text.index(ec.SECTION_TITLES_B[0]):text.index(ec.SECTION_TITLES_B[1])]
    rows = [ln.split("|")[1].strip() for ln in sec.splitlines() if ln.startswith("| ") and not ln.startswith("| 지표")]
    assert rows == ["성공률", "error_max_turns 건수", "check_result 사용률", "평균 num_turns", "평균 모델 응답 수", "평균 도구 호출 수",
                    "실행당 평균 비용", "일관성 (a) 도구 순서", "일관성 (b) 핵심 인자"]
    for ln in sec.splitlines():
        if ln.startswith("| ") and not ln.startswith("| 지표"):
            assert re.search(r"N=\d+, 과제당 [\d~]+회.*총 \d+건", ln), ln


def test_b_values_success_max_turns_check_result_means_and_consistency(tmp_path):
    for c in COLS_B:
        fill_b(tmp_path, c)
    make_b(tmp_path, "verify", OTHER[0], 1, [[CHECK], [CHECK]], passed=False, cost=0.03)
    make_b(tmp_path, "verify", OTHER[1], 1, [[CHECK]], subtype="error_max_turns", passed=True)
    for r in (1, 2, 3):
        make_b(tmp_path, "verify_tool", OTHER[2], r, [[(CHECK, {"path": "x"})]])
    text = ec.build_from_dir_b(tmp_path)
    total = 3 * len(TASKS)
    assert cells_b(text, "성공률")[1] == f"100% ({total}/{total})"
    assert cells_b(text, "성공률")[2] == f"99% ({total - 1}/{total})"
    assert cells_b(text, "error_max_turns 건수")[2] == "1 (통과 1)"
    assert cells_b(text, "check_result 사용률")[2] == f"{100 * 2 / total:.0f}% (2/{total})"
    assert cells_b(text, "check_result 사용률")[3] == f"{100 * 3 / total:.0f}% (3/{total})"
    assert cells_b(text, "평균 num_turns")[1] == "1.0"
    assert cells_b(text, "실행당 평균 비용")[2].startswith("$0.01")
    assert "쌍" in cells_b(text, "일관성 (a) 도구 순서")[1]


def test_b_warns_on_small_samples_and_missing_configs_are_na(tmp_path):
    for t in OTHER[:2]:
        for r in (1, 2, 3):
            make_b(tmp_path, "default", t, r)
            make_b(tmp_path, "verify", t, r)
    text = ec.build_from_dir_b(tmp_path)
    assert report.SMALL_SAMPLE_WARNING in cells_b(text, "성공률")[-1]
    assert cells_b(text, "성공률")[3] == "n/a"


def test_b_collect_does_not_mix_verify_with_verify_tool_or_other_experiments(tmp_path):
    fill_b(tmp_path, "verify")
    fill_b(tmp_path, "verify_tool")
    fill_all(tmp_path, "long")
    (tmp_path / "expB_haiku_verify_summary.jsonl").write_text("{}", encoding="utf-8")
    make_b(tmp_path, "verify", OTHER[0], 1, suffix=".jsonl.partial1")
    cols = ec.collect(tmp_path, ec.PREFIXES_B)
    total = 3 * len(TASKS)
    assert len(cols["verify"]) == total and len(cols["verify_tool"]) == total and cols["default"] == []
    assert not any("verifyTool" in r.item.run.path for r in cols["verify"])


def test_b_probes_use_expB_names(tmp_path):
    t0, t1 = "2026-11-12T03:00:00.000+00:00", "2026-11-12T03:30:00.000+00:00"
    _probe(tmp_path, "expB-verifyTool", "start", 0.40, 0.2, t0)
    _probe(tmp_path, "expB-verifyTool", "end", 0.45, 0.2, t1)
    make_b(tmp_path, "verify_tool", OTHER[0], 1, cost=0.1, ts="2026-11-12T03:10:00.000+00:00")
    text = ec.build_from_dir_b(tmp_path)
    line = next(ln for ln in text[text.index(ec.SECTION_TITLES_B[1]):].splitlines() if ln.startswith("| verify_tool |"))
    assert "+0.05" in line and "| 1 | $0.1000 |" in line


def test_main_exp_b_writes_files_and_refuses_when_no_b_logs(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    fill_all(raw, "default")                                   # baseline만 있다
    assert ec.main(["--exp", "B", "--raw-dir", str(raw), "--out-md", str(tmp_path / "b.md"), "--out-csv", str(tmp_path / "b.csv")]) == 1
    fill_b(raw, "verify")
    assert ec.main(["--exp", "B", "--raw-dir", str(raw), "--out-md", str(tmp_path / "b.md"), "--out-csv", str(tmp_path / "b.csv")]) == 0
    assert (tmp_path / "b.md").read_text(encoding="utf-8").startswith("# 실험 B 비교표")
    got = {(r["metric"], r["config"]) for r in csv.DictReader((tmp_path / "b.csv").open(encoding="utf-8"))}
    assert ("성공률", "verify") in got and ("check_result 사용률", "default") in got


def test_b_tables_have_consistent_cell_counts(tmp_path):
    for c in COLS_B:
        fill_b(tmp_path, c)
    text = ec.build_from_dir_b(tmp_path)
    width = None
    for ln in text.splitlines():
        if not ln.startswith("|"):
            width = None
            continue
        n = len(ln.strip().strip("|").split("|"))
        width = width or n
        assert n == width, ln


# ---------------- 실험 C: max_turns 비교 (default=20, 3, 4, 5, 7) ----------------

PREFIX.update({"3": "expC_haiku_maxTurns3", "4": "expC_haiku_maxTurns4", "5": "expC_haiku_maxTurns5", "7": "expC_haiku_maxTurns7"})
COLS_C = ["default", "3", "4", "5", "7"]


def fill_c(d, col, **kw):
    mt = 20 if col == "default" else int(col)
    for t in TASKS:
        for r in (1, 2, 3):
            make(d, col, t, r, max_turns=mt, **kw)


def cells_c(text, label):
    sec = text[text.index(ec.SECTION_TITLES_C[0]):text.index(ec.SECTION_TITLES_C[1])]
    lines = [ln for ln in sec.splitlines() if ln.startswith(f"| {label}")]
    assert len(lines) == 1, (label, lines)
    return [c.strip() for c in lines[0].strip().strip("|").split("|")]


def test_c_columns_titles_rows_are_fixed(tmp_path):
    for c in COLS_C:
        fill_c(tmp_path, c)
    text = ec.build_from_dir_c(tmp_path)
    assert ec.COLUMNS_C == COLS_C
    assert text.startswith("# 실험 C 비교표 (exp_compare)\n")
    assert ec.SECTION_TITLES_C == ["## 1. 설정 5개 비교", "## 2. 한계 판정: 설정 max_turns x 모델 응답 수", "## 3. 한도와 배치별 비용"]
    assert "| 지표 | default | 3 | 4 | 5 | 7 | 표본 |" in text
    sec = text[text.index(ec.SECTION_TITLES_C[0]):text.index(ec.SECTION_TITLES_C[1])]
    rows = [ln.split("|")[1].strip() for ln in sec.splitlines() if ln.startswith("| ") and not ln.startswith("| 지표")]
    assert rows == ["성공률", "error_max_turns 건수(비율)", "error_max_turns인데 채점 통과", "평균 모델 응답 수", "평균 num_turns", "실행당 평균 비용"]
    for ln in sec.splitlines():
        if ln.startswith("| ") and not ln.startswith("| 지표"):
            assert re.search(r"N=\d+, 과제당 [\d~]+회.*총 \d+건", ln), ln


def test_c_values_error_max_turns_rate_and_separate_pass_count_and_means(tmp_path):
    for c in COLS_C:
        fill_c(tmp_path, c)
    total = 3 * len(TASKS)
    # max_turns 3: 에러 3건(그중 1건은 채점 통과), 3건 중 응답 3개
    make(tmp_path, "3", OTHER[0], 1, [[CHECK], [CHECK], [CHECK]], subtype="error_max_turns", passed=False, final=False, max_turns=3)
    make(tmp_path, "3", OTHER[1], 1, [[CHECK], [CHECK], [CHECK]], subtype="error_max_turns", passed=True, final=False, max_turns=3)
    make(tmp_path, "3", OTHER[2], 1, [[CHECK], [CHECK], [CHECK]], subtype="error_max_turns", passed=False, final=False, max_turns=3)
    text = ec.build_from_dir_c(tmp_path)
    assert cells_c(text, "error_max_turns 건수(비율)")[1] == f"0 (0%, 0/{total})"
    assert cells_c(text, "error_max_turns 건수(비율)")[2] == f"3 ({100 * 3 / total:.0f}%, 3/{total})"
    assert cells_c(text, "error_max_turns인데 채점 통과")[2] == "1/3"                 # 통과한 error_max_turns / error_max_turns 건수
    assert cells_c(text, "error_max_turns인데 채점 통과")[1] == "0/0"
    assert cells_c(text, "성공률")[2] == f"{100 * (total - 2) / total:.0f}% ({total - 2}/{total})"   # 채점 통과 기준: 에러 중 통과 1건은 성공에 포함
    assert cells_c(text, "평균 num_turns")[1] == "1.0"
    assert cells_c(text, "평균 모델 응답 수")[1] == "1.0"
    assert cells_c(text, "실행당 평균 비용")[1] == "$0.0100"


def test_c_small_sample_warning_and_missing_columns(tmp_path):
    for t in OTHER[:2]:
        for r in (1, 2, 3):
            make(tmp_path, "default", t, r)
            make(tmp_path, "3", t, r, max_turns=3)
    text = ec.build_from_dir_c(tmp_path)
    assert report.SMALL_SAMPLE_WARNING in cells_c(text, "성공률")[-1]
    assert cells_c(text, "성공률")[3] == "n/a"


def _limit_rows(text):
    sec = text[text.index(ec.SECTION_TITLES_C[1]):text.index(ec.SECTION_TITLES_C[2])]
    assert "| 설정 max_turns | 모델 응답 수 | success | error_max_turns | 합계 |" in sec
    rows = {}
    for ln in sec.splitlines():
        c = [x.strip() for x in ln.strip().strip("|").split("|")]
        if ln.startswith("| ") and c[0].isdigit() and len(c) == 5:
            rows[(int(c[0]), int(c[1]))] = tuple(int(x) for x in c[2:])
    return sec, rows


def test_c_limit_table_groups_by_max_turns_and_response_count(tmp_path):
    # max_turns 3: success(응답 2), success(응답 3) x2, error(응답 3) x1
    make(tmp_path, "3", OTHER[0], 1, [[CHECK]], max_turns=3)
    make(tmp_path, "3", OTHER[0], 2, [[CHECK], [CHECK]], max_turns=3)
    make(tmp_path, "3", OTHER[0], 3, [[CHECK], [CHECK]], max_turns=3)
    make(tmp_path, "3", OTHER[1], 1, [[CHECK]] * 3, subtype="error_max_turns", passed=False, final=False, max_turns=3)
    # baseline(20): 응답 2, 4
    make(tmp_path, "default", OTHER[2], 1, [[CHECK]])
    make(tmp_path, "default", OTHER[2], 2, [[CHECK]] * 3)
    text = ec.build_from_dir_c(tmp_path)
    sec, rows = _limit_rows(text)
    assert rows == {(3, 2): (1, 0, 1), (3, 3): (2, 1, 3), (20, 2): (1, 0, 1), (20, 4): (1, 0, 1)}
    order = [k for k in re.findall(r"^\| (\d+) \| (\d+) \|", sec, re.M)]
    assert order == sorted(order, key=lambda x: (int(x[0]), int(x[1])))


def test_c_limit_verdict_supports_greater_than_rule_and_rejects_ge_when_success_at_equal(tmp_path):
    make(tmp_path, "3", OTHER[0], 1, [[CHECK]] * 2, max_turns=3)                            # success, 응답 3 == 설정값
    make(tmp_path, "3", OTHER[1], 1, [[CHECK]] * 3, subtype="error_max_turns", passed=False, final=False, max_turns=3)   # 에러, 응답 3
    text = ec.build_from_dir_c(tmp_path)
    line = next(ln for ln in text.splitlines() if ln.startswith("- max_turns 3:"))
    assert "지지" in line and "> max_turns" in line and "≥" in line and "기각" in line
    assert "한계에 걸린 실행 1건 중 응답 수가 설정값과 같은 실행 1건" in text


def test_c_limit_verdict_partial_when_no_success_at_equal(tmp_path):
    make(tmp_path, "4", OTHER[0], 1, [[CHECK]] * 4, subtype="error_max_turns", passed=False, final=False, max_turns=4)
    make(tmp_path, "4", OTHER[0], 2, [[CHECK]], max_turns=4)                                # 응답 2 < 4
    line = next(ln for ln in ec.build_from_dir_c(tmp_path).splitlines() if ln.startswith("- max_turns 4:"))
    assert "부분 지지" in line and "확인 불가" in line


def test_c_limit_verdict_contradiction_cases_are_undecidable(tmp_path):
    make(tmp_path, "5", OTHER[0], 1, [[CHECK]] * 5, max_turns=5)                            # success인데 응답 6 > 5
    make(tmp_path, "5", OTHER[1], 1, [[CHECK]] * 5, subtype="error_max_turns", passed=False, final=False, max_turns=5)
    make(tmp_path, "7", OTHER[2], 1, [[CHECK]] * 2, subtype="error_max_turns", passed=False, final=False, max_turns=7)   # 에러인데 응답 2 != 7
    text = ec.build_from_dir_c(tmp_path)
    l5 = next(ln for ln in text.splitlines() if ln.startswith("- max_turns 5:"))
    l7 = next(ln for ln in text.splitlines() if ln.startswith("- max_turns 7:"))
    assert l5.startswith("- max_turns 5: 확인 불가") and "모순" in l5
    assert l7.startswith("- max_turns 7: 확인 불가") and "모순" in l7


def test_c_limit_verdict_when_no_run_hit_the_limit(tmp_path):
    make(tmp_path, "default", OTHER[0], 1, [[CHECK]] * 3)
    line = next(ln for ln in ec.build_from_dir_c(tmp_path).splitlines() if ln.startswith("- max_turns 20:"))
    assert line.startswith("- max_turns 20: 확인 불가") and "한계에 걸린 실행 없음" in line


def test_c_probes_collect_and_main_exp_c(tmp_path):
    t0, t1 = "2026-11-12T03:00:00.000+00:00", "2026-11-12T03:30:00.000+00:00"
    _probe(tmp_path, "expC-maxTurns3", "start", 0.40, 0.2, t0)
    _probe(tmp_path, "expC-maxTurns3", "end", 0.41, 0.2, t1)
    make(tmp_path, "3", OTHER[0], 1, cost=0.1, ts="2026-11-12T03:10:00.000+00:00", max_turns=3)
    sec = ec.build_from_dir_c(tmp_path)
    sec = sec[sec.index(ec.SECTION_TITLES_C[2]):]
    line = next(ln for ln in sec.splitlines() if ln.startswith("| 3 |"))
    assert "+0.01" in line and "| 1 | $0.1000 |" in line
    raw = tmp_path / "raw"
    raw.mkdir()
    fill_c(raw, "default")
    args = ["--exp", "C", "--raw-dir", str(raw), "--out-md", str(tmp_path / "c.md"), "--out-csv", str(tmp_path / "c.csv")]
    assert ec.main(args) == 1                                                         # baseline만 있으면 거부
    make(raw, "3", OTHER[0], 1, max_turns=3)
    assert ec.main(args) == 0
    assert (tmp_path / "c.md").read_text(encoding="utf-8").startswith("# 실험 C 비교표")


def test_c_collect_does_not_mix_other_experiments(tmp_path):
    fill_c(tmp_path, "3")
    fill_c(tmp_path, "4")
    fill_all(tmp_path, "long")
    (tmp_path / "expC_haiku_maxTurns3_summary.jsonl").write_text("{}", encoding="utf-8")
    cols = ec.collect(tmp_path, ec.PREFIXES_C)
    total = 3 * len(TASKS)
    assert len(cols["3"]) == total and len(cols["4"]) == total and cols["5"] == [] and cols["default"] == []


def test_c_tables_have_consistent_cell_counts(tmp_path):
    for c in COLS_C:
        fill_c(tmp_path, c)
    width = None
    for ln in ec.build_from_dir_c(tmp_path).splitlines():
        if not ln.startswith("|"):
            width = None
            continue
        n = len(ln.strip().strip("|").split("|"))
        width = width or n
        assert n == width, ln


# ---------------- 실험 D: haiku baseline vs sonnet (같은 (과제, run) 쌍만) ----------------

PREFIX.update({"haiku": "baseline_haiku_default", "sonnet": "expD_sonnet_default"})
COLS_D = ["haiku", "sonnet"]


def cells_d(text, label):
    sec = text[text.index(ec.SECTION_TITLES_D[0]):text.index(ec.SECTION_TITLES_D[1])]
    lines = [ln for ln in sec.splitlines() if ln.startswith(f"| {label}")]
    assert len(lines) == 1, (label, lines)
    return [c.strip() for c in lines[0].strip().strip("|").split("|")]


def _d_setup(tmp_path):
    for t in TASKS:
        for r in (1, 2, 3):
            make(tmp_path, "haiku", t, r, [[S_BUILTIN]] if t in SEARCH else [[F_BUILTIN]], cost=0.01)
    hard = ["H01", "H02", "H04"]
    for t in hard:
        make(tmp_path, "sonnet", t, 1, [[S_CUSTOM], [F_CUSTOM]], cost=0.05, passed=t != "H02")


def test_d_scope_line_lists_common_pairs_and_counts(tmp_path):
    _d_setup(tmp_path)
    text = ec.build_from_dir_d(tmp_path)
    assert text.startswith("# 실험 D 비교표 (exp_compare)\n")
    head = text[:text.index(ec.SECTION_TITLES_D[0])]
    assert "비교 범위: 같은 (과제, run) 쌍 3건, 과제 3개(H01, H02, H04)" in head
    assert f"haiku baseline 전체 {3 * len(TASKS)}건 중 3건" in head and "sonnet 전체 3건 중 3건" in head
    assert ec.COLUMNS_D == COLS_D and "| 지표 | haiku | sonnet | 표본 |" in text
    assert ec.SECTION_TITLES_D == ["## 1. haiku vs sonnet (같은 (과제, run) 쌍만)", "## 2. 한도와 배치별 비용"]


def test_d_compares_only_pairs_present_in_both(tmp_path):
    _d_setup(tmp_path)
    make(tmp_path, "sonnet", "H05", 2, [[S_CUSTOM]], cost=0.07)                   # haiku에도 H05 run2가 있으므로 쌍이 된다
    make(tmp_path, "sonnet", "E01", 4, [[S_CUSTOM]], cost=9.0)                    # haiku에 run4가 없다 -> 제외
    text = ec.build_from_dir_d(tmp_path)
    assert "같은 (과제, run) 쌍 4건" in text and "sonnet 전체 5건 중 4건" in text
    assert cells_d(text, "실행당 평균 비용")[2] == f"${(0.05 * 3 + 0.07) / 4:.4f}"      # run4(9.0)는 평균에 안 들어간다
    assert cells_d(text, "실행당 평균 비용")[1] == "$0.0100"
    assert cells_d(text, "성공률")[1] == "100% (4/4)" and cells_d(text, "성공률")[2] == "75% (3/4)"


def test_d_rows_selection_rates_means_and_sample_labels(tmp_path):
    _d_setup(tmp_path)
    text = ec.build_from_dir_d(tmp_path)
    rows = [ln.split("|")[1].strip() for ln in text[text.index(ec.SECTION_TITLES_D[0]):text.index(ec.SECTION_TITLES_D[1])].splitlines()
            if ln.startswith("| ") and not ln.startswith("| 지표")]
    assert rows == ["성공률", "error_max_turns 건수", "평균 모델 응답 수", "평균 도구 호출 수", "실행당 평균 비용",
                    "search_text 선택률", "Grep 사용률", "file_stats 선택률", "Read 사용률", "일관성 (a) 도구 순서", "일관성 (b) 핵심 인자"]
    assert cells_d(text, "평균 도구 호출 수")[2] == "2.0" and cells_d(text, "평균 도구 호출 수")[1] == "1.0"
    assert cells_d(text, "search_text 선택률")[1] == "n/a" and cells_d(text, "search_text 선택률")[2] == "n/a"     # H01, H02, H04는 search 쌍 과제가 아니다
    assert cells_d(text, "file_stats 선택률")[2] == "100% (3/3)" and cells_d(text, "file_stats 선택률")[1] == "0% (0/3)"   # 세 과제 모두 file_stats 쌍
    sec1 = text[text.index(ec.SECTION_TITLES_D[0]):text.index(ec.SECTION_TITLES_D[1])]
    for ln in sec1.splitlines():
        if ln.startswith("| ") and not ln.startswith("| 지표"):
            assert re.search(r"N=\d+, 과제당 [\d~]+회.*총 \d+건", ln), ln
    assert report.SMALL_SAMPLE_WARNING in cells_d(text, "성공률")[-1]
    assert "n/a (0쌍)" in cells_d(text, "일관성 (a) 도구 순서")[2]                # 쌍마다 1회라 일관성 계산 불가


def test_d_consistency_uses_only_pairs_with_two_or_more_runs(tmp_path):
    for t in TASKS:
        for r in (1, 2, 3):
            make(tmp_path, "haiku", t, r, [[(S_CUSTOM, {"query": "a"})]])
    for r in (1, 2):
        make(tmp_path, "sonnet", "H01", r, [[(S_CUSTOM, {"query": "a"})]])
    make(tmp_path, "sonnet", "H01", 3, [[(F_CUSTOM, {"path": "x"})]])
    text = ec.build_from_dir_d(tmp_path)
    assert "3쌍" in cells_d(text, "일관성 (a) 도구 순서")[2]
    assert cells_d(text, "일관성 (a) 도구 순서")[1].startswith("100%")             # haiku도 같은 3개 쌍(H01 run1~3)만 비교


def test_d_probes_use_sonnet_probe_names_and_main_exp_d(tmp_path):
    t0, t1 = "2026-11-12T03:00:00.000+00:00", "2026-11-12T03:30:00.000+00:00"
    rows = [{"kind": "config", "ts": t0, "task_id": "probe"}, {"kind": "summary", "ts": t0, "five_hour": 0.4, "seven_day": 0.2}]
    (tmp_path / "probe_sonnet_expD-default_inv1_start.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    rows[1].update({"ts": t1, "five_hour": 0.47})
    (tmp_path / "probe_sonnet_expD-default_inv1_end.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    make(tmp_path, "sonnet", "H01", 1, cost=0.5, ts="2026-11-12T03:10:00.000+00:00")
    text = ec.build_from_dir_d(tmp_path)
    line = next(ln for ln in text[text.index(ec.SECTION_TITLES_D[1]):].splitlines() if ln.startswith("| sonnet |"))
    assert "+0.07" in line and "| 1 | $0.5000 |" in line
    raw = tmp_path / "raw"
    raw.mkdir()
    for t in TASKS:
        make(raw, "haiku", t, 1)
    args = ["--exp", "D", "--raw-dir", str(raw), "--out-md", str(tmp_path / "d.md"), "--out-csv", str(tmp_path / "d.csv")]
    assert ec.main(args) == 1                                                         # sonnet 로그가 없으면 거부
    make(raw, "sonnet", "H01", 1)
    assert ec.main(args) == 0
    assert (tmp_path / "d.md").read_text(encoding="utf-8").startswith("# 실험 D 비교표")


def test_d_no_common_pairs_is_stated_not_crashed(tmp_path):
    make(tmp_path, "haiku", "E01", 1)
    make(tmp_path, "sonnet", "H01", 1)
    text = ec.build_from_dir_d(tmp_path)
    assert "같은 (과제, run) 쌍 0건" in text and "n/a" in cells_d(text, "성공률")[1]
