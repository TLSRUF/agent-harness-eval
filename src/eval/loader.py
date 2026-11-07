"""과제 로더와 검증.

사용:
  python -m src.eval.loader              # 요약 + 정적 검증
  python -m src.eval.loader --check      # + 정답 풀이/무작업 채점 검증 (5가지 검증 전부)
  python -m src.eval.loader --criteria   # docs/task_grading_criteria.md 생성

5가지 검증 (status가 todo가 아닌 과제 전부)
 1. 프롬프트에 도구 이름이 없다
 2. overlap_with 형식이 맞다 (커스텀|내장)
 3. 정답 풀이를 적용하면 채점을 통과한다
 4. 아무것도 안 한 fixture는 채점에서 실패한다
 5. fixture, 채점기, 정답 풀이가 모두 있다
 6. (생성기가 만든 과제만, --check) 생성기가 정한 값(fixtures/_gen/plants/<ID>.json) = 독립 검색 스크립트(verify_counts.py)가 센 값
    = 과제 JSON의 answer. 하나라도 다르면 실패
추가 필수 항목: ID 형식, format_hint가 프롬프트에 글자 그대로 있음, grading.allowed(허용 기준 한 줄), hand_check.
"""
from __future__ import annotations

import argparse
import importlib
import json
import re
import shutil
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .graders import GRADERS

ROOT = Path(__file__).resolve().parents[2]
TASKS_DIR = Path(__file__).resolve().parent / "tasks"
FIXTURES_DIR = ROOT / "fixtures"
CRITERIA_DOC = ROOT / "docs" / "task_grading_criteria.md"
PLANTS_DIR = FIXTURES_DIR / "_gen" / "plants"

ID_RE = re.compile(r"^([EMH])(\d{2})$")
DIFFICULTY = {"E": "easy", "M": "medium", "H": "hard"}
TARGETS = {"easy": 15, "medium": 17, "hard": 8}
CUSTOM_TOOLS = ("search_text", "file_stats", "check_result")
BUILTIN_TOOLS = ("Read", "Write", "Edit", "Glob", "Grep")
OVERLAP_RE = re.compile(r"^(%s)\|(%s)$" % ("|".join(CUSTOM_TOOLS), "|".join(BUILTIN_TOOLS)))
# 프롬프트 금지어: 도구 이름. 대문자로 시작하는 일반 영단어와 겹치는 것(Read/Write/Edit)은 대소문자 구분.
_B0, _B1 = r"(?<![A-Za-z0-9_])", r"(?![A-Za-z0-9_])"  # ASCII 경계: 한국어 조사가 붙은 "Grep을"도 잡는다
LINT_INSENSITIVE = [r"search_text", r"file_stats", r"check_result", r"mcp__",
                    _B0 + r"grep" + _B1, _B0 + r"glob" + _B1, _B0 + r"bash" + _B1]
LINT_SENSITIVE = [_B0 + r"Read" + _B1, _B0 + r"Write" + _B1, _B0 + r"Edit" + _B1]
KEYS_REQUIRED = {"id", "slug", "rev", "difficulty", "prompt", "fixture", "outputs", "grading", "overlap_with", "hand_check"}
KEYS_OPTIONAL = {"format_hint", "status", "_comment", "answer"}


@dataclass
class Task:
    id: str
    slug: str
    rev: int
    difficulty: str
    prompt: str
    fixture: str
    outputs: list[str]
    grading: dict[str, Any]
    overlap_with: list[str]
    hand_check: str
    format_hint: str | None = None
    status: str = "ready"
    raw: dict = field(default_factory=dict, repr=False)

    @property
    def fixture_dir(self) -> Path:
        return FIXTURES_DIR / self.fixture

    @property
    def is_todo(self) -> bool:
        return self.status == "todo"


def load_task(path: Path) -> Task:
    d = json.loads(path.read_text(encoding="utf-8"))
    return Task(
        id=d.get("id", ""), slug=d.get("slug", ""), rev=d.get("rev", 0), difficulty=d.get("difficulty", ""),
        prompt=d.get("prompt", ""), fixture=d.get("fixture", ""), outputs=d.get("outputs", []),
        grading=d.get("grading", {}), overlap_with=d.get("overlap_with", []), hand_check=d.get("hand_check", ""),
        format_hint=d.get("format_hint"), status=d.get("status", "ready"), raw=d,
    )


def load_all(tasks_dir: Path = TASKS_DIR) -> list[Task]:
    return [load_task(p) for p in sorted(tasks_dir.glob("*.json"))]


# ---- 모듈 해석 ----

def solution_module(task_id: str):
    try:
        return importlib.import_module(f"src.eval.solutions.{task_id}")
    except ModuleNotFoundError:
        return None


def resolve_grader(task: Task) -> Callable[[Path], dict] | None:
    """채점 함수를 workdir -> 결과 dict 호출 형태로 돌려준다. 없으면 None."""
    name = task.grading.get("grader", "")
    if name.startswith("custom:"):
        fn = getattr(importlib.import_module("src.eval.graders_user"), name.split(":", 1)[1], None)
        return fn if callable(fn) else None
    fn = GRADERS.get(name)
    if fn is None:
        return None
    params = task.grading.get("params", {})
    return lambda workdir: fn(workdir, params, task.fixture_dir, task.outputs)


def make_grader(task: Task) -> Callable[[Path], dict]:
    """runner_agent.run_task의 grader 인자로 쓸 수 있는 함수."""
    fn = resolve_grader(task)
    if fn is None:
        raise ValueError(f"no grader for {task.id}")
    return fn


# ---- 검증 ----

def lint_prompt(prompt: str) -> list[str]:
    hits = [p for p in LINT_INSENSITIVE if re.search(p, prompt, re.IGNORECASE)]
    hits += [p for p in LINT_SENSITIVE if re.search(p, prompt)]
    return hits


def validate_static(task: Task) -> list[str]:
    """정적 검증(검증 1, 2, 5와 필수 항목)."""
    errs: list[str] = []
    m = ID_RE.match(task.id)
    if not m:
        errs.append(f"id 형식 오류: {task.id!r} (예: E01)")
    elif DIFFICULTY[m.group(1)] != task.difficulty:
        errs.append(f"difficulty({task.difficulty})가 id 접두({m.group(1)})와 다름")
    unknown = set(task.raw) - KEYS_REQUIRED - KEYS_OPTIONAL
    missing = KEYS_REQUIRED - set(task.raw)
    if unknown:
        errs.append(f"알 수 없는 키: {sorted(unknown)}")
    if missing:
        errs.append(f"필수 키 누락: {sorted(missing)}")
        return errs
    if not isinstance(task.rev, int) or task.rev < 1:
        errs.append("rev는 1 이상의 정수")
    if not task.slug:
        errs.append("slug 비어 있음")
    if not task.prompt.strip():
        errs.append("prompt 비어 있음")
    # 1. 도구 이름 금지
    bad = lint_prompt(task.prompt)
    if bad:
        errs.append(f"[1] 프롬프트에 도구 이름 사용: {bad}")
    # format_hint
    if task.outputs:
        if not task.format_hint:
            errs.append("outputs가 있는 과제는 format_hint 필수")
        elif task.format_hint not in task.prompt:
            errs.append(f"format_hint가 프롬프트에 글자 그대로 없음: {task.format_hint!r}")
    # 2. overlap_with 형식
    for pair in task.overlap_with:
        if not OVERLAP_RE.match(pair):
            errs.append(f"[2] overlap_with 형식 오류: {pair!r} (예: search_text|Grep)")
    # 5. fixture, 채점기, 정답 풀이 존재
    if not task.fixture_dir.is_dir():
        errs.append(f"[5] fixture 폴더 없음: fixtures/{task.fixture}")
    g = task.grading
    if not g.get("grader"):
        errs.append("[5] grading.grader 없음")
    else:
        try:
            if resolve_grader(task) is None:
                errs.append(f"[5] 채점기를 찾을 수 없음: {g['grader']}")
        except Exception as e:  # noqa: BLE001
            errs.append(f"[5] 채점기 로드 실패: {e}")
    if not str(g.get("allowed", "")).strip():
        errs.append("grading.allowed(허용 기준 한 줄) 필수")
    if not g.get("grader", "").startswith("custom:") and "params" not in g:
        errs.append("내장 채점기는 grading.params 필수")
    sol = solution_module(task.id)
    if sol is None or not hasattr(sol, "solve"):
        errs.append(f"[5] 정답 풀이 없음: src/eval/solutions/{task.id}.py (solve(workdir) 필요)")
    if not task.hand_check.strip():
        errs.append("hand_check(손으로 세는 근거) 필수")
    return errs


def _fresh_workdir(task: Task) -> Path:
    td = Path(tempfile.mkdtemp(prefix=f"chk_{task.id}_"))
    shutil.copytree(task.fixture_dir, td, dirs_exist_ok=True)
    return td


def check_plant(task: Task, plants_dir: Path = PLANTS_DIR, counters: dict | None = None) -> list[str]:
    """검증 6: 생성기가 정한 값, 독립 검색 스크립트가 센 값, 과제 JSON의 answer가 모두 같아야 한다.

    plants 파일도 answer 필드도 없는 과제(손으로 만든 과제)는 해당 없음.
    """
    plant_path = plants_dir / f"{task.id}.json"
    has_answer = "answer" in task.raw
    if not plant_path.exists() and not has_answer:
        return []
    errs: list[str] = []
    if not plant_path.exists():
        return [f"[6] 과제 JSON에 answer가 있는데 plants 파일이 없음: {plant_path.name}"]
    if not has_answer:
        return [f"[6] plants 파일이 있는데 과제 JSON에 answer가 없음: {task.id}"]
    if counters is None:
        from . import verify_counts
        counters = verify_counts.COUNTERS
    counter = counters.get(task.id)
    if counter is None:
        return [f"[6] 독립 검색 스크립트(verify_counts)에 {task.id} 카운터가 없음"]
    planted = json.loads(plant_path.read_text(encoding="utf-8"))["answer"]
    try:
        counted = counter(task.fixture_dir)
    except Exception as e:  # noqa: BLE001
        return [f"[6] 독립 검색 스크립트 실행 중 예외: {type(e).__name__}: {e}"]
    declared = task.raw["answer"]
    if not (planted == counted == declared):
        errs.append(f"[6] 정답 불일치: 생성기가 정한 값={planted}, 독립 검색으로 센 값={counted}, 과제 JSON answer={declared}")
    return errs


def check_solution(task: Task) -> list[str]:
    """검증 3(정답 풀이 통과)과 검증 4(무작업 실패)."""
    errs: list[str] = []
    grader = resolve_grader(task)
    sol = solution_module(task.id)
    if grader is None or sol is None or not hasattr(sol, "solve"):
        return ["[3,4] 채점기나 정답 풀이가 없어 실행 불가"]
    wd = _fresh_workdir(task)
    try:
        try:
            sol.solve(wd)
            r = grader(wd)
        except Exception as e:  # noqa: BLE001
            errs.append(f"[3] 정답 풀이/채점 중 예외: {type(e).__name__}: {e}")
        else:
            if not r.get("passed"):
                errs.append(f"[3] 정답 풀이가 채점 실패: {r}")
    finally:
        shutil.rmtree(wd, ignore_errors=True)
    wd = _fresh_workdir(task)
    try:
        try:
            r = grader(wd)
        except Exception as e:  # noqa: BLE001
            errs.append(f"[4] 무작업 채점 중 예외: {type(e).__name__}: {e}")
        else:
            if r.get("passed"):
                errs.append(f"[4] 아무것도 안 했는데 채점 통과: {r}")
    finally:
        shutil.rmtree(wd, ignore_errors=True)
    return errs


# ---- 요약 ----

def summarize(tasks: list[Task]) -> str:
    ready = [t for t in tasks if not t.is_todo]
    todo = [t for t in tasks if t.is_todo]
    lines = ["# 과제 요약", "", "난이도별 과제 수 (준비됨 / 미작성 / 목표):"]
    for diff in ("easy", "medium", "hard"):
        r = sum(1 for t in ready if t.difficulty == diff)
        w = sum(1 for t in todo if t.difficulty == diff)
        lines.append(f"- {diff}: {r} / {w} / {TARGETS[diff]}")
    lines.append(f"- 합계: {len(ready)} / {len(todo)} / {sum(TARGETS.values())}")
    if todo:
        lines.append(f"미작성(todo): {', '.join(t.id for t in todo)}")
    with_overlap = [t for t in ready if t.overlap_with]
    lines += ["", f"overlap_with가 있는 과제: {len(with_overlap)} / 준비된 {len(ready)}개 (선택률 계산 대상)"]
    pairs: dict[str, list[str]] = defaultdict(list)
    for t in with_overlap:
        for p in t.overlap_with:
            pairs[p].append(t.id)
    for p in sorted(pairs):
        lines.append(f"- {p}: {len(pairs[p])}개 ({', '.join(pairs[p])})")
    if not pairs:
        lines.append("- (없음)")
    return "\n".join(lines)


# ---- 채점 기준 문서 ----

BASELINE = ("앞뒤 공백, 끝 줄바꿈, 연속 공백(탭 포함)은 무시한다. 줄 끝 형식(CRLF/LF)도 무시한다. "
            "그 외 내용(숫자, 파일명, 대소문자, 줄 순서, 문장부호)은 엄격하게 일치해야 pass다.")


def loose_flags(task: Task) -> list[str]:
    """기본 기준(BASELINE)보다 느슨한 설정이 있으면 설명 목록."""
    p = task.grading.get("params", {})
    flags = list(task.grading.get("loose", []))  # custom 채점기는 params가 없으므로 JSON에서 직접 선언한다
    if p.get("case_insensitive"):
        flags.append("대소문자 무시")
    if float(p.get("abs_tol", 0) or 0) > 0:
        flags.append(f"숫자 허용 오차 {p['abs_tol']}")
    if p.get("ignore_order"):
        flags.append("줄 순서 무시")
    if p.get("partial_match"):
        flags.append("부분 일치 허용")
    return flags


def write_criteria(tasks: list[Task], path: Path = CRITERIA_DOC) -> str:
    ready = [t for t in tasks if not t.is_todo]
    out = ["# 과제 채점 기준 (자동 생성: python -m src.eval.loader --criteria)", "",
           "> 이 문서는 생성물이다. 고치려면 과제 JSON의 grading을 고치고 다시 생성한다.", "",
           "## 모든 과제에 공통인 관대한 기준 (겉모양만)", "", BASELINE, "",
           "- custom 채점기(E13 이후 사용자 작성)에는 위 공통 기준이 자동 적용되지 않는다. 그 과제의 `allowed` 문구가 기준이며, "
           "공통 기준보다 느슨한 부분은 JSON의 `grading.loose`에 선언해야 아래 목록에 나타난다.", "",
           "- `format_error`, `wrong_value`, `missing_output`, `unexpected_change`는 모두 **실패**다. "
           "format_error는 값은 맞고 형식만 틀린 실패를 구분해 보려는 분류일 뿐 통과 기준을 느슨하게 하지 않는다.", "",
           "## 기본 기준보다 느슨한 과제 (사용자 확인 필요)", ""]
    loose = [(t, loose_flags(t)) for t in ready if loose_flags(t)]
    if loose:
        out += ["| 과제 | 느슨한 설정 | 허용 기준(allowed) |", "|---|---|---|"]
        out += [f"| {t.id} | {', '.join(f)} | {t.grading.get('allowed','')} |" for t, f in loose]
    else:
        out.append("(없음: 현재 준비된 과제 전부가 공통 기준만 적용한다.)")
    out += ["", "## 과제별 허용 기준 한 줄", "", "| 과제 | 채점기 | 허용 기준(allowed) |", "|---|---|---|"]
    out += [f"| {t.id} | {t.grading.get('grader')} | {t.grading.get('allowed','')} |" for t in ready]
    todo = [t.id for t in tasks if t.is_todo]
    if todo:
        out += ["", f"미작성(todo): {', '.join(todo)}"]
    text = "\n".join(out) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")
    return text


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="정답 풀이/무작업 채점 검증까지 실행")
    ap.add_argument("--criteria", action="store_true", help="docs/task_grading_criteria.md 생성")
    a = ap.parse_args(argv)
    tasks = load_all()
    print(summarize(tasks))
    problems: dict[str, list[str]] = {}
    for t in tasks:
        if t.is_todo:
            continue
        errs = validate_static(t)
        if a.check and not errs:
            errs += check_solution(t)
            errs += check_plant(t)
        if errs:
            problems[t.id] = errs
    ready = sum(1 for t in tasks if not t.is_todo)
    print(f"\n검증: 준비된 {ready}개 중 문제 있는 과제 {len(problems)}개" + (" (정적 + 정답 풀이/무작업)" if a.check else " (정적만)"))
    for tid, errs in problems.items():
        for e in errs:
            print(f"  {tid}: {e}")
    if a.criteria:
        write_criteria(tasks)
        print(f"\n{CRITERIA_DOC} 생성")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
