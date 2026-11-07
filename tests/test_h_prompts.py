"""어려운 과제(H01~H08)의 프롬프트 규칙, hand_check 요구사항, overlap/min_steps 구성."""
import json
import re

import pytest

from src.eval import loader

TASKS = {t.id: t for t in loader.load_all() if not t.is_todo}
H = [f"H0{i}" for i in range(1, 9)]
FIX = loader.FIXTURES_DIR


def prompt(tid):
    return TASKS[tid].prompt


def plant(tid):
    return json.loads((loader.PLANTS_DIR / f"{tid}.json").read_text(encoding="utf-8"))


def test_all_hard_tasks_load_with_expected_shape():
    assert sorted(t for t in TASKS if t.startswith("H")) == H
    for tid in H:
        t = TASKS[tid]
        assert t.difficulty == "hard" and t.rev == 1 and t.status == "ready"
        assert re.search(r"[가-힣]", t.prompt)
        assert loader.validate_static(t) == []


def test_overlap_composition_matches_the_decision():
    """H07의 overlap_with는 비운다. file_stats|Read는 H01, H02, H04, H08 네 개, search_text|Grep은 H에 없다."""
    ov = {tid: TASKS[tid].overlap_with for tid in H}
    assert ov["H07"] == []
    assert [tid for tid in H if ov[tid] == ["file_stats|Read"]] == ["H01", "H02", "H04", "H08"]
    assert [tid for tid in H if ov[tid]] == ["H01", "H02", "H04", "H08"]
    pairs = [p for t in TASKS.values() for p in t.overlap_with]
    assert pairs.count("search_text|Grep") == 12 and pairs.count("file_stats|Read") == 8 and len(pairs) == 20


def test_h03_states_date_format_and_tie_rule():
    p = prompt("H03")
    assert "`Last updated: YYYY-MM-DD` 형식" in p
    assert "날짜가 가장 최근인 문서가 적은 기본 포트를 따른다" in p
    assert "가장 최근 날짜가 같은 문서가 둘 이상이면 파일 이름이 알파벳 순으로 앞서는 문서를 따른다" in p


def test_h04_counts_the_header_line_explicitly():
    p = prompt("H04")
    assert "첫 줄의 '# lines: N' 줄도 세는 줄에 포함한다" in p
    assert "줄 수는 줄바꿈으로 끝나는 줄의 개수" in p


def test_h07_states_the_processing_rules():
    p = prompt("H07")
    for sentence in ("main.conf에서 시작해 위에서 아래로 한 줄씩 처리한다", "그 파일을 그 자리에서 처리하고, 끝나면 다음 줄로 돌아온다",
                     "같은 키가 여러 번 나오면 나중에 처리한 값이 이긴다", "`#`으로 시작하는 줄은 무시한다"):
        assert sentence in p, sentence


def test_h08_states_the_size_and_tie_rule():
    p = prompt("H08")
    assert "파일 크기는 바이트 수로 비교하고" in p
    assert "크기가 같은 파일이 여럿이면 파일 이름이 알파벳 순으로 앞서는 파일을 고른다" in p


def test_definitions_and_rules_in_other_prompts():
    assert "단어는 공백으로 구분되는 덩어리야" in prompt("H01")           # E03, E10, M10과 같은 문장
    assert "줄 수는 줄바꿈으로 끝나는 줄의 개수야" in prompt("H02")       # M09와 같은 문장
    assert "customers.csv에 없는 주문은 세지 않아" in prompt("H06")
    p5 = prompt("H05")
    assert "키가 정확히 endpoint이고 값이 정확히 http://old.internal:8080인 줄" in p5 and "`#`으로 시작하는 줄" in p5 and "나머지 줄은 전혀 바꾸지 마" in p5


def test_output_files_never_match_the_input_globs():
    """출력 파일이 입력 파일과 같은 패턴(예: *.txt)이면 에이전트가 센 대상에 섞일 수 있다."""
    inputs = {"H01": "*.log", "H02": "*.txt", "H03": "*.md", "H04": "*.txt", "H06": "*.csv", "H07": "*.conf", "H08": "*.txt"}
    for tid, pattern in inputs.items():
        for out in TASKS[tid].outputs:
            assert not __import__("fnmatch").fnmatch(out, pattern), (tid, out)
    assert sorted(TASKS["H05"].outputs) == sorted(p.name for p in (FIX / "H05").iterdir())   # H05는 입력 파일을 제자리에서 고친다


def test_graders_used():
    g = {tid: TASKS[tid].grading["grader"] for tid in H}
    assert g["H05"] == "multi_edit_file" and g["H01"] == g["H04"] == "list_file"
    assert {g[t] for t in ("H02", "H03", "H06", "H07", "H08")} == {"text_file"}
    assert TASKS["H01"].grading["params"]["order_is_content"] is True            # 순위
    assert "order_is_content" not in TASKS["H04"].grading["params"]               # 알파벳 순은 지시 사항(어기면 format_error)
    assert set(TASKS["H05"].grading["params"]["files"]) == set(TASKS["H05"].outputs)


def test_every_hard_task_has_min_steps_and_basis_with_hypothesis_marks():
    assert {tid: TASKS[tid].min_steps for tid in H} == {"H01": 11, "H02": 13, "H03": 7, "H04": 12, "H05": 13, "H06": 3, "H07": 7, "H08": 11}
    for tid in H:
        assert TASKS[tid].min_steps_basis.strip()
    # 우회 가능성이 있는 과제는 근거에 '가설'을 표시한다 (M09, M10과 같은 규칙)
    for tid in ("H01", "H02", "H03", "H04", "H05", "H07"):
        assert "가설" in TASKS[tid].min_steps_basis, tid
    for tid in ("H06", "H08"):                                                    # 우회를 언급하지 않는 과제는 가설 표시가 없다
        assert "가설" not in TASKS[tid].min_steps_basis, tid


# ---------------- hand_check ----------------

def test_h07_hand_check_has_every_step_and_decoy_values():
    hc = TASKS["H07"].hand_check
    trace = plant("H07")["planted"]["trace"]
    assert len(trace) == 10
    for i, step in enumerate(trace, 1):
        assert f"({i}) {step}" in hc, i                                           # 단계별 기록
    assert "최종 timeout = 35" in hc and "net.conf의 마지막 줄" in hc
    answer = plant("H07")["answer"]["timeout"]
    for name, value in (("legacy.conf", 77), ("orphan.conf", 99)):
        assert f"{name}(timeout = {value})" in hc and value != answer             # 체인 밖 파일의 값은 정답과 다름


def test_h04_hand_check_names_both_off_by_one_traps():
    hc = TASKS["H04"].hand_check
    claims = plant("H04")["planted"]["claims"]
    minus1 = [n for n, v in claims.items() if v["claimed"] == v["actual"] - 1]
    plus1 = [n for n, v in claims.items() if v["claimed"] == v["actual"] + 1]
    assert len(minus1) == len(plus1) == 1
    assert f"{minus1[0]}는 적힌 값이 실제보다 1 작고" in hc and f"{plus1[0]}는 1 크다" in hc
    assert "둘 다 틀린 문서이고 정답은 하나다" in hc


def test_h08_hand_check_explains_chars_vs_bytes_and_tie():
    hc = TASKS["H08"].hand_check
    pl = plant("H08")["planted"]
    assert pl["char_max_file"] in hc and "글자 수로 답하면 틀린다" in hc
    for name in pl["tied_files"]:
        assert name in hc
    assert "알파벳 규칙으로" in hc and "wc -c" in hc


def test_h01_h02_h03_hand_checks_tell_how_a_human_verifies():
    assert "wc -w" in TASKS["H01"].hand_check and "wc -l" in TASKS["H01"].hand_check
    assert "경계 파일" in TASKS["H02"].hand_check and "wc -l" in TASKS["H02"].hand_check
    hc3 = TASKS["H03"].hand_check
    assert len(re.findall(r"번째 줄 `", hc3)) >= 6                                  # 표본 위치(날짜 줄과 포트 줄) 여러 개
    assert "ops_guide.md" in hc3 and "runbook.md" in hc3 and "알파벳으로 앞선" in hc3


def test_h05_and_h06_hand_checks_give_human_commands_and_samples():
    hc5 = TASKS["H05"].hand_check
    assert len(re.findall(r"번째 줄 `endpoint = http://old\.internal:8080`", hc5)) >= 3 and "grep -n" in hc5
    assert "디코이 6종" in hc5
    hc6 = TASKS["H06"].hand_check
    assert "c099" in hc6 and "세지 않는다" in hc6 and "11건" in hc6


@pytest.mark.parametrize("tid", H)
def test_h_prompts_have_no_tool_names_and_contain_their_format_hint(tid):
    t = TASKS[tid]
    assert loader.lint_prompt(t.prompt) == [] and t.format_hint in t.prompt
