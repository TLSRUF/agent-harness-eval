"""캐시 원인 실험 (호출 4회). 러너는 바꾸지 않는다.

A: 고정 cwd (실행 전 내용만 비우고 fixtures 재복사) 연속 2회
B: 실행마다 다른 임시 폴더 (run_task 그대로) 연속 2회
지표: 각 실행의 '첫 API 호출'(첫 AssistantMessage.usage)의 cache_read / cache_creation.

실행: python -m src.agent.exp_cache <고정폴더경로>
"""
import asyncio
import json
import shutil
import sys
import time
from pathlib import Path

from claude_agent_sdk import AssistantMessage, RateLimitEvent, ResultMessage, query

from .config import HarnessConfig
from .day3_demo import PROMPT, grader, make_fixtures
from .ratelimit import extract_windows
from .runner_agent import RAW_DIR, TrajectoryWriter, build_options, result_path, run_task, to_jsonable


def first_call_usage(log: Path) -> dict:
    for line in log.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r["kind"] == "message" and r["message"]["_type"] == "AssistantMessage":
            u = r["message"].get("usage") or {}
            return {"in": u.get("input_tokens"), "cache_create": u.get("cache_creation_input_tokens"),
                    "cache_read": u.get("cache_read_input_tokens")}
    return {}


async def run_fixed(fixed: Path, cfg: HarnessConfig, log_path: Path, fx: Path) -> dict:
    """고정 폴더에서 1회 실행 (러너 로직과 같은 옵션 사용)."""
    if fixed.exists():
        shutil.rmtree(fixed)
    shutil.copytree(fx, fixed)
    log = TrajectoryWriter(log_path)
    log.write("config", task_id="cache-fixed", config=cfg.to_dict(), prompt=PROMPT, cwd=str(fixed))
    s = {"rate_limit_events": []}
    t0 = time.monotonic()
    async for m in query(prompt=PROMPT, options=build_options(cfg, fixed.resolve())):
        log.write("message", message=to_jsonable(m))
        if isinstance(m, RateLimitEvent):
            snap = extract_windows(m.rate_limit_info)
            snap["elapsed_ms"] = int((time.monotonic() - t0) * 1000)
            s["rate_limit_events"].append(snap)
        if isinstance(m, ResultMessage):
            s.update(subtype=m.subtype, num_turns=m.num_turns, total_cost_usd=m.total_cost_usd, usage=m.usage)
    s["graded"] = grader(fixed)
    log.write("summary", **s)
    log.close()
    return s


def row(label: str, s: dict, first: dict) -> None:
    u = s.get("usage") or {}
    print(f"{label:<14} first[in={first.get('in')} create={first.get('cache_create')} read={first.get('cache_read')}] "
          f"total[create={u.get('cache_creation_input_tokens')} read={u.get('cache_read_input_tokens')} out={u.get('output_tokens')}] "
          f"cost=${s.get('total_cost_usd'):.4f} turns={s.get('num_turns')} graded={s.get('graded')} rl={[(e['five_hour'], e['seven_day']) for e in s['rate_limit_events']]}")


async def main(fixed_dir: str) -> None:
    fixed = Path(fixed_dir)
    fx = fixed.parent / "cache_fx"
    if fx.exists():
        shutil.rmtree(fx)
    fx.mkdir(parents=True)
    make_fixtures(fx)
    cfg = HarnessConfig()
    for i in (1, 2):
        p = result_path("cacheA", cfg, "fixedCwd", i, RAW_DIR)
        s = await run_fixed(fixed, cfg, p, fx)
        row(f"A fixed run{i}", s, first_call_usage(p))
    for i in (1, 2):
        p = result_path("cacheB", cfg, "tempCwd", i, RAW_DIR)
        s = await run_task(PROMPT, cfg, log_path=p, task_id="cache-temp", fixtures_dir=fx, grader=grader)
        row(f"B temp  run{i}", s, first_call_usage(p))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
