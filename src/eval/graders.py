"""채점 부품. 내용(숫자, 파일명 등)은 엄격하게, 겉모양(앞뒤 공백, 끝 줄바꿈, 연속 공백)은 관대하게 비교한다.

모든 채점 함수는 같은 형식의 dict를 반환한다:
    {"passed": bool, "failure_type": <FAILURE_TYPES 중 하나>, "reason": str}
failure_type
- pass: 통과
- wrong_value: 값(숫자, 파일명 등)이 틀림
- format_error: 값은 맞는데 형식만 틀림 (예: 순서, 구분자, 접두 문구)
- missing_output: 출력 파일이 없거나 비어 있음
- unexpected_change: 건드리면 안 되는 파일/줄이 바뀜
판정 우선순위: missing_output -> unexpected_change -> (내용) pass / format_error / wrong_value
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

FAILURE_TYPES = ("pass", "wrong_value", "format_error", "missing_output", "unexpected_change")


def make_result(failure_type: str, reason: str = "") -> dict[str, Any]:
    """채점 결과 dict를 만든다. 사용자 몫(E13~E15) 채점 함수도 이 함수로 반환한다."""
    if failure_type not in FAILURE_TYPES:
        raise ValueError(f"unknown failure_type: {failure_type}")
    return {"passed": failure_type == "pass", "failure_type": failure_type, "reason": reason}


# ---- 겉모양 정규화 (관대) ----

def normalize_lines(text: str) -> list[str]:
    """줄 끝 형식 통일, 줄마다 앞뒤 공백 제거와 연속 공백/탭을 한 칸으로, 앞뒤의 빈 줄 제거."""
    lines = [re.sub(r"[ \t]+", " ", ln.strip()) for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    while lines and lines[0] == "":
        lines.pop(0)
    return lines


def normalize_text(text: str) -> str:
    return "\n".join(normalize_lines(text))


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def contains_token(text: str, token: str) -> bool:
    """token이 다른 영문자/숫자/밑줄/점/하이픈의 일부가 아닌 독립된 덩어리로 text에 있는지.

    경계는 ASCII 기준이다(한국어 조사/단위가 붙은 '4줄', 'c.txt입니다'도 값이 있는 것으로 본다).
    '4'는 '14'나 '4.5'(소수의 일부)에는 매치되지 않지만, 문장 끝 '4.'에는 매치된다.
    """
    pattern = r"(?<![A-Za-z0-9_.\-])" + re.escape(token) + r"(?![A-Za-z0-9_\-]|\.\d)"
    return re.search(pattern, text) is not None


# ---- 보호 파일 검사 ----

def changed_protected_files(workdir: Path, fixture_dir: Path, outputs: list[str]) -> list[str]:
    """fixture에 있던 파일 중 outputs가 아닌 것이 사라졌거나 바뀌었으면 상대경로 목록."""
    changed = []
    for src in sorted(p for p in fixture_dir.rglob("*") if p.is_file()):
        rel = src.relative_to(fixture_dir).as_posix()
        if rel in outputs:
            continue
        dst = workdir / rel
        if not dst.is_file() or dst.read_bytes() != src.read_bytes():
            changed.append(rel)
    return changed


def _output_state(workdir: Path, path: str) -> tuple[Path, str | None]:
    p = workdir / path
    if not p.is_file():
        return p, "output file not found: " + path
    if normalize_text(read_text(p)) == "":
        return p, "output file is empty: " + path
    return p, None


# ---- 내장 채점기: 시그니처 (workdir, params, fixture_dir, outputs) ----

def grade_text_file(workdir: Path, params: dict, fixture_dir: Path, outputs: list[str]) -> dict:
    """출력 파일의 전체 내용이 expected_text와 같은지 (겉모양 정규화 후 비교).

    params: path, expected_text, value_tokens(선택), forbid_tokens(선택)
    다르면: value_tokens가 모두 있고 forbid_tokens가 없으면 format_error, 아니면 wrong_value.
    """
    p, err = _output_state(workdir, params["path"])
    if err:
        return make_result("missing_output", err)
    changed = changed_protected_files(workdir, fixture_dir, outputs)
    if changed:
        return make_result("unexpected_change", f"protected files changed: {changed}")
    actual = normalize_text(read_text(p))
    expected = normalize_text(params["expected_text"])
    if actual == expected:
        return make_result("pass")
    tokens = params.get("value_tokens", [])
    forbid = params.get("forbid_tokens", [])
    if tokens and all(contains_token(actual, t) for t in tokens) and not any(contains_token(actual, t) for t in forbid):
        return make_result("format_error", f"values present but format differs: got {actual!r}, expected {expected!r}")
    return make_result("wrong_value", f"got {actual!r}, expected {expected!r}")


def grade_edit_file(workdir: Path, params: dict, fixture_dir: Path, outputs: list[str]) -> dict:
    """파일 안의 한 줄만 바꾸고 나머지는 그대로 두었는지.

    params: path, expected_text(수정 후 전체 내용), target_key(바꿀 줄의 시작 키), value_tokens(선택)
    """
    p, err = _output_state(workdir, params["path"])
    if err:
        return make_result("missing_output", err)
    changed = changed_protected_files(workdir, fixture_dir, outputs)
    if changed:
        return make_result("unexpected_change", f"protected files changed: {changed}")
    key = params["target_key"]
    actual = normalize_lines(read_text(p))
    expected = normalize_lines(params["expected_text"])
    if actual == expected:
        return make_result("pass")
    is_target = lambda ln: ln.startswith(key)  # noqa: E731
    other_actual = [ln for ln in actual if not is_target(ln)]
    other_expected = [ln for ln in expected if not is_target(ln)]
    target_actual = [ln for ln in actual if is_target(ln)]
    if other_actual != other_expected or not target_actual:
        return make_result("unexpected_change", f"other lines changed: got {actual!r}, expected {expected!r}")
    tokens = params.get("value_tokens", [])
    if tokens and all(contains_token(target_actual[0], t) for t in tokens):
        return make_result("format_error", f"target line value ok but format differs: {target_actual[0]!r}")
    return make_result("wrong_value", f"target line {target_actual[0]!r}")


def grade_number_file(workdir: Path, params: dict, fixture_dir: Path, outputs: list[str]) -> dict:
    """숫자 하나를 허용 오차 안에서 비교한다.

    params: path, expected(number), abs_tol(기본 0), pattern(선택; 전체 일치해야 하는 정규식, 숫자는 그룹 1)
    pattern 전체 일치 + 허용 오차 이내 -> pass / 숫자는 맞는데 pattern 불일치 -> format_error / 그 외 wrong_value
    """
    p, err = _output_state(workdir, params["path"])
    if err:
        return make_result("missing_output", err)
    changed = changed_protected_files(workdir, fixture_dir, outputs)
    if changed:
        return make_result("unexpected_change", f"protected files changed: {changed}")
    text = normalize_text(read_text(p))
    expected = float(params["expected"])
    tol = float(params.get("abs_tol", 0))
    pattern = params.get("pattern")
    m = re.fullmatch(pattern, text) if pattern else None
    if m:
        value = float(m.group(1))
        ok = abs(value - expected) <= tol
        return make_result("pass") if ok else make_result("wrong_value", f"got {value}, expected {expected} +/- {tol}")
    nums = re.findall(r"-?\d+(?:\.\d+)?", text)
    if any(abs(float(n) - expected) <= tol for n in nums) and (pattern or len(nums) == 1):
        return make_result("format_error", f"number ok but format differs: {text!r}")
    return make_result("wrong_value", f"got {text!r}, expected {expected} +/- {tol}")


GRADERS: dict[str, Callable[[Path, dict, Path, list[str]], dict]] = {
    "text_file": grade_text_file,
    "edit_file": grade_edit_file,
    "number_file": grade_number_file,
}
