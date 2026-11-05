"""max_turns 동작 실험 (호출 4회). max_turns = 1, 2, 3, 5 로 같은 과제를 실행한다.

실행: python -m src.agent.exp_maxturns
"""
import asyncio
import json
import tempfile
from pathlib import Path

from .config import HarnessConfig
from .day3_demo import PROMPT, grader, make_fixtures
from .runner_agent import RAW_DIR, result_path, run_task


def api_responses(log: Path) -> int:
    """로그에서 서로 다른 message_id 개수 = 실제 API 응답 수."""
    ids = set()
    for line in log.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r["kind"] == "message" and r["message"]["_type"] == "AssistantMessage":
            ids.add(r["message"].get("message_id") or r["message"].get("uuid"))
    return len(ids)


async def main() -> None:
    with tempfile.TemporaryDirectory() as fx:
        fxp = Path(fx)
        make_fixtures(fxp)
        print("max_turns | num_turns | subtype | terminal_reason | is_error | api_responses | tool_calls | exception | graded | rl(5h,7d)")
        for mt in (1, 2, 3, 5):
            cfg = HarnessConfig(max_turns=mt)
            p = result_path("maxturns", cfg, f"mt{mt}", 1, RAW_DIR)
            s = await run_task(PROMPT, cfg, log_path=p, task_id="maxturns", fixtures_dir=fxp, grader=grader)
            rl = [(e["five_hour"], e["seven_day"]) for e in s["rate_limit_events"]]
            exc = (s["exception"] or "none").split(":")[0]
            print(f"{mt} | {s['num_turns']} | {s['subtype']} | {s['terminal_reason']} | {s['is_error']} | "
                  f"{api_responses(p)} | {s['tool_calls']} | {exc} | {s['graded']} | {rl}")


if __name__ == "__main__":
    asyncio.run(main())
