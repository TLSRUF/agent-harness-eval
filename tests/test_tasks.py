"""과제 로더 검증: 준비된 모든 과제에 대한 5가지 검증과 로더 규칙 자체 테스트."""
import json
import shutil
from pathlib import Path

import pytest

from src.eval import loader
from src.eval.loader import (
    Task, check_solution, lint_prompt, load_all, load_task, summarize, validate_static,
)

ALL = load_all()
READY = [t for t in ALL if not t.is_todo]
TODO = [t for t in ALL if t.is_todo]


@pytest.mark.parametrize("task", READY, ids=lambda t: t.id)
def test_static_validation(task):
    assert validate_static(task) == []


def grader_pending(task: Task) -> bool:
    """사용자가 아직 채점 함수를 쓰지 않았는가 (NotImplementedError)."""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        try:
            loader.resolve_grader(task)(Path(td))
        except NotImplementedError:
            return True
        except Exception:  # noqa: BLE001  (다른 예외는 실제 문제이므로 pending이 아니다)
            return False
    return False


@pytest.mark.parametrize("task", READY, ids=lambda t: t.id)
def test_solution_passes_and_noop_fails(task):
    if grader_pending(task):
        pytest.skip(f"{task.id}: 사용자 채점 함수 작성 대기 (graders_user.py)")
    assert check_solution(task) == []


def test_ids_unique_and_prefix():
    ids = [t.id for t in ALL]
    assert len(ids) == len(set(ids))
    assert all(loader.ID_RE.match(i) for i in ids)


def test_user_tasks_are_ready_and_only_graders_pending():
    ids = {t.id for t in READY}
    assert {"E13", "E14", "E15"} <= ids and TODO == []
    for t in READY:
        if t.id in ("E13", "E14", "E15"):
            assert validate_static(t) == []  # 정적 검증(1, 2, 5와 필수 항목)은 채점 함수 작성 전에도 통과해야 한다
            assert t.grading["grader"] == f"custom:grade_{t.id}" and "status" not in t.raw


def test_todo_status_is_skipped_in_summary(tmp_path):
    raw = json.loads((loader.TASKS_DIR / "E01.json").read_text(encoding="utf-8"))
    raw.update(id="E90", status="todo")
    p = tmp_path / "E90.json"
    p.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    t = load_task(p)
    assert t.is_todo
    s = summarize([t])
    assert "미작성(todo): E90" in s and "- easy: 0 / 1 / 15" in s


def test_summary_counts_and_overlap():
    s = summarize(ALL)
    assert "- easy: 15 / 0 / 15" in s
    assert "- medium: 17 / 0 / 17" in s
    assert "- hard: 8 / 0 / 8" in s
    assert "- 합계: 40 / 0 / 40" in s
    assert "미작성(todo)" not in s
    assert "overlap_with가 있는 과제: 20 / 준비된 40개" in s
    assert "- search_text|Grep: 12개 (E01, E02, E08, E13, M01, M02, M03, M04, M05, M06, M07, M08)" in s
    assert "- file_stats|Read: 8개 (E03, E10, H01, H02, H04, H08, M09, M10)" in s


def test_medium_overlap_structure():
    """보통 17개의 overlap 구성: 검색 8개(search_text|Grep), 통계 2개(file_stats|Read), 나머지 7개는 없음."""
    med = {t.id: t.overlap_with for t in READY if t.id.startswith("M")}
    assert sorted(med) == [f"M{i:02d}" for i in range(1, 18)]
    assert all(med[f"M{i:02d}"] == ["search_text|Grep"] for i in range(1, 9))
    assert all(med[f"M{i:02d}"] == ["file_stats|Read"] for i in (9, 10))
    assert all(med[f"M{i:02d}"] == [] for i in range(11, 18))


def test_prompts_never_leak_overlap_or_tool_names():
    for t in READY:
        assert lint_prompt(t.prompt) == []
        assert "|" not in t.prompt  # overlap_with 쌍 표기가 프롬프트에 새지 않음


def test_all_prompts_are_korean():
    import re
    for t in READY:
        assert re.search(r"[가-힣]", t.prompt), t.id


def test_lint_catches_tool_names():
    for bad in ("search_text로 찾아줘", "Grep을 써", "Grep으로 찾아", "grep으로", "Bash를 실행", "Read로 읽어", "Glob으로", "use grep", "Read the file", "file_stats 호출", "Bash 실행", "mcp__t__x", "check_result"):
        assert lint_prompt(bad), bad
    for ok in ("파일을 읽어줘", "result.txt에 저장", "stats.txt", "already read it"):
        assert lint_prompt(ok) == [], ok


def clone(task: Task, **changes) -> Task:
    raw = {**task.raw, **changes}
    return Task(**{k: raw.get(k, v) for k, v in dict(
        id=task.id, slug=task.slug, rev=task.rev, difficulty=task.difficulty, prompt=task.prompt, fixture=task.fixture,
        outputs=task.outputs, grading=task.grading, overlap_with=task.overlap_with, hand_check=task.hand_check,
        format_hint=task.format_hint, status=task.status).items()}, raw=raw)


def test_validation_rules_detect_problems():
    base = next(t for t in READY if t.id == "E01")
    assert any("[1]" in e for e in validate_static(clone(base, prompt=base.prompt + " search_text를 써")))
    assert any("[2]" in e for e in validate_static(clone(base, overlap_with=["search_text|Foo"])))
    assert any("[2]" in e for e in validate_static(clone(base, overlap_with=["grep|Grep"])))
    assert any("글자 그대로" in e for e in validate_static(clone(base, format_hint="없는 문구")))
    assert any("format_hint 필수" in e for e in validate_static(clone(base, format_hint=None)))
    assert any("[5]" in e and "fixture" in e for e in validate_static(clone(base, fixture="NOPE")))
    assert any("allowed" in e for e in validate_static(clone(base, grading={**base.grading, "allowed": " "})))
    assert any("hand_check" in e for e in validate_static(clone(base, hand_check="")))
    assert any("id 형식" in e for e in validate_static(clone(base, id="X1")))
    assert any("difficulty" in e for e in validate_static(clone(base, difficulty="hard")))
    assert any("[5]" in e and "채점기" in e for e in validate_static(clone(base, grading={**base.grading, "grader": "nope"})))


def test_solution_check_catches_bad_solution_and_vacuous_grader(monkeypatch):
    base = next(t for t in READY if t.id == "E01")

    class BadSol:
        @staticmethod
        def solve(wd):
            (wd / "result.txt").write_text("ERROR 줄 수: 5\n", encoding="utf-8")
    monkeypatch.setattr(loader, "solution_module", lambda tid: BadSol)
    assert any("[3]" in e for e in check_solution(base))

    class NoSol:
        @staticmethod
        def solve(wd):
            pass
    monkeypatch.setattr(loader, "solution_module", lambda tid: NoSol)
    assert any("[3]" in e for e in check_solution(base))

    monkeypatch.setattr(loader, "resolve_grader", lambda t: (lambda wd: {"passed": True, "failure_type": "pass", "reason": ""}))
    errs = check_solution(base)
    assert any("[4]" in e for e in errs)  # 아무것도 안 해도 통과하는 채점기는 거부


def test_todo_task_becomes_validated_when_status_removed(tmp_path):
    raw = json.loads((loader.TASKS_DIR / "E01.json").read_text(encoding="utf-8"))
    raw.update(id="E91", fixture="NOPE", grading={**raw["grading"], "grader": "nope"}, status="todo")
    p = tmp_path / "E91.json"
    p.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    assert load_task(p).is_todo
    raw.pop("status")
    p.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    t = load_task(p)
    assert not t.is_todo and validate_static(t)  # 깨진 과제는 status를 지우는 순간 검증에서 걸린다


def test_criteria_doc_generation(tmp_path):
    out = tmp_path / "c.md"
    text = loader.write_criteria(ALL, out)
    assert out.read_text(encoding="utf-8") == text
    assert "공통인 관대한 기준" in text and "custom 채점기" in text
    assert "제품 이름 대소문자 무시" in text  # E14가 선언한 느슨한 기준이 목록에 나타나야 한다
    for t in READY:
        assert f"| {t.id} |" in text
