import asyncio
import json
import types

import pytest

from src.agent.config import HarnessConfig
from src.agent.runner_agent import HARNESS_ENV, build_options
from src.agent.tools import DESCRIPTIONS, SCHEMAS, build_server, classify_tool


def _handlers(root):
    return build_server(root)["instance"]._request_handlers


def _list_tools(root):
    r = asyncio.run(_handlers(root)["tools/list"].handler(None, None))
    return {t.name: t for t in r.tools}


def _call(root, name, args):
    h = _handlers(root)["tools/call"]
    params = h.params_type(name=name, arguments=args)
    r = asyncio.run(h.handler(None, params))
    return r


def _text(r):
    return r.content[0].text


@pytest.fixture
def box(tmp_path):
    (tmp_path / "a.txt").write_text("hello world\nsecond line\n", encoding="utf-8", newline="\n")
    return tmp_path


def test_listed_schema_matches_baseline_v1(box):
    tools = _list_tools(box)
    assert set(tools) == {"search_text", "file_stats", "check_result"}
    assert tools["search_text"].input_schema["required"] == ["query"]
    assert tools["file_stats"].input_schema["required"] == ["path"]
    assert tools["check_result"].input_schema["required"] == ["path"]
    assert set(tools["check_result"].input_schema["properties"]) == {"path", "contains", "min_lines"}
    assert tools["check_result"].input_schema["properties"]["min_lines"]["type"] == "integer"
    for name, t in tools.items():
        assert t.description == DESCRIPTIONS["default"][name]
        assert t.input_schema == SCHEMAS[name]


def test_check_result_without_optional_args(box):
    assert _text(_call(box, "check_result", {"path": "a.txt"})) == "PASS"
    assert _text(_call(box, "check_result", {"path": "a.txt", "contains": "hello"})) == "PASS"
    assert _text(_call(box, "check_result", {"path": "a.txt", "min_lines": 5})).startswith("FAIL")
    assert _text(_call(box, "check_result", {"path": "missing.txt"})).startswith("FAIL")


def test_search_text_without_path(box):
    assert "a.txt:1:hello world" in _text(_call(box, "search_text", {"query": "hello"}))


def test_classify_tool():
    assert classify_tool("mcp__t__search_text") == "custom"
    assert classify_tool("mcp__t__check_result") == "custom"
    for b in ("Read", "Write", "Edit", "Glob", "Grep"):
        assert classify_tool(b) == "builtin"
    assert classify_tool("mcp__claude_ai_Example__send_message") == "other"
    assert classify_tool("Bash") == "other"


def test_options_block_connectors(tmp_path):
    o = build_options(HarnessConfig(), tmp_path)
    assert o.env == HARNESS_ENV == {"ENABLE_CLAUDEAI_MCP_SERVERS": "false"}
    assert "Bash" not in o.tools
