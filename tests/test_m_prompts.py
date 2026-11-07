"""보통 과제(M01~M17)의 프롬프트 문구 요구사항과 hand_check 표본의 정확성."""
import re

import pytest

from src.eval import loader

TASKS = {t.id: t for t in loader.load_all() if not t.is_todo}
FIX = loader.FIXTURES_DIR


def prompt(tid):
    return TASKS[tid].prompt


def test_line_number_answers_state_first_line_is_1():
    """줄 번호가 정답인 과제(E08, M02, M03)는 프롬프트에 '첫 줄이 1번이야'가 있다."""
    targets = [tid for tid, t in TASKS.items() if "줄 번호" in (t.format_hint or "")]
    assert {"E08", "M02", "M03"} <= set(targets)
    for tid in targets:
        assert "첫 줄이 1번이야" in prompt(tid), tid


def test_m04_explains_structure():
    p = prompt("M04")
    assert "BUILD_ID가 든 줄이 여러 개 있고 같은 값이 여러 번 나와" in p
    assert "정확히 한 번만 나오는 값 하나" in p


def test_m09_m10_define_lines_and_words():
    assert "줄 수는 줄바꿈으로 끝나는 줄의 개수야" in prompt("M09")
    word_def = "단어는 공백으로 구분되는 덩어리야"
    for tid in ("E03", "E10", "M10"):  # E03, E10과 같은 문장
        assert word_def in prompt(tid), tid


def test_m05_and_m15_conditions_are_explicit():
    assert "timeout과 retry=3이 둘 다 들어 있는 줄" in prompt("M05")
    assert "줄 전체가 #로 시작하는 줄" in prompt("M15")


def test_m16_m17_hints_are_concrete():
    h16, h17 = TASKS["M16"].format_hint, TASKS["M17"].format_hint
    assert "id,name,city" in h16 and "따옴표" in h16          # 헤더 순서, 따옴표 사용 여부
    assert '"name"' in h17 and '"score"' in h17 and h17.startswith("[{") and h17.endswith("...]")
    assert "문자열" in prompt("M17")                          # 값 타입(문자열)


def test_search_tasks_do_not_put_target_token_in_format_hint():
    """검색 대상 단어가 출력 형식에 들어 있으면 출력 파일을 다시 검색할 때 오염될 수 있다."""
    targets = {"M01": "dev-017", "M05": "timeout", "M07": "deadline", "M03": "E4021", "M02": "FAILED"}
    for tid, token in targets.items():
        assert token not in TASKS[tid].format_hint, tid


SAMPLE = re.compile(r"(?:\[(\S+) )?(\d+)번째 줄 `([^`]*)`")


@pytest.mark.parametrize("tid", [f"M0{i}" for i in range(1, 9)])
def test_big_fixture_hand_check_has_three_verified_samples(tid):
    """M01~M08의 hand_check에는 줄 번호와 줄 내용 표본이 3개 이상 있고, 실제 fixture와 일치한다."""
    samples = SAMPLE.findall(TASKS[tid].hand_check)
    assert len(samples) >= 3, (tid, len(samples))
    files = sorted(p.name for p in (FIX / tid).iterdir())
    for name, num, content in samples:
        fname = name or files[0]
        assert fname in files, (tid, fname)
        lines = (FIX / tid / fname).read_bytes().decode("utf-8").split("\n")[:-1]
        assert lines[int(num) - 1] == content, (tid, fname, num)


def test_hand_check_decoy_examples_really_are_non_targets():
    """'아닌 줄 예'로 든 표본이 실제로 대상이 아닌지 확인한다 (M01: dev-017이 없는 줄, M02: FAILED가 없는 줄)."""
    for tid, marker, token in (("M01", "dev-017이 아닌 줄 예: [", "dev-017"), ("M02", "FAILED가 아닌 줄 예: [", "FAILED")):
        hc = TASKS[tid].hand_check
        m = re.search(re.escape(marker) + r"(\d+)번째 줄 `([^`]*)`", hc)  # 로그 줄 안에 ]가 있을 수 있어 백틱 기준으로 읽는다
        assert m, (tid, hc[:80])
        num, content = m.groups()
        assert token not in content, (tid, num, content)


def test_m10_hand_check_names_the_boundary_files():
    import json
    words = json.loads((loader.PLANTS_DIR / "M10.json").read_text(encoding="utf-8"))["planted"]["words_per_file"]
    hc = TASKS["M10"].hand_check
    for count in (19, 20, 21):
        name = next(n for n, c in words.items() if c == count)
        assert f"{name}는 " in hc and f"{count}단어" in hc, (count, name)
    assert "기준과 같음" in hc and "기준보다 1 작음" in hc and "기준보다 1 큼" in hc


def test_m09_hand_check_lists_all_line_counts():
    import json
    lpf = json.loads((loader.PLANTS_DIR / "M09.json").read_text(encoding="utf-8"))["planted"]["lines_per_file"]
    hc = TASKS["M09"].hand_check
    for name, c in lpf.items():
        assert f"'{name}': {c}" in hc, name


def test_new_graders_are_used_where_designed():
    g = {tid: t.grading["grader"] for tid, t in TASKS.items() if tid.startswith("M")}
    assert g["M17"] == "json_file"
    assert {g[x] for x in ("M02", "M06", "M10", "M12", "M13")} == {"list_file"}
    assert TASKS["M13"].grading["params"]["order_is_content"] is True
    assert all("order_is_content" not in TASKS[x].grading["params"] for x in ("M02", "M06", "M10", "M12"))
    assert TASKS["M14"].grading["params"]["target_keys"] == ["timeout", "retries"]
    assert TASKS["M15"].grading["params"]["target_key"] == "#"
    assert "JSON 객체의 키 순서 무시" in TASKS["M17"].grading["loose"]
