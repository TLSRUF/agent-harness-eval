"""min_steps(분석 전용 필드): 로더 검증, 에이전트에게 전달되지 않음, 과제 내용 불변."""
import asyncio
import json
import shutil
from pathlib import Path

import pytest
from claude_agent_sdk import ResultMessage

from src.agent import config as agent_config
from src.agent import runner_agent
from src.agent.config import HarnessConfig
from src.eval import loader
from src.eval.loader import Task, load_all, load_task, validate_static

TASKS = [t for t in load_all() if not t.is_todo]
FIX = loader.FIXTURES_DIR


@pytest.mark.parametrize("task", TASKS, ids=lambda t: t.id)
def test_every_task_has_min_steps_and_basis(task):
    assert isinstance(task.min_steps, int) and not isinstance(task.min_steps, bool) and task.min_steps >= 1
    assert task.min_steps_basis.strip()
    assert task.min_steps == task.raw["min_steps"] and task.min_steps_basis == task.raw["min_steps_basis"]
    assert validate_static(task) == []


def _clone(task: Task, **changes) -> Task:
    raw = {**task.raw, **changes}
    raw = {k: v for k, v in raw.items() if v is not ...}
    return Task(id=task.id, slug=task.slug, rev=task.rev, difficulty=task.difficulty, prompt=task.prompt,
                fixture=task.fixture, outputs=task.outputs, grading=task.grading, overlap_with=task.overlap_with,
                hand_check=task.hand_check, format_hint=task.format_hint, status=task.status, raw=raw)


@pytest.mark.parametrize("bad", [0, -1, 2.5, "2", None, True, False, [2], {}])
def test_loader_rejects_non_positive_integer_min_steps(bad):
    t = _clone(next(x for x in TASKS if x.id == "E01"), min_steps=bad)
    assert any("min_steps" in e for e in validate_static(t)), bad


def test_loader_requires_min_steps_and_basis_keys():
    base = next(x for x in TASKS if x.id == "E01")
    for key in ("min_steps", "min_steps_basis"):
        raw = {k: v for k, v in base.raw.items() if k != key}
        t = Task(id=base.id, slug=base.slug, rev=base.rev, difficulty=base.difficulty, prompt=base.prompt,
                 fixture=base.fixture, outputs=base.outputs, grading=base.grading, overlap_with=base.overlap_with,
                 hand_check=base.hand_check, format_hint=base.format_hint, raw=raw)
        assert any(key in e for e in validate_static(t)), key
    for blank in ("", "   ", None, 3):
        t = _clone(base, min_steps_basis=blank)
        assert any("min_steps_basis" in e for e in validate_static(t)), blank


# ---------------- 에이전트에게 전달되지 않는다 ----------------

@pytest.mark.parametrize("task", TASKS, ids=lambda t: t.id)
def test_prompt_never_contains_min_steps_or_its_basis(task):
    assert "min_steps" not in task.prompt and "overlap_with" not in task.prompt
    assert task.min_steps_basis not in task.prompt
    assert task.prompt == task.raw["prompt"]  # 로더가 프롬프트를 가공하지 않는다


def test_system_prompts_and_tool_descriptions_do_not_mention_analysis_fields():
    from src.agent.tools import DESCRIPTIONS
    texts = list(agent_config.PROMPTS.values()) + [d for v in DESCRIPTIONS.values() for d in v.values()]
    assert all("min_steps" not in t and "overlap_with" not in t for t in texts)


def test_fixture_files_do_not_leak_analysis_fields():
    """에이전트는 작업 폴더의 파일을 읽을 수 있으므로 fixture에도 분석 필드가 없어야 한다."""
    for t in TASKS:
        for p in t.fixture_dir.iterdir():
            if p.is_file():
                text = p.read_bytes().decode("utf-8", errors="replace")
                assert "min_steps" not in text and "overlap_with" not in text, (t.id, p.name)


def test_agent_receives_only_prompt_text_when_run_through_the_runner(tmp_path, monkeypatch):
    """러너를 가짜 query로 돌려, 에이전트에게 실제로 넘어가는 prompt와 옵션에 분석 필드가 없음을 확인한다."""
    seen = {}

    async def fake_query(prompt, options):
        seen["prompt"], seen["options"] = prompt, options
        yield ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False, num_turns=1,
                            session_id="s", total_cost_usd=0.0, usage={}, result="ok", terminal_reason="completed")

    monkeypatch.setattr(runner_agent, "query", fake_query)
    monkeypatch.setattr(runner_agent, "RAW_DIR", tmp_path / "raw", raising=False)
    task = next(x for x in TASKS if x.id == "M09")  # min_steps가 큰(11) 과제
    asyncio.run(runner_agent.run_task(task.prompt, HarnessConfig(), log_path=tmp_path / "r.jsonl", task_id=task.id,
                                      fixtures_dir=task.fixture_dir, grader=loader.make_grader(task)))
    visible = json.dumps({"prompt": seen["prompt"], "system_prompt": seen["options"].system_prompt}, ensure_ascii=False)
    assert "min_steps" not in visible and task.min_steps_basis not in visible and "overlap_with" not in visible
    assert seen["prompt"] == task.prompt


# ---------------- 과제 내용은 바뀌지 않았다 ----------------

def test_adding_min_steps_did_not_change_task_content_or_rev():
    """HEAD(커밋된 버전)와 비교: min_steps, min_steps_basis 외의 모든 키와 rev가 같다."""
    import subprocess
    for t in TASKS:
        rel = f"src/eval/tasks/{t.id}.json"
        r = subprocess.run(["git", "show", f"HEAD:{rel}"], capture_output=True, cwd=loader.ROOT)
        if r.returncode != 0:
            pytest.skip("HEAD에 없는 과제(아직 커밋 전)")
        old = json.loads(r.stdout.decode("utf-8"))
        if "min_steps" in old:
            continue  # 이미 커밋된 뒤에는 비교 대상이 아님
        new = {k: v for k, v in t.raw.items() if k not in ("min_steps", "min_steps_basis")}
        assert new == old, t.id
        assert t.rev == old["rev"] == 1
