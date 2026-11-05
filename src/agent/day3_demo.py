"""Day 3 시연: 임의 과제 1개를 끝까지 실행하고 trajectory를 남긴다 (호출 3회).

실행: python -m src.agent.day3_demo
로그는 results/raw/ (gitignore 대상)에 저장된다.
"""
import asyncio
import tempfile
from pathlib import Path

from .config import HarnessConfig
from .runner_agent import RAW_DIR, result_path, run_task

PROMPT = (
    "In this folder, find which file contains the word ERROR and count its lines with file_stats. "
    "Write a file named summary.txt containing '<filename>: <line count> lines'. "
    "Then verify it with check_result."
)


def make_fixtures(root: Path) -> None:
    (root / "app.log").write_text("INFO start\nERROR disk full\nINFO retry\nINFO done\n", encoding="utf-8")
    (root / "notes.txt").write_text("all good here\nnothing to see\n", encoding="utf-8")


def grader(workdir: Path) -> dict:
    p = workdir / "summary.txt"
    ok = p.is_file() and "app.log" in p.read_text(encoding="utf-8") and "4" in p.read_text(encoding="utf-8")
    return {"passed": ok}


async def main() -> None:
    with tempfile.TemporaryDirectory() as fx:
        fxp = Path(fx)
        make_fixtures(fxp)
        cases = [
            ("normal", HarnessConfig(), 1),
            ("maxturns1", HarnessConfig(max_turns=1), 1),
            ("normal", HarnessConfig(), 2),  # 캐시 재사용 확인용 반복
        ]
        for name, cfg, run in cases:
            path = result_path("day3demo", cfg, name, run, RAW_DIR)
            s = await run_task(PROMPT, cfg, log_path=path, task_id="demo", fixtures_dir=fxp, grader=grader)
            u = s["usage"] or {}
            print(f"[{name} run{run}] subtype={s['subtype']} terminal={s['terminal_reason']} turns={s['num_turns']} "
                  f"tools={s['tool_calls']} tool_err={s['tool_errors']} graded={s['graded']} exc={s['exception']}")
            print(f"    cost=${s['total_cost_usd']} in={u.get('input_tokens')} out={u.get('output_tokens')} "
                  f"cache_create={u.get('cache_creation_input_tokens')} cache_read={u.get('cache_read_input_tokens')} "
                  f"api_ms={s['duration_ms']} -> {path}")


if __name__ == "__main__":
    asyncio.run(main())
