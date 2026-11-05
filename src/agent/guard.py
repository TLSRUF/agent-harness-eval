"""런타임 가드: 에이전트가 보는 도구/서버가 허용 목록과 다르면 실행을 중단한다.

한계(실측): init 메시지의 tools/mcp_servers는 계정 커넥터가 로드되어 있어도 8개만 보이는 경우가 대부분이었다
(14회 중 13회). 그래서 init 검사만으로는 커넥터 노출을 못 잡을 수 있다. 배치 시작 전 preflight_check()가
get_mcp_status()로 서버 목록을 직접 확인한다 (모델 호출 없음).
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable

from .config import HarnessConfig
from .tools import ALLOWED_CUSTOM, SERVER_NAME


class ToolGuardError(RuntimeError):
    """허용되지 않은 도구/서버가 감지되어 실행을 중단했다."""


def allowed_tool_names(cfg: HarnessConfig) -> list[str]:
    return sorted(set(ALLOWED_CUSTOM) | set(cfg.builtin_tools))


def tools_digest(names: Iterable[str]) -> dict:
    """정렬된 도구 이름 목록의 sha256과 개수."""
    ordered = sorted(names)
    return {"sha256": hashlib.sha256("\n".join(ordered).encode("utf-8")).hexdigest(), "count": len(ordered)}


def unexpected_tools(observed: Iterable[str], cfg: HarnessConfig) -> list[str]:
    """허용 목록에 없는 이름 (정렬). 허용된 이름이 빠져 있는 것은 위반으로 보지 않는다."""
    return sorted(set(observed) - set(allowed_tool_names(cfg)))


def check_init_tools(observed: Iterable[str], cfg: HarnessConfig) -> None:
    extra = unexpected_tools(observed, cfg)
    if extra:
        raise ToolGuardError(f"unexpected tools in init message: {extra}")


def check_mcp_status(servers: list[dict]) -> None:
    """get_mcp_status()['mcpServers'] 검사: 우리 서버(SERVER_NAME)만 허용."""
    extra = sorted(s.get("name", "?") for s in servers if s.get("name") != SERVER_NAME)
    if extra:
        raise ToolGuardError(f"unexpected MCP servers: {extra}")


async def preflight_check(cfg: HarnessConfig, workdir: Path | None = None) -> dict:
    """배치 시작 전 1회: CLI만 띄워 서버 목록과 MCP 도구 토큰을 확인한다 (모델 호출 없음).

    위반이면 ToolGuardError. 통과하면 {"servers": [...], "mcp_tool_tokens": int}를 반환한다.
    """
    import tempfile
    from claude_agent_sdk import ClaudeSDKClient
    from .runner_agent import build_options

    with tempfile.TemporaryDirectory(prefix="preflight_") as td:
        wd = Path(workdir or td).resolve()
        async with ClaudeSDKClient(options=build_options(cfg, wd)) as client:
            import asyncio
            await asyncio.sleep(3)  # 커넥터가 있다면 연결될 시간을 준다
            status = await client.get_mcp_status()
            servers = status["mcpServers"]
            check_mcp_status(servers)
            usage = await client.get_context_usage()
    mcp = next((c.get("tokens") for c in usage.get("categories", []) if c.get("name") == "MCP tools"), None)
    return {"servers": [s["name"] for s in servers], "mcp_tool_tokens": mcp}
