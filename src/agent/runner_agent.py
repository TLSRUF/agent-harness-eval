"""에이전트 1회 실행 래퍼. 과제별 임시 폴더, 샌드박스, trajectory jsonl 로깅을 담당한다."""
from __future__ import annotations

import dataclasses
import json
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from claude_agent_sdk import (
    ClaudeAgentOptions, ClaudeSDKError, RateLimitEvent, ResultMessage, ToolResultBlock, ToolUseBlock, query,
)

from .config import HarnessConfig
from .ratelimit import extract_windows
from .tools import ALLOWED_CUSTOM, SERVER_NAME, build_server, sandbox_hooks

RESULTS_DIR = Path("results")
RAW_DIR = RESULTS_DIR / "raw"  # 개발용 임시 로그 (gitignore 대상)


def result_path(experiment: str, cfg: HarnessConfig, config_name: str, run: int, results_dir: Path = RESULTS_DIR) -> Path:
    """results/{실험}_{모델}_{설정}_{반복번호}.jsonl"""
    return Path(results_dir) / f"{experiment}_{cfg.model_short}_{config_name}_run{run}.jsonl"


def to_jsonable(obj: Any) -> Any:
    """SDK 메시지/블록(dataclass)을 JSON 직렬화 가능한 dict로 바꾼다."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        d = {"_type": type(obj).__name__}
        for f in dataclasses.fields(obj):
            d[f.name] = to_jsonable(getattr(obj, f.name))
        return d
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


class TrajectoryWriter:
    """한 줄에 이벤트 하나. 줄마다 flush해서 중단되어도 기록이 남는다."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._f = self.path.open("a", encoding="utf-8", newline="\n")
        self._t0 = time.monotonic()

    def write(self, kind: str, **fields: Any) -> None:
        rec = {
            "kind": kind,
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "elapsed_ms": int((time.monotonic() - self._t0) * 1000),
            **fields,
        }
        self._f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        self._f.flush()

    def close(self) -> None:
        self._f.close()


def build_options(cfg: HarnessConfig, workdir: Path) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        model=cfg.model,
        cwd=str(workdir),
        max_turns=cfg.max_turns,
        system_prompt=cfg.system_prompt,
        tools=list(cfg.builtin_tools),
        mcp_servers={SERVER_NAME: build_server(workdir, cfg.tool_desc_version)},
        allowed_tools=list(cfg.builtin_tools) + ALLOWED_CUSTOM,
        permission_mode="dontAsk",
        setting_sources=[],
        hooks=sandbox_hooks(workdir),
    )


async def run_task(
    prompt: str,
    cfg: HarnessConfig,
    *,
    log_path: Path,
    task_id: str = "adhoc",
    fixtures_dir: Path | None = None,
    grader: Callable[[Path], Any] | None = None,
) -> dict[str, Any]:
    """과제 1개를 실행하고 요약 dict를 반환한다. 모든 이벤트는 log_path(jsonl)에 기록된다.

    grader가 있으면 임시 폴더가 지워지기 전에 grader(workdir)를 호출해 결과를 기록한다.
    """
    log = TrajectoryWriter(log_path)
    summary: dict[str, Any] = {
        "task_id": task_id, "subtype": None, "is_error": None, "terminal_reason": None, "num_turns": None,
        "duration_ms": None, "total_cost_usd": None, "usage": None, "tool_calls": 0, "tool_errors": 0,
        "result": None, "exception": None, "graded": None,
        "rate_limit_events": [],  # 구독 전체 사용률 스냅샷(오염 가능). 델타는 ratelimit.delta 참고
    }
    t0 = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="task_") as td:
        workdir = Path(td).resolve()
        if fixtures_dir is not None:
            shutil.copytree(fixtures_dir, workdir, dirs_exist_ok=True)
        log.write("config", task_id=task_id, config=cfg.to_dict(), prompt=prompt)
        try:
            async for m in query(prompt=prompt, options=build_options(cfg, workdir)):
                log.write("message", message=to_jsonable(m))
                if isinstance(m, RateLimitEvent):
                    snap = extract_windows(m.rate_limit_info)
                    snap["elapsed_ms"] = int((time.monotonic() - t0) * 1000)
                    summary["rate_limit_events"].append(snap)
                content = getattr(m, "content", None)
                if isinstance(content, list):
                    for b in content:
                        if isinstance(b, ToolUseBlock):
                            summary["tool_calls"] += 1
                        elif isinstance(b, ToolResultBlock) and b.is_error is True:
                            summary["tool_errors"] += 1
                if isinstance(m, ResultMessage):
                    summary.update(
                        subtype=m.subtype, is_error=m.is_error, terminal_reason=m.terminal_reason,
                        num_turns=m.num_turns, duration_ms=m.duration_ms, total_cost_usd=m.total_cost_usd,
                        usage=m.usage, result=m.result,
                    )
        except ClaudeSDKError as e:  # ResultError 포함: 오류 결과 뒤 CLI가 비정상 종료한 경우
            summary["exception"] = f"{type(e).__name__}: {e}"
            log.write("exception", type=type(e).__name__, error=str(e))
        except Exception as e:  # 예기치 못한 실패도 기록하고 호출자에게 결과를 돌려준다
            summary["exception"] = f"{type(e).__name__}: {e}"
            log.write("exception", type=type(e).__name__, error=str(e))
        if grader is not None:
            try:
                summary["graded"] = to_jsonable(grader(workdir))
            except Exception as e:
                summary["graded"] = {"grader_error": f"{type(e).__name__}: {e}"}
            log.write("grade", graded=summary["graded"])
    summary["wall_ms"] = int((time.monotonic() - t0) * 1000)
    log.write("summary", **summary)
    log.close()
    return summary
