import asyncio
import json
from pathlib import Path

import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, ToolResultBlock, ToolUseBlock, UserMessage

from src.agent import runner_agent
from src.agent.config import COMPARE_MODEL, HarnessConfig
from src.agent.runner_agent import result_path, run_task, to_jsonable


def test_config_defaults_and_switch():
    c = HarnessConfig()
    assert c.model == "claude-haiku-5-5" and c.max_turns == 20 and "Bash" not in c.builtin_tools
    assert c.model_short == "haiku"
    s = HarnessConfig(model=COMPARE_MODEL, max_turns=5)
    assert s.model_short == "sonnet" and s.max_turns == 5
    assert c.to_dict()["builtin_tools"] == ["Read", "Write", "Edit", "Glob", "Grep"]


def test_config_rejects_bash_and_unknown_prompt():
    with pytest.raises(ValueError):
        HarnessConfig(builtin_tools=("Read", "Bash"))
    with pytest.raises(ValueError):
        HarnessConfig(prompt_version="nope")


def test_result_path_naming():
    p = result_path("expA", HarnessConfig(), "toolDescLong", 1, Path("results"))
    assert p.as_posix() == "results/expA_haiku_toolDescLong_run1.jsonl"
    p = result_path("baseline", HarnessConfig(), "default", 2, Path("results"))
    assert p.name == "baseline_haiku_default_run2.jsonl"


def test_to_jsonable_roundtrip():
    m = AssistantMessage(content=[TextBlock(text="hi"), ToolUseBlock(id="1", name="x", input={"a": 1})], model="m")
    d = json.loads(json.dumps(to_jsonable(m)))
    assert d["_type"] == "AssistantMessage" and d["content"][1]["_type"] == "ToolUseBlock"


def _result(**kw):
    base = dict(subtype="success", duration_ms=10, duration_api_ms=5, is_error=False, num_turns=2,
                session_id="s", total_cost_usd=0.01, usage={"input_tokens": 1, "output_tokens": 2},
                result="done", terminal_reason="completed")
    base.update(kw)
    return ResultMessage(**base)


def _fake_query(messages, raise_after=None):
    async def fake(prompt, options):
        for m in messages:
            yield m
        if raise_after:
            raise raise_after
    return fake


def test_run_task_logs_and_counts(tmp_path, monkeypatch):
    msgs = [
        AssistantMessage(content=[ToolUseBlock(id="1", name="mcp__t__file_stats", input={"path": "a"})], model="m"),
        UserMessage(content=[ToolResultBlock(tool_use_id="1", content="denied", is_error=True)]),
        _result(),
    ]
    monkeypatch.setattr(runner_agent, "query", _fake_query(msgs))
    fx = tmp_path / "fx"
    fx.mkdir()
    (fx / "a.txt").write_text("x", encoding="utf-8")
    seen = {}

    def grader(workdir):
        seen["files"] = sorted(p.name for p in workdir.iterdir())
        return {"passed": True}

    log = tmp_path / "out" / "t.jsonl"
    s = asyncio.run(run_task("p", HarnessConfig(), log_path=log, task_id="t1", fixtures_dir=fx, grader=grader))
    assert s["tool_calls"] == 1 and s["tool_errors"] == 1 and s["num_turns"] == 2
    assert s["graded"] == {"passed": True} and seen["files"] == ["a.txt"]
    lines = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]
    assert [r["kind"] for r in lines] == ["config", "message", "message", "message", "grade", "summary"]
    assert lines[0]["config"]["model"] == "claude-haiku-5-5" and lines[0]["config"]["max_turns"] == 20
    assert lines[-1]["total_cost_usd"] == 0.01 and lines[-1]["usage"]["output_tokens"] == 2


def test_run_task_records_exception(tmp_path, monkeypatch):
    from claude_agent_sdk import ClaudeSDKError
    monkeypatch.setattr(runner_agent, "query", _fake_query([_result(subtype="error_max_turns", is_error=True,
                                                                     terminal_reason="max_turns")], raise_after=ClaudeSDKError("boom")))
    log = tmp_path / "e.jsonl"
    s = asyncio.run(run_task("p", HarnessConfig(max_turns=1), log_path=log))
    assert s["subtype"] == "error_max_turns" and "ClaudeSDKError" in s["exception"]
    kinds = [json.loads(x)["kind"] for x in log.read_text(encoding="utf-8").splitlines()]
    assert "exception" in kinds and kinds[-1] == "summary"
