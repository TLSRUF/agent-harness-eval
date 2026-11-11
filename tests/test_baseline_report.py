"""baseline_report 테스트 (구현보다 먼저 작성). 출력 형식(섹션 제목, 표 머리글, 문구)을 여기서 고정한다. API 호출 없음."""
import json
import re
from pathlib import Path

import pytest

from src.eval import baseline_report as br
from src.eval import loader

TASKS = {t.id: t for t in loader.load_all()}
PAIR = [t.id for t in TASKS.values() if "search_text|Grep" in t.overlap_with]
NOPAIR = [t.id for t in TASKS.values() if not t.overlap_with]
EASY = sorted(t for t in TASKS if t.startswith("E"))
MED = sorted(t for t in TASKS if t.startswith("M"))
HARD = sorted(t for t in TASKS if t.startswith("H"))
CUSTOM, BUILTIN = "mcp__t__search_text", "Grep"


def write_log(d: Path, task, run, rounds=(), *, passed=True, failure_type=None, num_turns=None, subtype="success", graded=True,
              grouped=False, prefix="baseline_haiku_default", suffix=".jsonl"):
    """rounds: 응답 하나당 도구 이름 목록. 응답마다 고유 message_id를 준다.
    grouped=False면 SDK처럼 tool_use 블록마다 AssistantMessage를 따로 기록(같은 message_id), True면 한 메시지에 모두 담는다."""
    rows = [{"kind": "config", "task_id": task, "config": {"model": "claude-haiku-5-5", "max_turns": 20}},
            {"kind": "message", "message": {"_type": "SystemMessage", "subtype": "init", "data": {"cwd": "C:/x", "tools": []}}}]
    n_calls = 0
    for i, names in enumerate(rounds):
        mid = f"msg_{i}"
        blocks = []
        for name in names:
            blocks.append({"_type": "ToolUseBlock", "id": f"tu{n_calls}", "name": name, "input": {}})
            n_calls += 1
        if grouped:
            rows.append({"kind": "message", "message": {"_type": "AssistantMessage", "message_id": mid, "content": blocks}})
        else:
            for b in blocks:
                rows.append({"kind": "message", "message": {"_type": "AssistantMessage", "message_id": mid, "content": [b]}})
        for b in blocks:
            rows.append({"kind": "message", "message": {"_type": "UserMessage", "content": [
                {"_type": "ToolResultBlock", "tool_use_id": b["id"], "content": "x", "is_error": None}]}})
    rows.append({"kind": "message", "message": {"_type": "AssistantMessage", "message_id": "msg_final",
                                                "content": [{"_type": "TextBlock", "text": "done"}]}})      # 도구 없는 마지막 응답
    nt = n_calls + 1 if num_turns is None else num_turns
    g = None
    if graded:
        g = {"passed": passed, "failure_type": "pass" if passed else (failure_type or "wrong_value")}
    rows.append({"kind": "summary", "subtype": subtype, "is_error": subtype != "success", "num_turns": nt, "total_cost_usd": 0.01,
                 "exception": None, "graded": g})
    p = d / f"{prefix}_{task}_run{run}{suffix}"
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    return p


def report(d, **kw):
    return br.build_baseline_report(sorted(d.glob("*.jsonl")), **kw)


def section(text, title):
    # report.py 출력 안에도 '## ' 제목이 있으므로, 고정된 섹션 제목 6개만 경계로 본다
    marks = sorted((text.index(f"## {t}\n"), t) for t in br.SECTION_TITLES if f"## {t}\n" in text)
    assert text.count(f"## {title}\n") == 1, title
    start = text.index(f"## {title}\n")
    later = [p for p, _ in marks if p > start]
    return text[start:(min(later) if later else len(text))]


# ---------------- 형식 고정 ----------------

def test_section_titles_and_order_are_fixed(tmp_path):
    write_log(tmp_path, EASY[0], 1, [[CUSTOM]])
    text = report(tmp_path)
    assert br.SECTION_TITLES == ["a. 난이도별 성공률", "b. 과제별 턴 수 분포", "c. 반복 간 성패가 갈린 과제",
                                 "d. 검색 도구 사용 (search_text|Grep 쌍 과제)", "e. 실행별 도구 호출 수, 모델 응답 수, 보고된 num_turns",
                                 "report.py 출력"]
    assert text.startswith("# 베이스라인 보고 (baseline_report)\n")
    positions = [text.index(f"## {t}") for t in br.SECTION_TITLES]
    assert positions == sorted(positions)
    assert "- 입력: 실행 1건(과제 1개, 과제당 1회)" in text


# ---------------- a. 난이도별 성공률 ----------------

def test_a_difficulty_table_counts_and_sample_labels(tmp_path):
    for r in (1, 2, 3):
        write_log(tmp_path, EASY[0], r)                                  # 쉬움 3/3
        write_log(tmp_path, MED[0], r, passed=r != 3)                    # 보통 2/3
        write_log(tmp_path, HARD[0], r, passed=False)                    # 어려움 0/3
    write_log(tmp_path, HARD[1], 1, graded=False)                        # 채점 없음은 분모에서 제외하고 따로 알림
    a = section(report(tmp_path), br.SECTION_TITLES[0])
    assert "| 난이도 | 통과 | 채점된 실행 | 성공률 | 표본 |" in a
    assert "| 쉬움 | 3 | 3 | 100% | N=1, 과제당 3회 / 총 3건 |" in a
    assert "| 보통 | 2 | 3 | 67% | N=1, 과제당 3회 / 총 3건 |" in a
    assert "| 어려움 | 0 | 3 | 0% | N=1, 과제당 3회 / 총 3건 |" in a
    assert "| 전체 | 5 | 9 | 56% | N=3, 과제당 3회 / 총 9건 |" in a
    assert "채점 없음 1건(성공률 분모에서 제외)" in a


def test_a_ceiling_alert_at_90_percent_and_not_below(tmp_path):
    for r in (1, 2, 3):
        for t in EASY[:3]:
            write_log(tmp_path, t, r)
    for r in (1, 2, 3):
        write_log(tmp_path, MED[0], r, passed=r != 3)
    text = report(tmp_path)                                              # 11/12 = 92%
    a = section(text, br.SECTION_TITLES[0])
    assert "[천장 효과 알림]" in a and "92%" in a and "11/12" in a
    assert "난이도별(특히 성패가 갈린 과제) 결과 중심으로 해석할까요?" in a
    d = tmp_path / "low"
    d.mkdir()
    for r in (1, 2, 3):
        write_log(d, EASY[0], r)
        write_log(d, MED[0], r, passed=False)
    a2 = section(br.build_baseline_report(sorted(d.glob("*.jsonl"))), br.SECTION_TITLES[0])
    assert "[천장 효과 알림]" not in a2
    assert "천장 효과 점검: 전체 성공률 50% (90% 미만, 알림 없음)" in a2


# ---------------- b. 턴 수 분포 ----------------

def test_b_turn_distribution_per_task_and_overall(tmp_path):
    for r, n in zip((1, 2, 3), (4, 6, 5)):
        write_log(tmp_path, EASY[0], r, num_turns=n)
    for r, n in zip((1, 2, 3), (10, 12, 21)):
        write_log(tmp_path, HARD[0], r, num_turns=n, subtype="error_max_turns" if n == 21 else "success", passed=n != 21)
    b = section(report(tmp_path), br.SECTION_TITLES[1])
    assert "| 과제 | 난이도 | 실행 수 | 최소 | 중앙값 | 최대 | error_max_turns |" in b
    assert f"| {EASY[0]} | 쉬움 | 3 | 4 | 5 | 6 | 0 |" in b
    assert f"| {HARD[0]} | 어려움 | 3 | 10 | 12 | 21 | 1 |" in b
    # 전체 6건 [4,5,6,10,12,21]: 중앙값 8, 상위 10%(90번째 백분위, 가장 가까운 순위 ceil(0.9*6)=6번째) 21, 최대 21
    assert "- 전체(6건): 중앙값 8, 90번째 백분위 21, 최대 21, error_max_turns 1건" in b
    assert "error_max_turns는 설정값+1로 보고된다" in b


# ---------------- c. 성패가 갈린 과제 ----------------

def test_c_split_outcomes_table_and_any_failure_list(tmp_path):
    for r in (1, 2, 3):
        write_log(tmp_path, EASY[0], r)                                              # 전부 성공
        write_log(tmp_path, EASY[1], r, passed=False, failure_type="format_error")   # 전부 실패(갈리지 않음)
    write_log(tmp_path, MED[0], 1, num_turns=7)
    write_log(tmp_path, MED[0], 2, passed=False, failure_type="wrong_value", num_turns=9)
    write_log(tmp_path, MED[0], 3, num_turns=8)
    c = section(report(tmp_path), br.SECTION_TITLES[2])
    assert "| 과제 | 난이도 | run별 결과 | run별 턴 수 |" in c
    assert f"| {MED[0]} | 보통 | run1 pass / run2 wrong_value / run3 pass | 7 / 9 / 8 |" in c
    assert c.count(f"| {EASY[0]} |") == 0 and c.count(f"| {EASY[1]} |") == 0          # 갈리지 않은 과제는 표에 없음
    assert f"- 성패가 갈린 과제: 1개/{3}개" in c
    assert f"- 한 번이라도 실패한 과제: 2개/3개 ({EASY[1]}, {MED[0]})" in c
    assert f"- 모든 반복에서 실패한 과제: 1개 ({EASY[1]})" in c


def test_c_none_split(tmp_path):
    for r in (1, 2):
        write_log(tmp_path, EASY[0], r)
    c = section(report(tmp_path), br.SECTION_TITLES[2])
    assert "성패가 갈린 과제 없음(1개 과제 모두 반복 간 결과가 같음)" in c
    assert "- 한 번이라도 실패한 과제: 0개/1개" in c


# ---------------- d. 검색 도구 사용 ----------------

def test_d_search_tool_counts_only_pair_tasks(tmp_path):
    p = PAIR[0]
    write_log(tmp_path, p, 1, [[CUSTOM, CUSTOM], [BUILTIN]])
    write_log(tmp_path, p, 2, [[BUILTIN, BUILTIN, BUILTIN]])
    write_log(tmp_path, p, 3, [["Read"]])
    write_log(tmp_path, NOPAIR[0], 1, [[CUSTOM]])                         # 쌍이 없는 과제는 제외
    d = section(report(tmp_path), br.SECTION_TITLES[3])
    assert "| 과제 | run | search_text | Grep |" in d
    assert f"| {p} | run1 | 2 | 1 |" in d and f"| {p} | run2 | 0 | 3 |" in d and f"| {p} | run3 | 0 | 0 |" in d
    assert f"| {p} | 합계 | 2 | 4 |" in d
    assert NOPAIR[0] not in d
    # 선택률 = 한 번이라도 쓴 실행 / 쌍 과제 실행: search_text 1/3, Grep 2/3
    assert "search_text 선택률 33% (N=1, 과제당 3회 / 총 3건)" in d
    assert "Grep 사용률 67% (N=1, 과제당 3회 / 총 3건)" in d
    assert "search_text만 0, Grep만 1, 둘 다 1, 둘 다 안 씀 1" in d


# ---------------- e. 호출 수 / 응답 수 / num_turns ----------------

def test_e_calls_vs_responses_vs_num_turns(tmp_path):
    # 응답 3개 중 하나가 도구 3개를 병렬 호출(블록마다 AssistantMessage를 따로 기록하는 SDK 방식): 호출 5, 응답 4(마지막 텍스트 응답 포함)
    write_log(tmp_path, EASY[0], 1, [["Read"], ["Grep", "Grep", "Grep"], ["Read"]])
    # 한 메시지에 tool_use 2개를 담은 경우
    write_log(tmp_path, EASY[1], 1, [["Read", "Read"]], grouped=True)
    e = section(report(tmp_path), br.SECTION_TITLES[4])
    assert ("| 실행 | 도구 호출 수 | 모델 응답 수 | 보고된 num_turns | num_turns - 호출 수 | num_turns - 응답 수 "
            "| 한 메시지 안 tool_use 2개 이상인 메시지 수 | 한 응답(message_id) 안 tool_use 2개 이상인 응답 수 |") in e
    assert f"| {EASY[0]}_run1 | 5 | 4 | 6 | 1 | 2 | 0 | 1 |" in e
    assert f"| {EASY[1]}_run1 | 2 | 2 | 3 | 1 | 1 | 1 | 1 |" in e
    assert "- num_turns = 도구 호출 수 + 1: 2/2건" in e
    assert "- num_turns = 모델 응답 수 + 1: 1/2건" in e                    # 두 번째 실행은 우연히 응답 2 + 1 = 3 (호출 수 + 1과 겹침)
    assert "- num_turns = 모델 응답 수: 0/2건" in e
    assert "- 한 메시지 안에 tool_use 2개 이상: 1/2건 실행(메시지 1개)" in e


# ---------------- 입력 처리 ----------------

def test_partial_and_final_inputs_are_ignored_and_runs_sorted(tmp_path):
    write_log(tmp_path, EASY[0], 2)
    write_log(tmp_path, EASY[0], 10)
    write_log(tmp_path, EASY[0], 1)
    write_log(tmp_path, EASY[0], 1, suffix=".jsonl.partial1")
    (tmp_path / "baseline_haiku_default_E01_run1_final").mkdir()
    text = br.build_baseline_report(sorted(tmp_path.glob("*")))
    assert "실행 3건" in text
    e = section(text, br.SECTION_TITLES[4])
    rows = [ln for ln in e.splitlines() if ln.startswith(f"| {EASY[0]}_run")]
    assert [r.split("|")[1].strip() for r in rows] == [f"{EASY[0]}_run1", f"{EASY[0]}_run2", f"{EASY[0]}_run10"]


def test_empty_input_and_main_prints(tmp_path, capsys):
    assert "읽을 로그가 없다" in br.build_baseline_report([])
    write_log(tmp_path, EASY[0], 1)
    assert br.main([str(tmp_path / "baseline_haiku_default_*_run*.jsonl")]) == 0
    assert "## a. 난이도별 성공률" in capsys.readouterr().out
    assert br.main([str(tmp_path / "nothing_*.jsonl")]) == 1


def test_report_py_output_is_embedded(tmp_path):
    write_log(tmp_path, EASY[0], 1)
    r = section(report(tmp_path), "report.py 출력")
    assert "pass^k" in r and "N=1" in r


# ---------------- 실제 day7check 로그 (있을 때만) ----------------

def test_real_day7check_logs_turns_equal_calls_plus_one():
    files = sorted(Path("results/raw").glob("day7check_haiku_default_H*_run1.jsonl"))
    if len(files) != 5:
        pytest.skip("day7check 로그가 이 환경에 없다")
    e = section(br.build_baseline_report(files), br.SECTION_TITLES[4])
    assert "- num_turns = 도구 호출 수 + 1: 5/5건" in e
    assert "- num_turns = 모델 응답 수 + 1: 0/5건" in e


def test_a_ceiling_alert_boundary_exactly_90_percent(tmp_path):
    for r in range(1, 6):
        write_log(tmp_path, EASY[0], r)
        write_log(tmp_path, EASY[1], r, passed=r != 5)                   # 9/10 = 90%: 경계값은 알림 대상
    assert "[천장 효과 알림]" in section(report(tmp_path), br.SECTION_TITLES[0])
