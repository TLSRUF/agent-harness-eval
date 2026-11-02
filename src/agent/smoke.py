"""Day 1 스모크 테스트: 커스텀 도구 1개 호출 왕복 + 사용량 필드 출력."""
import asyncio
import tempfile
from typing import Any

from claude_agent_sdk import (
    AssistantMessage, ClaudeAgentOptions, ResultMessage, ToolResultBlock,
    ToolUseBlock, create_sdk_mcp_server, query, tool,
)

from .config import HarnessConfig


@tool("char_count", "Return the number of characters in the given text.", {"text": str})
async def char_count(args: dict[str, Any]) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": str(len(args["text"]))}]}


async def main() -> None:
    cfg = HarnessConfig(max_turns=5)
    server = create_sdk_mcp_server(name="t", version="1.0.0", tools=[char_count])
    with tempfile.TemporaryDirectory() as workdir:
        options = ClaudeAgentOptions(
            model=cfg.model,
            cwd=workdir,
            max_turns=cfg.max_turns,
            tools=[],  # 내장 도구 비활성
            mcp_servers={"t": server},
            allowed_tools=["mcp__t__char_count"],
            permission_mode="dontAsk",
            setting_sources=[],
            system_prompt="Use the provided tool to answer. Be brief.",
        )
        async for m in query(prompt="How many characters are in 'harness'? Use the tool.", options=options):
            if isinstance(m, AssistantMessage):
                for b in m.content:
                    if isinstance(b, ToolUseBlock):
                        print("TOOL_USE:", b.name, b.input)
            elif hasattr(m, "content") and isinstance(m.content, list):
                for b in m.content:
                    if isinstance(b, ToolResultBlock):
                        print("TOOL_RESULT:", b.content, "is_error=", b.is_error)
            if isinstance(m, ResultMessage):
                print("ANSWER:", m.result)
                print("subtype:", m.subtype, "terminal:", m.terminal_reason, "turns:", m.num_turns)
                print("duration_ms:", m.duration_ms, "cost_usd:", m.total_cost_usd)
                print("usage:", m.usage)
                print("model_usage:", m.model_usage)


if __name__ == "__main__":
    asyncio.run(main())
