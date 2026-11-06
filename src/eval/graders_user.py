"""사용자 지정 채점 함수 (E13~E15). 반환은 항상 make_result(...) 형식의 dict:
    {"passed": bool, "failure_type": "pass"|"wrong_value"|"format_error"|"missing_output"|"unexpected_change", "reason": str}

세 함수 공통 규칙
- 판정 우선순위: missing_output -> unexpected_change -> (내용) pass / format_error / wrong_value
- 출력 파일이 없거나 공백뿐이면 missing_output (E01~E12의 내장 채점기와 같은 규칙)
- 입력 파일(출력이 아닌 fixture 파일)이 바뀌면 unexpected_change (E01~E12의 내장 채점기와 같은 규칙)
- normalize_text는 쓰지 않는다. 비교는 과제마다 아래의 전용 규칙으로 한다.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

from .graders import changed_protected_files, make_result

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"

# ---------------- 공통 보조 ----------------


def _read_output(workdir: Path, name: str) -> tuple[str | None, str | None]:
    """(텍스트, 오류). 파일이 없거나 공백뿐이면 텍스트는 None이고 오류 문구가 있다."""
    p = workdir / name
    if not p.is_file():
        return None, f"output file not found: {name}"
    text = p.read_bytes().decode("utf-8", errors="replace")
    if text.strip() == "":
        return None, f"output file is empty: {name}"
    return text, None


def _split_lines_strict(text: str) -> list[str]:
    """E13/E15 전용 줄 분리: \\r\\n은 \\n으로 보고, 맨 끝의 줄바꿈 하나(또는 없음)만 무시한다.

    그 밖의 공백(줄 앞뒤 공백, 연속 공백, 끝의 빈 줄 두 개 이상)은 내용으로 취급한다.
    """
    text = text.replace("\r\n", "\n")
    if text.endswith("\n"):
        text = text[:-1]
    return text.split("\n") if text != "" else []


# ---------------- E13: WARN 줄 복사 ----------------

E13_WARN_LINE_NUMBERS = [4, 9, 15, 22, 27, 33, 41, 47]  # hand_check에 적은 줄 번호


def grade_E13(workdir: Path) -> dict:
    """warn.txt가 app.log의 WARN 줄 8개를 원래 순서 그대로, 한 글자도 바꾸지 않고 담았는지.

    허용: 끝 줄바꿈 하나(있어도 없어도 됨), \\r\\n/\\n 차이.  그 외 모든 차이는 wrong_value.
    """
    text, err = _read_output(workdir, "warn.txt")
    if err:
        return make_result("missing_output", err)
    changed = changed_protected_files(workdir, FIXTURES / "E13", ["warn.txt"])
    if changed:
        return make_result("unexpected_change", f"input files changed: {changed}")
    src = (FIXTURES / "E13" / "app.log").read_text(encoding="utf-8").splitlines()
    expected = [src[n - 1] for n in E13_WARN_LINE_NUMBERS]
    actual = _split_lines_strict(text)
    if actual == expected:
        return make_result("pass")
    missing = [ln for ln in expected if ln not in actual]
    extra = [ln for ln in actual if ln not in expected]
    if missing or extra:
        why = f"{len(missing)} expected line(s) missing or altered, {len(extra)} unexpected line(s)"
    elif len(actual) != len(expected):
        why = f"duplicate lines: got {len(actual)} lines, expected {len(expected)}"
    else:
        why = "same lines but different order"
    return make_result("wrong_value", why)


# ---------------- E14: qty 최댓값 행의 product ----------------

E14_EXPECTED = "scissors"
E14_FORMAT = re.compile(r"제품: +(\S.*?)")  # 전체 일치, 제품 이름 앞뒤 공백은 허용


def _has_token_ci(text: str, token: str) -> bool:
    """대소문자 무시, ASCII 경계 기준으로 token이 독립된 덩어리로 있는지."""
    pat = r"(?<![A-Za-z0-9_.\-])" + re.escape(token) + r"(?![A-Za-z0-9_\-]|\.\d)"
    return re.search(pat, text, re.IGNORECASE) is not None


def grade_E14(workdir: Path) -> dict:
    """top.txt가 정확히 `제품: scissors` 한 줄인지.

    허용: 제품 이름의 대소문자, 앞뒤 공백, 끝 줄바꿈.
    pass는 위 형식 전체가 맞고 이름이 같을 때만.  이름이 다르면 wrong_value.
    형식이 틀려도 정답 이름만 들어 있으면(예: `scissors`, `제품:scissors`, `제품: scissors.`) format_error.
    정답 이름이 없거나 다른 제품 이름이 함께 있으면 wrong_value.
    """
    text, err = _read_output(workdir, "top.txt")
    if err:
        return make_result("missing_output", err)
    changed = changed_protected_files(workdir, FIXTURES / "E14", ["top.txt"])
    if changed:
        return make_result("unexpected_change", f"input files changed: {changed}")
    body = text.strip()  # 앞뒤 공백과 끝 줄바꿈 허용
    m = E14_FORMAT.fullmatch(body) if "\n" not in body else None
    if m and m.group(1).casefold() == E14_EXPECTED:
        return make_result("pass")
    with (FIXTURES / "E14" / "orders.csv").open(encoding="utf-8", newline="") as f:
        others = {r["product"] for r in csv.DictReader(f)} - {E14_EXPECTED}
    if _has_token_ci(body, E14_EXPECTED) and not any(_has_token_ci(body, o) for o in others):
        return make_result("format_error", f"product ok but format differs: {body!r}")
    return make_result("wrong_value", f"got {body!r}, expected '제품: {E14_EXPECTED}'")


# ---------------- E15: 두 파일 단어 치환, 다른 줄 보존 ----------------

E15_FILES = ["memo1.txt", "memo2.txt"]


def grade_E15(workdir: Path) -> dict:
    """memo1.txt, memo2.txt에서 Cat이 든 줄만 Cat->Dog로 정확히 바뀌고 나머지는 그대로인지.

    허용: 끝 줄바꿈 하나(있어도 없어도 됨), \\r\\n/\\n 차이.  줄 내용은 정확히 같아야 한다.
    파일 줄 수가 달라지거나 바뀌면 안 되는 줄이 바뀌면 unexpected_change (wrong_value보다 우선).
    바뀌어야 하는 줄이 안 바뀌었거나 일부만/다르게 바뀌었으면 wrong_value.
    """
    texts = {}
    for name in E15_FILES:
        text, err = _read_output(workdir, name)
        if err:
            return make_result("missing_output", err)
        texts[name] = text
    unexpected: list[str] = []
    wrong: list[str] = []
    for name in E15_FILES:
        orig = (FIXTURES / "E15" / name).read_text(encoding="utf-8").splitlines()
        actual = _split_lines_strict(texts[name])
        if len(actual) != len(orig):
            unexpected.append(f"{name}: line count {len(actual)} != {len(orig)}")
            continue
        for i, (o, a) in enumerate(zip(orig, actual), 1):
            expected = o.replace("Cat", "Dog")
            if a == expected:
                continue
            if "Cat" in o:
                wrong.append(f"{name}:{i} not replaced correctly: {a!r}")
            else:
                unexpected.append(f"{name}:{i} line that must stay was changed: {a!r}")
    if unexpected:
        return make_result("unexpected_change", "; ".join(unexpected))
    if wrong:
        return make_result("wrong_value", "; ".join(wrong))
    return make_result("pass")
