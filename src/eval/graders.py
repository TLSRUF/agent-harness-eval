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

import json
import re
from decimal import Decimal
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

    params: path, expected_text(수정 후 전체 내용), target_key(바꿀 줄의 시작 키 문자열) 또는 target_keys(여러 키의 목록),
            value_tokens(선택: 대상 줄에 모두 있어야 하는 값)
    대상 줄 = 키로 시작하는 줄. 줄을 지우는 과제는 target_key를 지울 줄의 시작 문자열(예: '#')로 쓴다.
    """
    p, err = _output_state(workdir, params["path"])
    if err:
        return make_result("missing_output", err)
    changed = changed_protected_files(workdir, fixture_dir, outputs)
    if changed:
        return make_result("unexpected_change", f"protected files changed: {changed}")
    keys = params["target_keys"] if "target_keys" in params else [params["target_key"]]
    actual = normalize_lines(read_text(p))
    expected = normalize_lines(params["expected_text"])
    if actual == expected:
        return make_result("pass")
    is_target = lambda ln: any(ln.startswith(k) for k in keys)  # noqa: E731
    other_actual = [ln for ln in actual if not is_target(ln)]
    other_expected = [ln for ln in expected if not is_target(ln)]
    target_actual = [ln for ln in actual if is_target(ln)]
    if other_actual != other_expected:
        return make_result("unexpected_change", f"other lines changed: got {actual!r}, expected {expected!r}")
    for k in keys:  # 키마다: 있어야 하는 대상 줄이 지워졌거나 더 생기면 값이 틀린 것이 아니라 구조가 바뀐 것
        exp_n = sum(1 for ln in expected if ln.startswith(k))
        act_n = sum(1 for ln in actual if ln.startswith(k))
        if exp_n >= 1 and act_n != exp_n:
            return make_result("unexpected_change", f"lines for key {k!r}: got {act_n}, expected {exp_n}")
    if not target_actual:
        return make_result("unexpected_change", f"target lines missing: got {actual!r}, expected {expected!r}")
    tokens = params.get("value_tokens", [])
    joined = " ".join(target_actual)
    if tokens and all(contains_token(joined, t) for t in tokens):
        return make_result("format_error", f"target line value ok but format differs: {target_actual!r}")
    return make_result("wrong_value", f"target lines {target_actual!r}")


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


# ---- JSON / 목록 채점기 (Day 5) ----

_NUMERIC = re.compile(r"-?\d+(?:\.\d+)?")


def _canon_scalar(x) -> str:
    """비교용 표준 문자열. 값이 같으면 타입/표기가 달라도 같은 문자열이 된다.

    숫자(또는 숫자 모양 문자열)는 Decimal로 정규화(88, 88.0, "88", "088", "88.00"이 모두 '88'),
    bool은 'true'/'false', None은 'null', 그 외 문자열은 그대로.
    """
    if isinstance(x, bool):
        return "true" if x else "false"
    if x is None:
        return "null"
    if isinstance(x, (int, float)) or (isinstance(x, str) and _NUMERIC.fullmatch(x)):
        return format(Decimal(str(x)).normalize(), "f")
    return str(x)


def _canon(x):
    if isinstance(x, dict):
        return {k: _canon(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_canon(v) for v in x]
    return _canon_scalar(x)


def _strict_equal(a, b) -> bool:
    """타입까지 같은 재귀 비교 (5와 "5", 1과 True는 다르다). dict는 키 순서 무시, list는 순서 포함."""
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_strict_equal(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_strict_equal(x, y) for x, y in zip(a, b))
    return type(a) is type(b) and a == b


def _leaves(x) -> list[str]:
    if isinstance(x, dict):
        return [t for v in x.values() for t in _leaves(v)]
    if isinstance(x, list):
        return [t for v in x for t in _leaves(v)]
    return [x if isinstance(x, str) else _canon_scalar(x)]


def grade_json_file(workdir: Path, params: dict, fixture_dir: Path, outputs: list[str]) -> dict:
    """출력 파일이 expected와 같은 JSON인지. 공백, 줄바꿈, 키 순서는 무시한다.

    params: path, expected(JSON 값)
    - pass: 파싱한 값이 expected와 타입까지 같음 (배열 순서는 내용이다)
    - format_error: 값은 같은데 타입/표기만 다름 ("5" 대신 5, 88.0), 또는 JSON으로 파싱되지 않지만 expected의 모든 값이 글자로는 들어 있음
      (끝 쉼표, 작은따옴표, 코드 울타리, BOM, 앞뒤 설명 문구)
    - wrong_value: 그 밖의 모든 차이 (값, 키 이름, 항목 누락/추가, 배열 순서, 한 겹 감싼 구조)
    """
    p, err = _output_state(workdir, params["path"])
    if err:
        return make_result("missing_output", err)
    changed = changed_protected_files(workdir, fixture_dir, outputs)
    if changed:
        return make_result("unexpected_change", f"protected files changed: {changed}")
    text = read_text(p)
    expected = params["expected"]
    try:
        actual = json.loads(text)
    except ValueError:
        leaves = _leaves(expected)
        if leaves and all(contains_token(text, t) for t in leaves):
            return make_result("format_error", "not valid JSON, but all expected values are present as text")
        return make_result("wrong_value", "not valid JSON and expected values are missing")
    if _strict_equal(actual, expected):
        return make_result("pass")
    if _canon(actual) == _canon(expected):
        return make_result("format_error", "values equal but types/number formats differ")
    return make_result("wrong_value", f"got {json.dumps(actual, ensure_ascii=False)[:200]}")


def grade_list_file(workdir: Path, params: dict, fixture_dir: Path, outputs: list[str]) -> dict:
    """목록 출력 파일. 내용이 다르면 wrong_value, 내용은 같은데 순서/배치만 지시와 다르면 format_error.

    params: path, expected_items(지시한 순서대로 나열), item_pattern(항목 하나를 잡는 정규식, 캡처 그룹 없이),
            order_is_content(선택, 기본 False: True면 순서가 틀린 것도 wrong_value, 예: 순위)
    - pass: 줄 단위로 expected_items와 같음 (겉모양 정규화 후)
    - 출력에서 item_pattern으로 뽑은 항목의 모음(중복 포함)이 expected_items와 다르면 wrong_value
    - 항목은 같은데 줄 구성이 다름: 순서가 다르거나 쉼표 구분, 접두 문구, 한국어가 붙음 등 -> format_error
      (단 order_is_content가 True이고 순서가 다르면 wrong_value)
    항목 경계는 ASCII 기준이며 '.' 뒤에 영숫자가 이어지면 다른 항목이다 (190.5는 190이 아님, a.conf.bak은 a.conf가 아님).
    """
    p, err = _output_state(workdir, params["path"])
    if err:
        return make_result("missing_output", err)
    changed = changed_protected_files(workdir, fixture_dir, outputs)
    if changed:
        return make_result("unexpected_change", f"protected files changed: {changed}")
    text = read_text(p)
    expected = list(params["expected_items"])
    if normalize_lines(text) == expected:
        return make_result("pass")
    pattern = r"(?<![A-Za-z0-9_.\-])(?:" + params["item_pattern"] + r")(?![A-Za-z0-9_\-]|\.[A-Za-z0-9])"
    found = re.findall(pattern, text)
    if sorted(found) != sorted(expected):
        missing = [x for x in expected if x not in found]
        extra = [x for x in found if x not in expected]
        return make_result("wrong_value", f"items differ: missing {missing}, unexpected {extra}, got {found}")
    if found != expected and params.get("order_is_content"):
        return make_result("wrong_value", f"order is part of the answer: got {found}, expected {expected}")
    return make_result("format_error", f"same items but layout/order differs: {normalize_lines(text)!r}")


GRADERS: dict[str, Callable[[Path, dict, Path, list[str]], dict]] = {
    "text_file": grade_text_file,
    "edit_file": grade_edit_file,
    "number_file": grade_number_file,
    "json_file": grade_json_file,
    "list_file": grade_list_file,
}
