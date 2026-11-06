"""grade_E13 / grade_E14 / grade_E15: 처리하는 모든 경우와 failure_type."""
import shutil
from pathlib import Path

import pytest

from src.eval import graders_user as gu
from src.eval import loader

FIX = loader.FIXTURES_DIR
WARN_NUMBERS = gu.E13_WARN_LINE_NUMBERS


def fresh(tid: str, tmp_path: Path) -> Path:
    wd = tmp_path / tid
    shutil.copytree(FIX / tid, wd)
    return wd


def put(wd: Path, name: str, text: str):
    (wd / name).write_bytes(text.encode("utf-8"))


def ft(r) -> str:
    assert set(r) == {"passed", "failure_type", "reason"}
    assert r["passed"] == (r["failure_type"] == "pass")
    return r["failure_type"]


# ---------------- E13 ----------------

@pytest.fixture
def e13(tmp_path):
    wd = fresh("E13", tmp_path)
    src = (FIX / "E13" / "app.log").read_text(encoding="utf-8").splitlines()
    good = [src[n - 1] for n in WARN_NUMBERS]
    return wd, good, src


def test_e13_pass_variants(e13):
    wd, good, _ = e13
    for text in ("\n".join(good), "\n".join(good) + "\n", "\r\n".join(good), "\r\n".join(good) + "\r\n"):
        put(wd, "warn.txt", text)
        assert ft(gu.grade_E13(wd)) == "pass", repr(text[-6:])


def test_e13_missing_and_empty(e13):
    wd, good, _ = e13
    assert ft(gu.grade_E13(wd)) == "missing_output"  # 파일 없음
    put(wd, "warn.txt", "")
    assert ft(gu.grade_E13(wd)) == "missing_output"
    put(wd, "warn.txt", "  \n\n")
    assert ft(gu.grade_E13(wd)) == "missing_output"


def test_e13_wrong_value_cases(e13):
    wd, good, src = e13
    cases = {
        "누락": good[:-1],
        "추가(WARN 아닌 줄)": good + [src[0]],
        "순서": [good[1], good[0]] + good[2:],
        "순서(역순)": list(reversed(good)),
        "내용 수정": [good[0].replace("80 percent", "81 percent")] + good[1:],
        "앞 공백": [" " + good[0]] + good[1:],
        "뒤 공백": [good[0] + " "] + good[1:],
        "연속 공백": [good[0].replace(" ", "  ", 1)] + good[1:],
        "줄 번호 접두": [f"{n}: {ln}" for n, ln in zip(WARN_NUMBERS, good)],
        "중복": good + [good[0]],
        "중간 빈 줄": good[:3] + [""] + good[3:],
    }
    for label, lines in cases.items():
        put(wd, "warn.txt", "\n".join(lines) + "\n")
        r = gu.grade_E13(wd)
        assert ft(r) == "wrong_value", (label, r)
    put(wd, "warn.txt", "\n".join(good) + "\n\n")  # 끝 빈 줄 둘 이상은 '끝 줄바꿈 하나' 허용 범위를 넘음
    assert ft(gu.grade_E13(wd)) == "wrong_value"
    put(wd, "warn.txt", "\n".join(good).replace("\n", "\r"))  # 낱개 \r은 허용 대상이 아님
    assert ft(gu.grade_E13(wd)) == "wrong_value"


def test_e13_never_format_error(e13):
    wd, good, _ = e13
    for text in ("4", "WARN", "\n".join(good).upper()):
        put(wd, "warn.txt", text)
        assert ft(gu.grade_E13(wd)) == "wrong_value"


def test_e13_input_changed(e13):
    wd, good, _ = e13
    put(wd, "warn.txt", "\n".join(good) + "\n")
    (wd / "app.log").write_text("changed", encoding="utf-8")
    assert ft(gu.grade_E13(wd)) == "unexpected_change"
    (wd / "app.log").unlink()
    assert ft(gu.grade_E13(wd)) == "unexpected_change"


# ---------------- E14 ----------------

@pytest.fixture
def e14(tmp_path):
    return fresh("E14", tmp_path)


def test_e14_pass_variants(e14):
    for text in ("제품: scissors", "제품: scissors\n", "제품: scissors\r\n", "제품: Scissors", "제품: SCISSORS\n",
                 "  제품: scissors  \n\n", "제품:  scissors", "제품: scissors   ", "\n제품: scissors\n"):
        put(e14, "top.txt", text)
        assert ft(gu.grade_E14(e14)) == "pass", repr(text)


def test_e14_missing(e14):
    assert ft(gu.grade_E14(e14)) == "missing_output"
    put(e14, "top.txt", " \n")
    assert ft(gu.grade_E14(e14)) == "missing_output"


def test_e14_wrong_value(e14):
    for text in ("제품: notebook", "제품: scissor", "제품: scissorss", "제품: tape", "제품: 50", "제품: ",
                 "제품: scissors, notebook", "제품: notebook scissors", "notebook", "999"):
        put(e14, "top.txt", text)
        assert ft(gu.grade_E14(e14)) == "wrong_value", repr(text)


def test_e14_format_error(e14):
    for text in ("scissors", "제품:scissors", "제품 : scissors", "제품: scissors.", "제품: <scissors>", "제품: scissors입니다",
                 "Product: scissors", "제품: scissors\n제품: scissors", "제품: scissors (qty 50)", "제품 - scissors"):
        put(e14, "top.txt", text)
        assert ft(gu.grade_E14(e14)) == "format_error", repr(text)


def test_e14_input_changed(e14):
    put(e14, "top.txt", "제품: scissors")
    (e14 / "orders.csv").write_text("x", encoding="utf-8")
    assert ft(gu.grade_E14(e14)) == "unexpected_change"


# ---------------- E15 ----------------

@pytest.fixture
def e15(tmp_path):
    wd = fresh("E15", tmp_path)
    o1 = (FIX / "E15" / "memo1.txt").read_text(encoding="utf-8").splitlines()
    o2 = (FIX / "E15" / "memo2.txt").read_text(encoding="utf-8").splitlines()
    return wd, o1, o2


def write_memos(wd, l1, l2, nl="\n", end="\n"):
    put(wd, "memo1.txt", nl.join(l1) + end)
    put(wd, "memo2.txt", nl.join(l2) + end)


def good_lines(o1, o2):
    return [ln.replace("Cat", "Dog") for ln in o1], [ln.replace("Cat", "Dog") for ln in o2]


def test_e15_untouched_input_is_wrong_value(e15):
    wd, o1, o2 = e15  # fixture 그대로 = 아무것도 안 바꿈
    assert ft(gu.grade_E15(wd)) == "wrong_value"


def test_e15_pass_variants(e15):
    wd, o1, o2 = e15
    g1, g2 = good_lines(o1, o2)
    for nl, end in (("\n", "\n"), ("\n", ""), ("\r\n", "\r\n"), ("\r\n", "")):
        write_memos(wd, g1, g2, nl, end)
        assert ft(gu.grade_E15(wd)) == "pass", (nl, end)


def test_e15_missing(e15):
    wd, o1, o2 = e15
    g1, g2 = good_lines(o1, o2)
    write_memos(wd, g1, g2)
    (wd / "memo2.txt").unlink()
    assert ft(gu.grade_E15(wd)) == "missing_output"
    put(wd, "memo2.txt", "")
    assert ft(gu.grade_E15(wd)) == "missing_output"


def test_e15_wrong_value_not_replaced(e15):
    wd, o1, o2 = e15
    g1, g2 = good_lines(o1, o2)
    write_memos(wd, g1, o2)  # memo2 안 바꿈
    assert ft(gu.grade_E15(wd)) == "wrong_value"
    write_memos(wd, o1, g2)  # memo1 안 바꿈
    assert ft(gu.grade_E15(wd)) == "wrong_value"
    partial = list(g2)
    partial[3] = "A Dog chased another Cat across the yard."  # 한 줄 안의 두 Cat 중 하나만
    write_memos(wd, g1, partial)
    assert ft(gu.grade_E15(wd)) == "wrong_value"
    lower = list(g2)
    lower[0] = lower[0].replace("Dog", "dog")  # 대소문자 틀림
    write_memos(wd, g1, lower)
    assert ft(gu.grade_E15(wd)) == "wrong_value"
    other = list(g1)
    other[1] = "Our Cow sleeps on the porch every afternoon."  # 다른 단어로 바꿈
    write_memos(wd, other, g2)
    assert ft(gu.grade_E15(wd)) == "wrong_value"


def test_e15_unexpected_change(e15):
    wd, o1, o2 = e15
    g1, g2 = good_lines(o1, o2)
    touched = list(g1)
    touched[0] = touched[0] + "!"  # Cat이 없는 줄 수정
    write_memos(wd, touched, g2)
    assert ft(gu.grade_E15(wd)) == "unexpected_change"
    trailing = list(g2)
    trailing[2] = trailing[2] + " "  # 공백 하나도 내용으로 취급
    write_memos(wd, g1, trailing)
    assert ft(gu.grade_E15(wd)) == "unexpected_change"
    write_memos(wd, g1[:-1], g2)  # 줄 수 줄어듦
    assert ft(gu.grade_E15(wd)) == "unexpected_change"
    write_memos(wd, g1, g2 + ["extra line"])  # 줄 수 늘어남
    assert ft(gu.grade_E15(wd)) == "unexpected_change"
    write_memos(wd, g1, g2, end="\n\n")  # 끝 빈 줄 둘 이상 = 줄 수 달라짐
    assert ft(gu.grade_E15(wd)) == "unexpected_change"


def test_e15_unexpected_beats_wrong_value(e15):
    wd, o1, o2 = e15
    g1, g2 = good_lines(o1, o2)
    touched = list(g1)
    touched[0] = "changed"  # 바꾸면 안 되는 줄 수정
    write_memos(wd, touched, o2)  # + memo2는 안 바꿈(wrong_value 조건)
    assert ft(gu.grade_E15(wd)) == "unexpected_change"
