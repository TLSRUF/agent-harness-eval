import asyncio
import json

import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage, SystemMessage, TextBlock

from src.agent import guard, runner_agent
from src.agent.config import HarnessConfig
from src.agent.guard import (
    ToolGuardError, allowed_tool_names, check_init_tools, check_mcp_status, tools_digest, unexpected_tools,
)
from src.agent.runner_agent import run_task

OK_TOOLS = ["Edit", "Glob", "Grep", "Read", "Write", "mcp__t__check_result", "mcp__t__file_stats", "mcp__t__search_text"]
BAD_TOOLS = OK_TOOLS + ["mcp__claude_ai_Example__send_message", "Bash"]


def init_msg(tools):
    return SystemMessage(subtype="init", data={"tools": tools, "mcp_servers": []})


def result():
    return ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False, num_turns=1,
                         session_id="s", total_cost_usd=0.001, usage={}, result="ok", terminal_reason="completed")


def fake(messages, consumed):
    async def q(prompt, options):
        for m in messages:
            consumed.append(m)
            yield m
    return q


def lines(path):
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]


def test_allowed_names_and_digest_stable():
    cfg = HarnessConfig()
    assert allowed_tool_names(cfg) == sorted(OK_TOOLS)
    d1, d2 = tools_digest(OK_TOOLS), tools_digest(reversed(OK_TOOLS))
    assert d1 == d2 and d1["count"] == 8 and len(d1["sha256"]) == 64
    assert tools_digest(BAD_TOOLS)["sha256"] != d1["sha256"]


def test_unexpected_tools():
    cfg = HarnessConfig()
    assert unexpected_tools(OK_TOOLS, cfg) == []
    assert unexpected_tools(OK_TOOLS[:3], cfg) == []  # 일부만 있는 것은 위반 아님
    assert unexpected_tools(BAD_TOOLS, cfg) == ["Bash", "mcp__claude_ai_Example__send_message"]
    with pytest.raises(ToolGuardError):
        check_init_tools(BAD_TOOLS, cfg)


def test_check_mcp_status():
    check_mcp_status([{"name": "t", "status": "connected"}])
    with pytest.raises(ToolGuardError, match="claude.ai Example"):
        check_mcp_status([{"name": "t"}, {"name": "claude.ai Example"}])


def test_run_stops_on_unexpected_tool(tmp_path, monkeypatch):
    consumed = []
    later = AssistantMessage(content=[TextBlock(text="should never be read")], model="m")
    monkeypatch.setattr(runner_agent, "query", fake([init_msg(BAD_TOOLS), later, result()], consumed))
    log = tmp_path / "bad.jsonl"
    graded = []
    with pytest.raises(ToolGuardError, match="Example"):
        asyncio.run(run_task("p", HarnessConfig(), log_path=log, grader=lambda w: graded.append(1)))
    assert later not in consumed and len(consumed) == 1  # init 이후 메시지를 읽지 않고 중단
    assert graded == []  # 채점도 하지 않음
    rows = lines(log)
    kinds = [r["kind"] for r in rows]
    assert kinds == ["config", "message", "tool_guard", "summary"]
    assert rows[2]["ok"] is False and "mcp__claude_ai_Example__send_message" in rows[2]["unexpected"]
    assert "ToolGuardError" in rows[-1]["exception"]


def test_run_ok_and_first_line_hash(tmp_path, monkeypatch):
    consumed = []
    monkeypatch.setattr(runner_agent, "query", fake([init_msg(list(reversed(OK_TOOLS))), result()], consumed))
    log = tmp_path / "ok.jsonl"
    s = asyncio.run(run_task("p", HarnessConfig(), log_path=log))
    rows = lines(log)
    first = rows[0]
    assert first["kind"] == "config"
    d = tools_digest(OK_TOOLS)
    assert first["allowed_tools_sha256"] == d["sha256"] and first["allowed_tools_count"] == 8
    guard_ev = next(r for r in rows if r["kind"] == "tool_guard")
    assert guard_ev["ok"] is True and guard_ev["observed_tools_sha256"] == d["sha256"] and guard_ev["observed_tools_count"] == 8
    assert s["subtype"] == "success" and s["exception"] is None
