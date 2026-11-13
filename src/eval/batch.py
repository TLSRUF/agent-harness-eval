"""배치 러너 (터미널에서 직접 실행): 과제 선택, 반복, 이어하기, 시작 전 점검, 한도 감시, 배치 요약.

  python -m src.eval.batch --experiment day7check --tasks H01,H02 --runs 1

순차 실행(동시성 1)이고 오류를 임의로 재시도하지 않는다. 베이스라인 설정(Haiku 5.5, 기본 도구 설명, 검증 없음, max_turns 20)은
config 기본값 그대로 쓴다. 로그는 {실험}_{모델}_{설정}_{과제ID}_run{n}.jsonl (출력 폴더, 기본 results/raw).
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import importlib.metadata
import json
import platform
import re
import shlex
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from claude_agent_sdk import ClaudeAgentOptions, RateLimitEvent, ResultMessage, SystemMessage

from src.agent import guard, runner_agent
from src.agent.config import COMPARE_MODEL, DEFAULT_MODEL, PROMPTS, VARIANT_PROMPTS, ExperimentConfig, HarnessConfig
from src.agent.ratelimit import extract_windows
from src.agent.runner_agent import HARNESS_ENV, TrajectoryWriter, run_task, to_jsonable
from src.agent.tool_outputs import OUTPUT_VARIANTS
from src.agent.tools import SERVER_NAME

from . import freeze, loader, report

ROOT = Path(__file__).resolve().parents[2]
EXIT_OK, EXIT_DECLINED, EXIT_REFUSED, EXIT_STOPPED, EXIT_INTERRUPTED = 0, 1, 2, 3, 130

DEFAULT_FIVE_HOUR_STOP = None  # 임계값 기본값은 비워 둔다. 시험 실행 결과를 보고 사용자가 정한다.
# 설정 이름(파일명용, 밑줄 금지) -> HarnessConfig. 실험 A는 도구 설명만 바꾼다(tool_desc_version). default는 동결된 config 기본값 그대로.
CONFIGS: dict[str, Callable[[], HarnessConfig]] = {
    "default": lambda: HarnessConfig(),
    "short": lambda: HarnessConfig(tool_desc_version="short"),
    "long": lambda: HarnessConfig(tool_desc_version="long"),
    "longDirective": lambda: HarnessConfig(tool_desc_version="long_directive"),
    # 실험 B는 시스템 프롬프트만 바꾼다(prompt_version). 도구 설명은 default
    "verify": lambda: HarnessConfig(prompt_version="verify"),
    "verifyTool": lambda: HarnessConfig(prompt_version="verify_tool"),
    # 실험 C는 max_turns만 바꾼다. 기본값(20)은 config 기본값 그대로 두고 베이스라인이 맡는다
    "maxTurns3": lambda: HarnessConfig(max_turns=3),
    "maxTurns4": lambda: HarnessConfig(max_turns=4),
    "maxTurns5": lambda: HarnessConfig(max_turns=5),
    "maxTurns7": lambda: HarnessConfig(max_turns=7),
    # 실험 E는 long 설정 위에서 file_stats 출력만 바꾼다(비교 기준은 expA의 long)
    "longFilename": lambda: ExperimentConfig(tool_desc_version="long", tool_output_variant="filename"),
}
ALLOWED_MAX_TURNS = (3, 4, 5, 7)                          # 실험 C 후보(응답 수 분포 기준, plan.md)
ALLOWED_MODELS = (DEFAULT_MODEL, COMPARE_MODEL)           # 실험 D: haiku(기본), sonnet
CONFIG_ALIASES = {"long_directive": "longDirective", "verify_tool": "verifyTool", "long_filename": "longFilename"}  # 밑줄 이름은 파일명용 이름으로 바꿔 받는다
RUN_FILE_RE = re.compile(r"^(?P<exp>[A-Za-z0-9]+)_(?P<model>[a-z]+)_(?P<cfg>[A-Za-z0-9]+)_(?P<task>[EMH]\d{2})_run(?P<n>\d+)\.jsonl$")
NAME_RE = re.compile(r"^[A-Za-z0-9]+$")
LIMIT_RE = re.compile(r"rate.?limit|usage limit|limit (reached|exceeded)|hit your .{0,20}limit|quota|overloaded|\b429\b|\b529\b|credit balance", re.I)
RELEVANT_PREFIXES = ("src/", "fixtures/")
RELEVANT_FILES = ("MANIFEST.json",)
UNIT_NOTE = "미확인"  # utilization의 단위(0~1 비율로 보이나 확인되지 않음)와 해상도(0.01 단위로만 관찰)
RESOLUTION, NOISE = 0.01, 0.01
DELTA_FLOOR = RESOLUTION + NOISE  # 두 값의 차이가 이 이하이면 측정 한계 이하일 수 있다(가설: 값마다 ±0.01 노이즈)
TOKEN_KEYS = [("input_tokens", "입력 토큰"), ("output_tokens", "출력 토큰"), ("cache_read_input_tokens", "캐시 읽기 토큰"),
              ("cache_creation_input_tokens", "캐시 생성 토큰")]
DEMO_COST_BOUND = 0.0015  # 5턴 데모 과제 건당 최대(2026-11-05 측정, 커넥터 차단 후 8회). 어려운 과제에는 적용하지 않는다.
DIFFICULTY_LABEL = {"E": "쉬움(E)", "M": "보통(M)", "H": "어려움(H)"}


# ---------------- 기본 의존성 (테스트에서 바꿔 끼운다) ----------------

def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=30)


def default_git_status() -> list[str] | None:
    try:
        r = _git("status", "--porcelain")
        return r.stdout.splitlines() if r.returncode == 0 else None
    except Exception:  # noqa: BLE001
        return None


def default_git_commit() -> str:
    try:
        r = _git("rev-parse", "HEAD")
        return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else "확인 불가"
    except Exception:  # noqa: BLE001
        return "확인 불가"


def default_cli_version() -> str:
    """SDK가 실제로 쓰는 번들 Claude Code CLI의 버전. PATH의 claude와 다를 수 있다(2026-11-10 확인: 번들 2.1.316)."""
    try:
        import claude_agent_sdk
        exe = Path(claude_agent_sdk.__file__).parent / "_bundled" / ("claude.exe" if sys.platform == "win32" else "claude")
        r = subprocess.run([str(exe), "--version"], capture_output=True, text=True, timeout=30)
        return (r.stdout.strip() + " (SDK 번들)") if r.returncode == 0 and r.stdout.strip() else "확인 불가"
    except Exception:  # noqa: BLE001
        return "확인 불가"


@dataclass
class Deps:
    verify_freeze: Callable[[], list[str]] = freeze.verify
    preflight: Callable[..., Any] | None = None
    input_fn: Callable[[str], str] = input
    git_status: Callable[[], list[str] | None] = default_git_status
    git_commit: Callable[[], str] = default_git_commit
    cli_version: Callable[[], str] = default_cli_version


# ---------------- 인자와 선택 ----------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="python -m src.eval.batch", description="평가셋 배치 러너(순차 실행, 동시성 1, 재시도 없음)")
    ap.add_argument("--experiment", required=True, help="실험 이름(영문/숫자만). 예: baseline, day7check")
    sel = ap.add_mutually_exclusive_group(required=True)
    sel.add_argument("--tasks", help="과제 ID 목록(쉼표). 예: E01,H02")
    sel.add_argument("--difficulty", choices=["easy", "medium", "hard"])
    sel.add_argument("--all", action="store_true", help="40개 전체")
    ap.add_argument("--runs", type=int, default=2, help="과제당 반복 횟수(기본 2)")
    ap.add_argument("--config", "--config-name", dest="config", default="default", type=lambda s: CONFIG_ALIASES.get(s, s),
                    help="설정 이름: default, short, long, longDirective(long_directive도 받음), verify, verifyTool(verify_tool도 받음). 실험 A는 도구 설명 변형, 실험 B는 프롬프트 변형")
    ap.add_argument("--prompt-version", dest="prompt_version", default=None,
                    help="시스템 프롬프트 버전: v1, verify, verify_tool. 실험 B. 설정 이름(파일 라벨)은 default/verify/verifyTool로 정해진다. --config-name과 같이 주면 같은 변형이어야 한다")
    ap.add_argument("--max-turns", dest="max_turns", type=int, default=None,
                    help="실험 C: 최대 턴 수(3, 4, 5, 7만). 설정 이름(파일 라벨)은 maxTurnsN. config 기본값 20은 바꾸지 않는다(베이스라인이 20)")
    ap.add_argument("--tool-output-variant", dest="tool_output_variant", default=None,
                    help="실험 E: file_stats 출력 변형(default, filename). filename은 --config-name long과 함께만 쓴다(설정 이름은 longFilename). 다른 변수와 같이 바꿀 수 없다")
    ap.add_argument("--model", dest="model", default=None,
                    help="실험 D: claude-haiku-5-5(기본) 또는 claude-sonnet-5-5만. sonnet이면 파일 이름의 모델 자리가 sonnet이 된다. 다른 변수와 같이 바꿀 수 없다")
    ap.add_argument("--out-dir", default=str(runner_agent.RAW_DIR), help="jsonl과 스냅샷을 둘 폴더(기본 results/raw)")
    ap.add_argument("--results-dir", default=str(runner_agent.RESULTS_DIR), help="요약 파일을 둘 폴더(기본 results)")
    ap.add_argument("--probe", action=argparse.BooleanOptionalAction, default=True, help="시작/끝에 1턴 탐침 호출로 five_hour, seven_day 읽기(기본 켜짐)")
    ap.add_argument("--start-five-hour", type=float, help="수동으로 읽은 시작 five_hour")
    ap.add_argument("--start-seven-day", type=float, help="수동으로 읽은 시작 seven_day")
    ap.add_argument("--five-hour-stop", type=float, default=DEFAULT_FIVE_HOUR_STOP, help="five_hour가 이 값 이상이면 다음 실행 전에 멈춤(기본: 설정 안 함)")
    ap.add_argument("--limits-file", help='JSON {"five_hour_stop": 값}. CLI 인자가 우선')
    ap.add_argument("--yes", action="store_true", help="비용 확인(y/n)을 건너뜀")
    ap.add_argument("--allow-dirty", action="store_true", help="코드/데이터 변경 경고의 y/n 확인을 건너뜀")
    return ap.parse_args(argv)


def resolve_variant(a: argparse.Namespace) -> None:
    """--prompt-version, --max-turns, --config-name을 설정 이름(a.config) 하나로 합친다. --model은 다른 변수와 같이 바꿀 수 없다.

    모르는 값이거나 서로 다른 변형을 동시에 주면 ValueError(한 번에 변수 하나만 바꾼다). 같은 변형을 여러 방법으로 주는 것은 허용한다.
    """
    tov = a.tool_output_variant
    if tov is not None and tov not in OUTPUT_VARIANTS:
        raise ValueError(f"알 수 없는 --tool-output-variant: {tov} (사용 가능: {list(OUTPUT_VARIANTS)})")
    if tov == "filename":
        if a.prompt_version or a.max_turns is not None or a.config not in ("long", "longFilename"):
            raise ValueError("--tool-output-variant filename은 --config-name long과 함께만 쓴다(도구 설명 long 위에서 출력만 바꾼다). "
                             "프롬프트, max_turns, 다른 도구 설명과는 같이 바꿀 수 없다")
        if a.model is not None and a.model != DEFAULT_MODEL:
            raise ValueError("--model은 다른 변수와 같이 바꿀 수 없다(--tool-output-variant filename)")
        a.config = "longFilename"
        return
    if tov == "default" and a.config == "longFilename":
        raise ValueError("--config-name longFilename과 --tool-output-variant default는 서로 다른 변형이다")
    requested: list[tuple[str, str]] = []
    if a.prompt_version:
        pv = a.prompt_version
        if pv not in PROMPTS and pv not in VARIANT_PROMPTS:
            raise ValueError(f"알 수 없는 --prompt-version: {pv} (사용 가능: {['v1', *sorted(VARIANT_PROMPTS)]})")
        requested.append(("--prompt-version " + pv, "default" if pv == "v1" else CONFIG_ALIASES.get(pv, pv)))
    if a.max_turns is not None:
        if a.max_turns not in ALLOWED_MAX_TURNS:
            raise ValueError(f"--max-turns는 {list(ALLOWED_MAX_TURNS)}만 허용한다(받은 값 {a.max_turns}; 기본 20은 베이스라인이 담당)")
        requested.append((f"--max-turns {a.max_turns}", f"maxTurns{a.max_turns}"))
    if a.config != "default":
        requested.append(("--config-name " + a.config, a.config))
    labels = {label for _, label in requested}
    if len(labels) > 1:
        raise ValueError("서로 다른 변형을 한 번에 바꿀 수 없다(한 번에 변수 하나만 바꾼다): " + ", ".join(name for name, _ in requested))
    if a.model is not None:
        if a.model not in ALLOWED_MODELS:
            raise ValueError(f"--model은 {list(ALLOWED_MODELS)}만 허용한다(받은 값 {a.model})")
        if a.model != DEFAULT_MODEL and any(label != "default" for label in labels):
            raise ValueError("--model은 다른 변수(도구 설명, 프롬프트, max_turns)와 같이 바꿀 수 없다: " + ", ".join(name for name, _ in requested))
    if labels:
        a.config = next(iter(labels))


def validate_names(a: argparse.Namespace) -> None:
    for label, v in (("experiment", a.experiment), ("config", a.config)):
        if not NAME_RE.match(v):
            raise ValueError(f"--{label} 이름은 영문/숫자만 쓴다(밑줄, 하이픈 불가: 파일명에서 구분자로 쓰인다): {v!r}")
    if a.runs < 1:
        raise ValueError("--runs는 1 이상")


def select_tasks(a: argparse.Namespace, tasks: list[loader.Task]) -> list[loader.Task]:
    ready = sorted((t for t in tasks if not t.is_todo), key=lambda t: t.id)
    if a.all:
        return ready
    if a.difficulty:
        return [t for t in ready if t.difficulty == a.difficulty]
    ids = [x.strip() for x in a.tasks.split(",") if x.strip()]
    by_id = {t.id: t for t in ready}
    unknown = [i for i in ids if i not in by_id]
    if unknown:
        raise ValueError(f"없는 과제 ID: {unknown}")
    return [by_id[i] for i in sorted(set(ids))]


def resolve_threshold(a: argparse.Namespace) -> float | None:
    value = a.five_hour_stop
    if value is None and a.limits_file:
        value = json.loads(Path(a.limits_file).read_text(encoding="utf-8")).get("five_hour_stop")
    if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0):
        raise ValueError(f"five_hour 임계값은 0보다 큰 숫자여야 한다: {value!r}")
    return value


# ---------------- 파일 이름, 분류, 보관 ----------------

def log_name(experiment: str, model_short: str, config: str, task_id: str, run: int) -> str:
    return f"{experiment}_{model_short}_{config}_{task_id}_run{run}"


def read_events(path: Path) -> list[dict]:
    """jsonl을 읽는다. 강제 종료로 잘린 마지막 줄은 무시한다."""
    out = []
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            break
    return out


def classify_summary(s: dict) -> tuple[str, str | None]:
    """'complete' 또는 'aborted'(+이유). summary가 있어도 ToolGuardError와 한도/API 오류만 중단된 실행이다.

    결과(subtype)가 있으면 예외가 함께 와도 완료다(예: error_max_turns 뒤 CLI 비정상 종료). 한도 문구 판정은 가설이다.
    """
    exc = s.get("exception") or ""
    if exc.startswith("ToolGuardError"):
        return "aborted", exc
    has_result = s.get("subtype") is not None
    if not has_result:
        return "aborted", f"API/한도 오류로 보임(결과 메시지 없음): {exc or '예외 없이 스트림 종료'}"
    if s.get("is_error") and s.get("subtype") != "error_max_turns" and LIMIT_RE.search(str(s.get("result") or "")):
        return "aborted", f"한도/API 오류로 보임(가설, 문구 매칭): {str(s.get('result'))[:120]}"
    return "complete", None


def classify_log(path: Path) -> str:
    """'missing' | 'complete' | 'aborted' | 'incomplete'(summary 없음: Ctrl+C, 강제 종료)."""
    path = Path(path)
    if not path.exists():
        return "missing"
    summaries = [e for e in read_events(path) if e.get("kind") == "summary"]
    return classify_summary(summaries[-1])[0] if summaries else "incomplete"


def archive_run(log_path: Path, snapshot_root: Path) -> int:
    """끝나지 않은 로그와 스냅샷 폴더(_final)를 같은 번호의 .partialN으로 이름을 바꿔 보관한다. 덮어쓰지 않는다."""
    snap = Path(snapshot_root) / f"{log_path.stem}_final"
    k = 1
    while (log_path.with_name(f"{log_path.name}.partial{k}")).exists() or snap.with_name(f"{snap.name}.partial{k}").exists():
        k += 1
    if log_path.exists():
        log_path.rename(log_path.with_name(f"{log_path.name}.partial{k}"))
    if snap.exists():
        snap.rename(snap.with_name(f"{snap.name}.partial{k}"))
    return k


def relevant_dirty(lines: list[str]) -> list[str]:
    """git status --porcelain 줄 중 src/, fixtures/, MANIFEST.json만 골라 경로를 돌려준다(docs, tests, results 등은 경고 대상이 아니다)."""
    paths = []
    for ln in lines:
        path = ln[3:].strip()
        if " -> " in path:
            path = path.split(" -> ")[-1]
        path = path.strip('"')
        if "__pycache__" in path:
            continue
        if path.startswith(RELEVANT_PREFIXES) or path in RELEVANT_FILES:
            paths.append(path)
    return paths


def repro_info(deps: Deps, dirty_paths: list[str] | None) -> dict:
    """config 이벤트의 repro 필드. model, max_turns, 프롬프트/도구 설명 버전은 config에 이미 있어 중복하지 않는다."""
    return {
        "git_commit": deps.git_commit(),
        "git_dirty": None if dirty_paths is None else bool(dirty_paths),
        "git_dirty_paths": dirty_paths,
        "manifest_sha256": freeze.sha256_file(freeze.MANIFEST_PATH, normalize_newlines=True),
        "sdk_version": importlib.metadata.version("claude-agent-sdk"),
        "cli_version": deps.cli_version(),
        "python_version": platform.python_version(),
        "os": platform.platform(),
    }


def measured_cost_bounds(out_dir: Path, model: str | None = None) -> dict[str, dict]:
    """배치 규칙 이름의 로그에서 난이도(E/M/H)별 건당 비용 최댓값과 건수. 보관/탐침/옛 규칙 파일은 제외한다.
    model(파일 이름의 모델 약칭)을 주면 그 모델의 로그만 쓴다(다른 모델의 측정값을 상한으로 빌리지 않기 위해)."""
    best: dict[str, dict] = {}
    for f in sorted(Path(out_dir).glob("*.jsonl")):
        m = RUN_FILE_RE.match(f.name)
        if not m or (model is not None and m["model"] != model):
            continue
        sums = [e for e in read_events(f) if e.get("kind") == "summary"]
        cost = sums[-1].get("total_cost_usd") if sums else None
        if cost is None:
            continue
        d = best.setdefault(m["task"][0], {"max": cost, "n": 0})
        d["max"], d["n"] = max(d["max"], cost), d["n"] + 1
    return best


# ---------------- 탐침 ----------------

async def run_probe(log_path: Path) -> dict:
    """가장 저렴한 설정(Haiku, 도구 없음, 1턴)의 짧은 호출로 five_hour, seven_day를 읽는다. 베이스라인 결과에 포함하지 않는다."""
    log = TrajectoryWriter(log_path)
    out: dict[str, Any] = {"five_hour": None, "seven_day": None, "status": None, "cost": None, "error": None}
    cfg = HarnessConfig()
    try:
        with tempfile.TemporaryDirectory(prefix="probe_") as td:
            opts = ClaudeAgentOptions(env=dict(HARNESS_ENV), model=DEFAULT_MODEL, cwd=str(Path(td).resolve()), max_turns=1, tools=[],
                                      allowed_tools=[], system_prompt="Reply with the single word OK.", permission_mode="dontAsk",
                                      setting_sources=[])
            log.write("config", task_id="probe", purpose="한도 탐침(베이스라인 결과 아님)", model=DEFAULT_MODEL)
            async with contextlib.aclosing(runner_agent.query(prompt="OK?", options=opts)) as stream:
                async for m in stream:
                    log.write("message", message=to_jsonable(m))
                    if isinstance(m, SystemMessage) and m.subtype == "init":
                        extra = guard.unexpected_tools(list(m.data.get("tools", [])), cfg)
                        if extra:
                            raise guard.ToolGuardError(f"probe: unexpected tools in init message: {extra}")
                    if isinstance(m, RateLimitEvent):
                        w = extract_windows(m.rate_limit_info)
                        out.update(five_hour=w["five_hour"], seven_day=w["seven_day"], status=w["status"])
                    if isinstance(m, ResultMessage):
                        out["cost"] = m.total_cost_usd
    except guard.ToolGuardError:
        log.write("summary", **out, error="ToolGuardError")
        log.close()
        raise
    except Exception as e:  # noqa: BLE001  탐침 실패는 배치를 막지 않고 기록만 한다
        out["error"] = f"{type(e).__name__}: {e}"
    log.write("summary", **out)
    log.close()
    return out


# ---------------- 배치 상태와 실행 ----------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _append(path: Path, rec: dict) -> None:
    with Path(path).open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps({"ts": _now(), **rec}, ensure_ascii=False, default=str) + "\n")
        f.flush()


@dataclass
class Ctx:
    a: argparse.Namespace
    cfg: HarnessConfig
    out_dir: Path
    summary_path: Path
    invocation: int
    repro: dict
    threshold: float | None
    work: list[tuple[loader.Task, int]]
    probe_end_allowed: bool = True
    stop_reason: str | None = None
    start: dict = field(default_factory=lambda: {"five_hour": None, "seven_day": None, "source": None, "note": ""})
    first_event: dict | None = None
    last_event: dict | None = None
    five_obs: list[float] = field(default_factory=list)
    seven_obs: list[float] = field(default_factory=list)
    new_done: int = 0
    last_resets_at: Any = None


def _observe(ctx: Ctx, w: dict) -> None:
    if w.get("five_hour") is not None:
        ctx.five_obs.append(w["five_hour"])
    if w.get("seven_day") is not None:
        ctx.seven_obs.append(w["seven_day"])


def _range(vals: list[float]) -> list[float] | None:
    return [min(vals), max(vals)] if vals else None


def _check_limit(ctx: Ctx, five: float | None, statuses: list[Any]) -> str | None:
    """allowed 외의 문자열 status는 모두 멈춤(가설: SDK 문서상 값은 allowed, allowed_warning, rejected). None은 판단하지 않는다."""
    bad = sorted({s for s in statuses if isinstance(s, str) and s != "allowed"})
    if bad:
        return f"한도 신호: RateLimitEvent status={bad} (allowed 외에는 모두 멈춤, 가설)"
    if ctx.threshold is not None and five is not None and five >= ctx.threshold:
        return f"한도 임계 도달: five_hour={five} >= 임계 {ctx.threshold} (utilization 단위 {UNIT_NOTE})"
    return None


async def _execute(ctx: Ctx, deps: Deps) -> None:
    a, out_dir = ctx.a, ctx.out_dir
    model = ctx.cfg.model_short
    if a.probe:
        ctx.start.update(source="probe")
        res = await run_probe(out_dir / f"probe_{model}_{a.experiment}-{a.config}_inv{ctx.invocation}_start.jsonl")
        if res["five_hour"] is not None or res["seven_day"] is not None:
            ctx.start.update(five_hour=res["five_hour"], seven_day=res["seven_day"], note="탐침 호출(1턴, 도구 없음)로 읽음")
            _observe(ctx, res)
        else:
            ctx.start.update(source=None, note=f"탐침에서 한도 값을 얻지 못함({res['error'] or 'RateLimitEvent 없음'})")
    if ctx.start["source"] is None and (a.start_five_hour is not None or a.start_seven_day is not None):
        ctx.start.update(source="manual", five_hour=a.start_five_hour, seven_day=a.start_seven_day, note="사용자가 수동으로 읽은 값")
    if ctx.start["source"] is None:
        ctx.start.update(source="first_event", note="첫 실행 중 처음 관찰된 값이라 첫 실행에서 쓴 양이 델타에서 빠진다(미확인)")
    _append(ctx.summary_path, {"kind": "batch_start", "batch": f"{a.experiment}_{model}_{a.config}", "invocation": ctx.invocation,
                               "argv": sys.argv[1:] if not hasattr(a, "_argv") else a._argv, "planned_runs": len(ctx.work),
                               "threshold_five_hour": ctx.threshold, "utilization_unit": UNIT_NOTE, "repro": ctx.repro, **ctx.start})
    pre = _check_limit(ctx, ctx.start["five_hour"], [])
    if pre:
        ctx.stop_reason = pre if len(ctx.work) else None
        return
    for i, (task, run) in enumerate(ctx.work):
        log_path = out_dir / f"{log_name(a.experiment, model, a.config, task.id, run)}.jsonl"
        if log_path.exists():
            archive_run(log_path, out_dir)
        print(f"[{i + 1}/{len(ctx.work)}] {task.id} run{run} 실행 중...", flush=True)
        guard_msg = None
        try:
            summary = await run_task(task.prompt, ctx.cfg, log_path=log_path, task_id=task.id, fixtures_dir=task.fixture_dir,
                                     grader=loader.resolve_grader(task), outputs=task.outputs, snapshot_root=out_dir, config_extra=ctx.repro)
        except guard.ToolGuardError as e:
            guard_msg = f"ToolGuardError: {e}"
            sums = [x for x in read_events(log_path) if x.get("kind") == "summary"]
            summary = sums[-1] if sums else {"task_id": task.id, "exception": guard_msg, "rate_limit_events": []}
        status, reason = classify_summary(summary)
        events = summary.get("rate_limit_events") or []
        for w in events:
            _observe(ctx, w)
            ctx.first_event = ctx.first_event or w
        if events:
            ctx.last_event = events[-1]
            ctx.last_resets_at = events[-1].get("resets_at") or ctx.last_resets_at
        last = events[-1] if events else {}
        graded = summary.get("graded") or {}
        _append(ctx.summary_path, {
            "kind": "run", "invocation": ctx.invocation, "task_id": task.id, "run": run, "file": log_path.name, "status": status, "reason": reason,
            "passed": graded.get("passed"), "failure_type": graded.get("failure_type"), "num_turns": summary.get("num_turns"),
            "total_cost_usd": summary.get("total_cost_usd"), "usage": summary.get("usage"), "rate_limit_status": last.get("status"),
            "five_hour": last.get("five_hour"), "seven_day": last.get("seven_day"),
            "observed_five_hour_range": _range(ctx.five_obs), "observed_seven_day_range": _range(ctx.seven_obs), "utilization_unit": UNIT_NOTE})
        ctx.new_done += 1
        remaining = len(ctx.work) - (i + 1)
        if status == "aborted":
            ctx.stop_reason = f"중단된 실행({task.id} run{run}): {reason}"
            ctx.probe_end_allowed = False
            return
        stop = _check_limit(ctx, last.get("five_hour"), [e.get("status") for e in events])
        if stop:
            ctx.stop_reason = stop if remaining else None
            ctx.probe_end_allowed = not any(isinstance(e.get("status"), str) and e.get("status") != "allowed" for e in events)
            if remaining:
                return
            print(f"참고: 마지막 실행 뒤 {stop} (남은 실행 없음)")
    if a.probe and ctx.probe_end_allowed:
        res = await run_probe(out_dir / f"probe_{model}_{a.experiment}-{a.config}_inv{ctx.invocation}_end.jsonl")
        ctx.end_probe = res


def _delta(a: float | None, b: float | None) -> float | None:
    return None if a is None or b is None else round(b - a, 6)


def _delta_text(d: float | None) -> str:
    if d is None:
        return "측정 불가"
    t = f"{d:+.2f}"
    return t + (" (측정 한계 이하일 수 있음)" if abs(d) <= DELTA_FLOOR + 1e-9 else "")


def _finalize_window(ctx: Ctx) -> dict:
    """배치 시작/끝 값과 출처. 시작값이 first_event이면 첫 이벤트, 끝값은 탐침이 없으면 마지막 이벤트."""
    start = dict(ctx.start)
    if start["source"] == "first_event" and ctx.first_event:
        start.update(five_hour=ctx.first_event.get("five_hour"), seven_day=ctx.first_event.get("seven_day"))
    probe = getattr(ctx, "end_probe", None)
    if probe and (probe["five_hour"] is not None or probe["seven_day"] is not None):
        end = {"five_hour": probe["five_hour"], "seven_day": probe["seven_day"], "source": "probe"}
    elif ctx.last_event:
        end = {"five_hour": ctx.last_event.get("five_hour"), "seven_day": ctx.last_event.get("seven_day"), "source": "last_event"}
    else:
        end = {"five_hour": None, "seven_day": None, "source": None}
    return {"start": start, "end": end,
            "delta": {"five_hour": _delta(start["five_hour"], end["five_hour"]), "seven_day": _delta(start["seven_day"], end["seven_day"])}}


# ---------------- 요약 ----------------

def _collect(out_dir: Path, a: argparse.Namespace, model: str, selection: list[tuple[loader.Task, int]]) -> list[dict]:
    rows = []
    for task, run in selection:
        p = out_dir / f"{log_name(a.experiment, model, a.config, task.id, run)}.jsonl"
        state = classify_log(p)
        row = {"task": task, "run": run, "path": p, "state": state, "summary": None}
        if state == "complete":
            row["summary"] = [e for e in read_events(p) if e.get("kind") == "summary"][-1]
        rows.append(row)
    return rows


def build_summary(ctx: Ctx, reason: str | None, selection: list[tuple[loader.Task, int]], window: dict, interrupted: bool) -> str:
    a, model = ctx.a, ctx.cfg.model_short
    rows = _collect(ctx.out_dir, a, model, selection)
    done = [r for r in rows if r["state"] == "complete"]
    graded = [r["summary"].get("graded") or {} for r in done]
    passed = sum(1 for g in graded if g.get("passed") is True)
    failed = sum(1 for g in graded if g.get("passed") is False)
    ungraded = len(done) - passed - failed
    aborted = sum(1 for r in rows if r["state"] in ("aborted", "incomplete"))
    missing = sum(1 for r in rows if r["state"] == "missing")
    ftypes: dict[str, int] = {}
    for g in graded:
        if g.get("failure_type"):
            ftypes[g["failure_type"]] = ftypes.get(g["failure_type"], 0) + 1
    turns = [r["summary"].get("num_turns") for r in done if r["summary"].get("num_turns") is not None]
    cost = sum(r["summary"].get("total_cost_usd") or 0 for r in done)
    tokens = {k: sum((r["summary"].get("usage") or {}).get(k, 0) or 0 for r in done) for k, _ in TOKEN_KEYS}
    L = [f"# 배치 요약: {a.experiment} / {ctx.cfg.model_short} / {a.config} (호출 {ctx.invocation}번째)", "",
         f"- 선택: 과제 {len({r['task'].id for r in rows})}개 x 반복 {a.runs} = {len(rows)}회. 이번 호출에서 새로 끝낸 실행 {ctx.new_done}회",
         f"- 종료 사유: {'정상 완료' if reason is None else reason}" + (" (사용자 중단)" if interrupted else ""), "",
         "## 결과", "| 항목 | 값 |", "|---|---|", f"| 통과 | {passed} |", f"| 실패 | {failed} |", f"| 채점 없음 | {ungraded} |",
         f"| 중단된 실행 | {aborted} |", f"| 미실행 | {missing} |"]
    L += [f"| failure_type: {k} | {v} |" for k, v in sorted(ftypes.items())]
    L += [f"| 평균 턴 수 | {sum(turns) / len(turns):.1f} |" if turns else "| 평균 턴 수 | n/a |"]
    L += [f"| {label} | {tokens[k]} |" for k, label in TOKEN_KEYS]
    L += [f"| 정가 환산 비용 합계 | ${cost:.4f} |", "",
          "비용은 정가 환산 추정치이며 구독 한도 소모와는 별개다. 중단된 실행은 실패가 아니므로 통과/실패에 넣지 않았다.", "",
          "## 배치 델타 (이번 호출, 구독 전체 사용량이라 다른 사용이 섞일 수 있음)", "| 창 | 시작 | 끝 | 델타 |", "|---|---|---|---|"]
    for k in ("five_hour", "seven_day"):
        s, e = window["start"][k], window["end"][k]
        L.append(f"| {k} | {s if s is not None else '-'} ({window['start']['source'] or '없음'}) | {e if e is not None else '-'} ({window['end']['source'] or '없음'}) | {_delta_text(window['delta'][k])} |")
    L += ["", f"- 단위 {UNIT_NOTE}: utilization이 0~1 비율로 보이나 확인되지 않았다. 관찰된 해상도는 0.01 단위, 값마다 ±0.01 노이즈가 관찰됐다. "
              f"관찰 범위: five_hour {_range(ctx.five_obs)}, seven_day {_range(ctx.seven_obs)}",
          f"- 시작값 출처: {window['start']['note'] or '-'}", "- 과제 단위 델타는 쓰지 않는다(해상도와 잡음 때문). 배치 단위로만 본다.", ""]
    runs = [report.load_run(r["path"]) for r in done]
    if runs:
        tasks = [t for t, _ in selection]
        overlap = {t.id: t.overlap_with for t in tasks}
        min_steps = {t.id: t.min_steps for t in tasks}
        L += ["## report.py 출력 (표본 크기 문구 포함)", "", report.build_report(runs, overlap, min_steps)]
    return "\n".join(L) + "\n"


def write_run_csv(path: Path, ctx: Ctx, selection: list[tuple[loader.Task, int]]) -> None:
    """runs.csv는 이번 호출의 선택분이 아니라 out-dir의 이 실험/모델/설정 로그 전체에서 매번 다시 만든다(멱등).
    selection은 받지만 쓰지 않는다(호출 형식 유지). .partial 보관본과 다른 실험/설정 로그는 제외한다."""
    import csv
    prefix = f"{ctx.a.experiment}_{ctx.cfg.model_short}_{ctx.a.config}_"
    pat = re.compile(re.escape(prefix) + r"([EMH]\d+)_run(\d+)\.jsonl")
    tasks = {t.id: t for t in loader.load_all()}
    found = []
    for p in Path(ctx.out_dir).glob(prefix + "*.jsonl"):
        m = pat.fullmatch(p.name)
        if m and m.group(1) in tasks:
            found.append((m.group(1), int(m.group(2))))
    rows = _collect(ctx.out_dir, ctx.a, ctx.cfg.model_short, [(tasks[t], n) for t, n in sorted(found)])
    with Path(path).open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["task", "run", "state", "passed", "failure_type", "num_turns", "total_cost_usd"] + [k for k, _ in TOKEN_KEYS])
        for r in rows:
            s = r["summary"] or {}
            g = s.get("graded") or {}
            w.writerow([r["task"].id, r["run"], r["state"], g.get("passed"), g.get("failure_type"), s.get("num_turns"), s.get("total_cost_usd")]
                       + [(s.get("usage") or {}).get(k) for k, _ in TOKEN_KEYS])


# ---------------- 진입점 ----------------

def _ask(deps: Deps, prompt: str) -> str:
    """y/n 입력. 입력이 없으면(EOF) n으로 본다."""
    try:
        return deps.input_fn(prompt).strip().lower()
    except EOFError:
        return "n"


def _restart_command(argv: list[str]) -> str:
    return "python -m src.eval.batch " + shlex.join(argv)


def _plan(out_dir: Path, a: argparse.Namespace, model: str, tasks: list[loader.Task]) -> tuple[list[tuple[loader.Task, int]], dict]:
    selection = [(t, n) for t in tasks for n in range(1, a.runs + 1)]
    work, counts = [], {"complete": 0, "redo": 0, "new": 0}
    for t, n in selection:
        st = classify_log(out_dir / f"{log_name(a.experiment, model, a.config, t.id, n)}.jsonl")
        if st == "complete":
            counts["complete"] += 1
            continue
        counts["redo" if st != "missing" else "new"] += 1
        work.append((t, n))
    return selection, {"selection": selection, "work": work, **counts}


def main(argv: list[str] | None = None, deps: Deps | None = None) -> int:
    deps = deps or Deps()
    argv = list(sys.argv[1:] if argv is None else argv)
    a = parse_args(argv)
    a._argv = argv
    try:
        resolve_variant(a)
        validate_names(a)
        tasks = select_tasks(a, loader.load_all())
        threshold = resolve_threshold(a)
    except (ValueError, OSError) as e:
        print(f"인자 오류: {e}")
        return EXIT_REFUSED
    if a.config not in CONFIGS:
        print(f"알 수 없는 설정 이름: {a.config} (사용 가능: {sorted(CONFIGS)})")
        return EXIT_REFUSED
    cfg = CONFIGS[a.config]()
    if a.model is not None and a.model != cfg.model:
        cfg = replace(cfg, model=a.model)                  # 실험 D: 모델만 바꾼다(HarnessConfig는 frozen이라 새로 만든다)
    model = cfg.model_short
    out_dir, results_dir = Path(a.out_dir), Path(a.results_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)

    # 1) 동결 일치, 2) 에이전트가 볼 수 있는 서버가 t뿐인지
    problems = deps.verify_freeze()
    if problems:
        print("동결 불일치: 실행을 거부한다.\n" + "\n".join(problems))
        return EXIT_REFUSED
    print("동결 일치")
    try:
        info = asyncio.run((deps.preflight or guard.preflight_check)(cfg))
        if set(info.get("servers", [])) - {SERVER_NAME}:
            raise guard.ToolGuardError(f"unexpected MCP servers: {info.get('servers')}")
    except Exception as e:  # noqa: BLE001
        print(f"시작 전 점검 실패: {type(e).__name__}: {e}")
        return EXIT_REFUSED
    print(f"preflight 통과: 서버 {info.get('servers')}")

    # 3) 코드/데이터가 바뀐 채인지 (docs, tests만 바뀐 건 경고하지 않는다)
    lines = deps.git_status()
    dirty = None if lines is None else relevant_dirty(lines)
    if dirty is None:
        print("참고: git 상태를 확인할 수 없다(git_dirty=확인 불가로 기록).")
    elif dirty:
        print("경고: 코드/데이터가 커밋되지 않은 채 바뀌어 있다(결과 재현이 어려울 수 있음): " + ", ".join(dirty))
        if not a.allow_dirty and _ask(deps, "이 상태로 계속하시겠습니까? (y/n): ") != "y":
            print("취소했다.")
            return EXIT_DECLINED

    # 4) 예상 호출 수와 비용 상한, 5) 확인
    selection, plan = _plan(out_dir, a, model, tasks)
    bounds = measured_cost_bounds(out_dir, model)
    probes = 2 if a.probe else 0
    print(f"예상 실행: 과제 {len(tasks)}개 x 반복 {a.runs} = {len(selection)}회 (건너뜀 {plan['complete']}, 신규 실행 {plan['new'] + plan['redo']}회"
          f"{f' 중 끊긴/중단 실행 재실행 {plan['redo']}회' if plan['redo'] else ''})")
    n_new = plan["new"] + plan["redo"]
    print(f"예상 호출 수: 에이전트 실행 {n_new}회(실행당 최대 {cfg.max_turns}턴, 턴당 요청 1회로 가정하면 최대 약 {n_new * cfg.max_turns}회 요청, 가설) + 탐침 호출 {probes}회")
    for d in sorted({t.id[0] for t in tasks}):
        b = bounds.get(d)
        print(f"  건당 비용 상한 {DIFFICULTY_LABEL[d]}: " + (f"측정 최대 ${b['max']:.4f} ({b['n']}건)" if b else "측정 전(추정값을 적지 않음)"))
    if model == "haiku":
        print(f"  참고: 5턴 데모 과제는 건당 최대 ${DEMO_COST_BOUND} (2026-11-05 측정). 20턴까지 가는 과제에는 적용하지 않는다. 비용은 정가 환산이며 구독 한도 소모와는 별개다.")
    else:
        print(f"  참고: {model}는 이 프로젝트에서 측정한 적이 없어 haiku 측정값을 상한으로 쓰지 않는다. 비용은 정가 환산이며 구독 한도 소모와는 별개다.")
    if not n_new:
        print("할 일이 없다(모두 끝남).")
    if not a.yes and _ask(deps, "시작하시겠습니까? (y/n): ") != "y":
        print("취소했다. 아무것도 실행하지 않았다.")
        return EXIT_DECLINED

    # 6) 실행
    summary_path = out_dir / f"{a.experiment}_{model}_{a.config}_summary.jsonl"
    prior = [r for r in read_events(summary_path) if r.get("kind") == "batch_start"] if summary_path.exists() else []
    ctx = Ctx(a=a, cfg=cfg, out_dir=out_dir, summary_path=summary_path, invocation=len(prior) + 1, repro=repro_info(deps, dirty),
              threshold=threshold, work=plan["work"])
    interrupted = False
    try:
        asyncio.run(_execute(ctx, deps))
    except guard.ToolGuardError as e:  # 탐침의 도구 가드 위반
        ctx.stop_reason = f"ToolGuardError: {e}"
    except (KeyboardInterrupt, asyncio.CancelledError):
        interrupted, ctx.stop_reason = True, "사용자 중단(KeyboardInterrupt)"
    window = _finalize_window(ctx)
    _append(summary_path, {"kind": "batch_end", "invocation": ctx.invocation, "reason": ctx.stop_reason or "완료", "new_runs": ctx.new_done,
                           "five_hour": window["end"]["five_hour"], "seven_day": window["end"]["seven_day"], "source": window["end"]["source"],
                           "start_five_hour": window["start"]["five_hour"], "start_seven_day": window["start"]["seven_day"],
                           "delta": window["delta"], "observed_five_hour_range": _range(ctx.five_obs), "observed_seven_day_range": _range(ctx.seven_obs),
                           "utilization_unit": UNIT_NOTE})
    text = build_summary(ctx, ctx.stop_reason, selection, window, interrupted)
    md = results_dir / f"{a.experiment}_{model}_{a.config}_summary_inv{ctx.invocation}.md"
    md.write_text(text, encoding="utf-8", newline="\n")
    write_run_csv(results_dir / f"{a.experiment}_{model}_{a.config}_runs.csv", ctx, selection)
    print("\n" + text)
    print(f"요약 저장: {md}")
    if ctx.stop_reason:
        print(f"\n안전하게 멈췄다: {ctx.stop_reason}")
        if ctx.last_resets_at:
            print(f"참고: 마지막 RateLimitEvent의 resets_at={ctx.last_resets_at} (유닉스 시각, 의미는 가설)")
        print("이어하기: 같은 명령을 다시 실행하면 끝난 실행은 건너뛰고, 끊기거나 중단된 실행은 이름을 바꿔 보관한 뒤 다시 한다.")
        print("  " + _restart_command(argv))
        return EXIT_INTERRUPTED if interrupted else EXIT_STOPPED
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
