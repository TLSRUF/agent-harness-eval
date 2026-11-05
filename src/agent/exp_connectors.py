"""커넥터 노출 확인 + 차단 시험 (호출 3회). 레포 설정은 바꾸지 않고 옵션만 덮어쓴다.

1) probe: 현재 설정에서 커넥터 도구(Claude Docs guide)를 호출할 수 있는지
2) blocked x2: env ENABLE_CLAUDEAI_MCP_SERVERS=false 로 같은 데모 과제 실행

실행: python -m src.agent.exp_connectors
"""
import asyncio
import dataclasses
import json
import tempfile
from pathlib import Path

from . import runner_agent
from .config import HarnessConfig
from .day3_demo import PROMPT, grader, make_fixtures
from .runner_agent import RAW_DIR, result_path, run_task

CUSTOM = {"mcp__t__search_text", "mcp__t__file_stats", "mcp__t__check_result"}
BUILTIN = {"Read", "Write", "Edit", "Glob", "Grep"}
PROBE = ("Call the tool named mcp__claude_ai_Claude_Docs__guide (no arguments needed if possible) and tell me "
         "exactly what happened: did the call succeed, or was it denied or unavailable?")

_orig_build = runner_agent.build_options


def with_env(env: dict[str, str]):
    def build(cfg, workdir):
        return dataclasses.replace(_orig_build(cfg, workdir), env=env)
    return build


def read_log(p: Path):
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()]


def init_tools(rows) -> list[str]:
    for r in rows:
        if r["kind"] == "message" and r["message"]["_type"] == "SystemMessage" and r["message"]["subtype"] == "init":
            return r["message"]["data"]["tools"]
    return []


def requests(rows):
    """message_id별 (create, read) — 중복 제거한 API 요청 목록."""
    seen, out = set(), []
    for r in rows:
        if r["kind"] == "message" and r["message"]["_type"] == "AssistantMessage":
            m = r["message"]
            key = m.get("message_id") or m.get("uuid")
            u = m.get("usage") or {}
            sig = (key, u.get("cache_creation_input_tokens"), u.get("cache_read_input_tokens"))
            if sig not in seen:
                seen.add(sig)
                out.append((u.get("cache_creation_input_tokens"), u.get("cache_read_input_tokens")))
    return out


async def one(label: str, prompt: str, cfg: HarnessConfig, fx: Path, run: int) -> None:
    p = result_path("conn", cfg, label, run, RAW_DIR)
    s = await run_task(prompt, cfg, log_path=p, task_id=label, fixtures_dir=fx, grader=grader if label != "probe" else None)
    rows = read_log(p)
    tools = init_tools(rows)
    extra = [t for t in tools if t not in CUSTOM and t not in BUILTIN]
    servers = []
    for r in rows:
        if r["kind"] == "message" and r["message"]["_type"] == "SystemMessage" and r["message"]["subtype"] == "init":
            servers = [(x["name"], x["status"], x.get("source")) for x in r["message"]["data"]["mcp_servers"]]
    u = s["usage"] or {}
    print(f"\n=== {label} run{run} ===")
    print(f"init tools total={len(tools)} custom={len(CUSTOM & set(tools))} builtin={len(BUILTIN & set(tools))} other={len(extra)}")
    print("mcp_servers:", servers)
    print(f"requests(create,read): {requests(rows)}")
    print(f"total create={u.get('cache_creation_input_tokens')} read={u.get('cache_read_input_tokens')} out={u.get('output_tokens')} "
          f"cost=${s['total_cost_usd']:.4f} turns={s['num_turns']} graded={s['graded']} exc={s['exception']}")
    print("tool_calls:", [b["name"] for r in rows if r["kind"] == "message" and r["message"]["_type"] == "AssistantMessage"
                          for b in r["message"]["content"] if b["_type"] == "ToolUseBlock"])
    for r in rows:
        if r["kind"] == "message" and r["message"]["_type"] == "UserMessage":
            for b in r["message"]["content"]:
                if isinstance(b, dict) and b.get("_type") == "ToolResultBlock":
                    print("tool_result:", str(b.get("content"))[:160].replace("\n", " "), "| is_error =", b.get("is_error"))
    print("final:", (s["result"] or "")[:300].replace("\n", " "))
    if label == "probe":
        print("FULL INIT TOOL LIST:")
        print(json.dumps(tools, ensure_ascii=False))


async def main() -> None:
    cfg = HarnessConfig()
    with tempfile.TemporaryDirectory() as fx:
        fxp = Path(fx)
        make_fixtures(fxp)
        runner_agent.build_options = _orig_build
        await one("probe", PROBE, cfg, fxp, 1)
        runner_agent.build_options = with_env({"ENABLE_CLAUDEAI_MCP_SERVERS": "false"})
        for i in (1, 2):
            await one("blocked", PROMPT, cfg, fxp, i)


if __name__ == "__main__":
    asyncio.run(main())
