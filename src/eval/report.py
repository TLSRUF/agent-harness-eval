"""trajectory jsonl 리포트: 성공률, 커스텀 도구 선택률, 도구 호출 횟수, 성패 5범주.

규칙
- 성공률과 선택률은 별도 열/줄로 보고하고 하나로 합치지 않는다.
- 성공률/선택률을 출력하는 모든 줄에는 sample_label()이 만든 표본 크기 문구가 붙는다 (데이터에서 센 값).
- 선택률 계산에 포함된 실행이 30건 미만이면 출력 끝에 경고 문구를 붙인다.
- 도구 종류 판정은 src.agent.tools.classify_tool 한 곳만 쓴다.

사용: python -m src.eval.report results/raw/day3demo_haiku_normal_run*.jsonl [--overlap overlap.json]
overlap.json 형식: {"과제id": ["search_text|Grep", "file_stats|Read"], ...}  (비어 있으면 선택률에서 제외)
"""
from __future__ import annotations

import argparse
import glob
import json
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from src.agent.tools import classify_tool

MIN_SAMPLE = 30
SMALL_SAMPLE_WARNING = "표본이 작아 해석에 주의"

CATEGORIES = [
    ("success_pass", "success + 채점 통과"),
    ("success_fail", "success + 채점 실패(오답)"),
    ("maxturns_pass", "error_max_turns + 채점 통과"),
    ("maxturns_fail", "error_max_turns + 채점 실패"),
    ("other_error", "기타 error_* / 예외"),
    ("ungraded", "채점 없음(분류 불가)"),
]


@dataclass
class Run:
    path: str
    task_id: str
    config: dict
    tool_counts: Counter = field(default_factory=Counter)  # SDK 이름 그대로
    tool_calls: int = 0
    tool_errors: int = 0
    subtype: str | None = None
    is_error: bool | None = None
    terminal_reason: str | None = None
    num_turns: int | None = None
    cost: float | None = None
    exception: str | None = None
    passed: bool | None = None  # 채점 결과, 없으면 None
    cwd: str | None = None  # init 메시지의 작업 폴더 (인자 정규화용)
    seq: list = field(default_factory=list)  # 도구 호출 순서: (SDK 이름, 입력 dict)
    calls_by_kind: Counter = field(default_factory=Counter)  # custom / builtin / other
    errors_by_kind: Counter = field(default_factory=Counter)  # 오류 결과를 호출과 짝지어 센 것
    unmatched_errors: int = 0  # tool_use_id가 어떤 호출과도 안 맞는 오류 결과

    @property
    def category(self) -> str:
        if self.subtype is None or self.is_error and self.subtype == "success":
            return "other_error"
        if self.subtype == "success":
            if self.passed is None:
                return "ungraded"
            return "success_pass" if self.passed else "success_fail"
        if self.subtype == "error_max_turns":
            if self.passed is None:
                return "ungraded"
            return "maxturns_pass" if self.passed else "maxturns_fail"
        return "other_error"

    def used_custom(self, short_names: set[str]) -> bool:
        return any(classify_tool(n) == "custom" and n.split("__", 2)[-1] in short_names for n in self.tool_counts)

    def used_builtin(self, names: set[str]) -> bool:
        return any(classify_tool(n) == "builtin" and n in names for n in self.tool_counts)


def load_run(path: str | Path) -> Run:
    rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    cfg_ev = next((r for r in rows if r["kind"] == "config"), {})
    run = Run(path=str(path), task_id=cfg_ev.get("task_id", "unknown"), config=cfg_ev.get("config", {}))
    id_to_name: dict[str, str] = {}
    for r in rows:
        if r["kind"] != "message":
            continue
        m = r["message"]
        kind = m.get("_type")
        if kind == "SystemMessage" and m.get("subtype") == "init":
            run.cwd = (m.get("data") or {}).get("cwd") or run.cwd
        elif kind == "AssistantMessage":
            for b in m.get("content", []):
                if isinstance(b, dict) and b.get("_type") == "ToolUseBlock":
                    run.tool_counts[b["name"]] += 1
                    run.tool_calls += 1
                    run.seq.append((b["name"], b.get("input", {})))
                    run.calls_by_kind[classify_tool(b["name"])] += 1
                    id_to_name[b.get("id")] = b["name"]
        elif kind == "UserMessage" and isinstance(m.get("content"), list):
            for b in m["content"]:
                if isinstance(b, dict) and b.get("_type") == "ToolResultBlock" and b.get("is_error") is True:
                    run.tool_errors += 1
                    name = id_to_name.get(b.get("tool_use_id"))
                    if name is None:
                        run.unmatched_errors += 1
                    else:
                        run.errors_by_kind[classify_tool(name)] += 1
    summ = next((r for r in reversed(rows) if r["kind"] == "summary"), None)
    if summ:
        run.subtype, run.is_error = summ.get("subtype"), summ.get("is_error")
        run.terminal_reason, run.num_turns = summ.get("terminal_reason"), summ.get("num_turns")
        run.cost, run.exception = summ.get("total_cost_usd"), summ.get("exception")
        g = summ.get("graded")
        if isinstance(g, dict) and isinstance(g.get("passed"), bool):
            run.passed = g["passed"]
    return run


# ---- 표본 크기 문구 (모든 성공률/선택률 출력이 이 함수를 거친다) ----

def sample_label(runs_per_task: dict[str, int]) -> str:
    """'N=…, 과제당 M회 / 총 실행 K건' 문구를 데이터에서 세어 만든다. 손으로 쓰지 않는다."""
    n = len(runs_per_task)
    k = sum(runs_per_task.values())
    if n == 0:
        return "N=0, 과제당 0회 / 총 0건"
    lo, hi = min(runs_per_task.values()), max(runs_per_task.values())
    m = f"{lo}회" if lo == hi else f"{lo}~{hi}회(최소 {lo}회)"
    return f"N={n}, 과제당 {m} / 총 {k}건"


def rate_line(name: str, numerator: int, runs_per_task: dict[str, int]) -> str:
    k = sum(runs_per_task.values())
    pct = "n/a" if k == 0 else f"{100 * numerator / k:.0f}%"
    return f"{name} {pct} ({sample_label(runs_per_task)})"


def chart_title(title: str, runs_per_task: dict[str, int]) -> str:
    """그래프 제목/범례용: 같은 형식의 표본 문구를 붙인다."""
    return f"{title} ({sample_label(runs_per_task)})"


def _per_task(runs: list[Run]) -> dict[str, int]:
    return dict(Counter(r.task_id for r in runs))


# ---- 지표 ----

def success_stats(runs: list[Run]) -> tuple[int, dict[str, int], int]:
    """(통과 실행 수, 과제별 채점된 실행 수, 채점 없는 실행 수). 통과 = success_pass + maxturns_pass."""
    graded = [r for r in runs if r.passed is not None]
    return sum(r.passed for r in graded), _per_task(graded), len(runs) - len(graded)


def parse_pairs(pairs: list[str]) -> list[tuple[str, str]]:
    out = []
    for p in pairs:
        custom, builtin = p.split("|", 1)
        out.append((custom.strip(), builtin.strip()))
    return out


def selection_stats(runs: list[Run], overlap: dict[str, list[str]]):
    """overlap_with가 있는 과제만. 커스텀 사용 = 그 과제의 overlap 쌍에 적힌 커스텀 도구를 한 번이라도 호출."""
    sel_runs = [r for r in runs if overlap.get(r.task_id)]
    overall_used = 0
    for r in sel_runs:
        customs = {c for c, _ in parse_pairs(overlap[r.task_id])}
        overall_used += r.used_custom(customs)
    pair_rows = {}
    all_pairs = sorted({p for t in overlap.values() for p in t})
    for pair in all_pairs:
        c, b = parse_pairs([pair])[0]
        pr = [r for r in runs if pair in overlap.get(r.task_id, [])]
        used_c = [r.used_custom({c}) for r in pr]
        used_b = [r.used_builtin({b}) for r in pr]
        pair_rows[pair] = {
            "runs": pr, "custom_used": sum(used_c),
            "custom_only": sum(uc and not ub for uc, ub in zip(used_c, used_b)),
            "builtin_only": sum(ub and not uc for uc, ub in zip(used_c, used_b)),
            "both": sum(uc and ub for uc, ub in zip(used_c, used_b)),
            "neither": sum(not uc and not ub for uc, ub in zip(used_c, used_b)),
        }
    return sel_runs, overall_used, pair_rows


# ---- 반복 실행 지표 (pass^k, 일관성) ----

def _warn_if_small(k: int) -> str:
    return f" ※ {SMALL_SAMPLE_WARNING}" if k < MIN_SAMPLE else ""


def pass_k_line(runs: list[Run]) -> str:
    """pass^k: 같은 과제를 k번 돌려 모두 성공한 과제의 비율. 채점된 실행이 2회 이상인 과제만 대상.

    같은 과제 집합에서 단일 실행 평균 성공률(통과 실행 / 채점된 실행)을 같은 줄에 나란히 보고한다.
    """
    by: dict[str, list[Run]] = defaultdict(list)
    for r in runs:
        if r.passed is not None:
            by[r.task_id].append(r)
    rep = {t: rs for t, rs in by.items() if len(rs) >= 2}
    per_task = {t: len(rs) for t, rs in rep.items()}
    k = sum(per_task.values())
    if not rep:
        return f"pass^k n/a | 단일 실행 평균 성공률 n/a ({sample_label({})}) — 반복 2회 이상 과제만" + _warn_if_small(0)
    hits = sum(all(r.passed for r in rs) for rs in rep.values())
    singles = sum(r.passed for rs in rep.values() for r in rs)
    return (f"pass^k {100 * hits / len(rep):.0f}% | 단일 실행 평균 성공률 {100 * singles / k:.0f}% "
            f"({sample_label(per_task)}) — 반복 2회 이상 과제만" + _warn_if_small(k))


def _norm_value(x, cwd_n: str | None):
    if isinstance(x, dict):
        return {str(k): _norm_value(v, cwd_n) for k, v in sorted(x.items(), key=lambda kv: str(kv[0]))}
    if isinstance(x, list):
        return [_norm_value(v, cwd_n) for v in x]
    if isinstance(x, str):
        s = x.replace("\\", "/")
        if cwd_n:
            if s.rstrip("/") == cwd_n:
                return "<cwd>"
            if s.startswith(cwd_n + "/"):  # 경로 경계가 있는 접두만 (task_a가 task_ab의 접두로 오인되지 않게)
                return "<cwd>" + s[len(cwd_n):]
        return s
    return x


def normalize_args(args, cwd: str | None = None) -> str:
    """도구 인자를 비교용 문자열로 정규화한다: 객체 키 순서, 경로 구분자(\\ -> /), 작업 폴더 접두(<cwd>)를 무시한다."""
    cwd_n = (cwd or "").replace("\\", "/").rstrip("/") or None
    return json.dumps(_norm_value(args, cwd_n), sort_keys=True, ensure_ascii=False)


def consistency_line(runs: list[Run]) -> str:
    """같은 과제의 반복 실행 쌍마다 (a) 도구 이름 순서가 같은 비율 (b) 이름과 정규화한 인자까지 같은 비율. 반복 2회 이상인 과제만."""
    by: dict[str, list[Run]] = defaultdict(list)
    for r in runs:
        by[r.task_id].append(r)
    rep = {t: rs for t, rs in by.items() if len(rs) >= 2}
    pairs = names_eq = full_eq = 0
    for rs in rep.values():
        names = [[n for n, _ in r.seq] for r in rs]
        full = [[(n, normalize_args(a, r.cwd)) for n, a in r.seq] for r in rs]
        for i in range(len(rs)):
            for j in range(i + 1, len(rs)):
                pairs += 1
                names_eq += names[i] == names[j]
                full_eq += full[i] == full[j]
    per_task = {t: len(rs) for t, rs in rep.items()}
    k = sum(per_task.values())
    if pairs == 0:
        return (f"일관성 (a) 도구 이름 순서 일치 n/a | (b) 이름과 정규화한 인자까지 일치 n/a "
                f"({sample_label({})}; 비교한 쌍 0개) — 반복 2회 이상 과제만" + _warn_if_small(0))
    return (f"일관성 (a) 도구 이름 순서 일치 {100 * names_eq / pairs:.0f}% | (b) 이름과 정규화한 인자까지 일치 {100 * full_eq / pairs:.0f}% "
            f"({sample_label(per_task)}; 비교한 쌍 {pairs}개) — 반복 2회 이상 과제만" + _warn_if_small(k))


def tool_error_split_line(runs: list[Run]) -> str:
    """도구 호출 대비 오류 결과(is_error) 비율을 커스텀/내장/기타로 나눠서."""
    calls: Counter = Counter()
    errs: Counter = Counter()
    unmatched = 0
    for r in runs:
        calls.update(r.calls_by_kind)
        errs.update(r.errors_by_kind)
        unmatched += r.unmatched_errors

    def part(label: str, kind: str) -> str:
        c, e = calls[kind], errs[kind]
        return f"{label} {e}/{c} = " + (f"{100 * e / c:.1f}%" if c else "n/a")

    text = "도구 오류율(구분): " + " | ".join([part("커스텀", "custom"), part("내장", "builtin"), part("기타", "other")])
    if unmatched:
        text += f" (짝 없는 오류 결과 {unmatched}건은 구분에서 제외)"
    return text


# ---- min_steps 구간별 성공률 ----

MIN_STEPS_BINS = [("1~2", 1, 2), ("3~4", 3, 4), ("5 이상", 5, None)]


def min_steps_lines(runs: list[Run], min_steps: dict | None) -> list[str]:
    """min_steps(분석 전용, 사람이 정한 추정값)별 성공률. min_steps가 없거나 올바르지 않은 과제는 제외하고 그 수를 표시한다."""
    if min_steps is None:
        return ["min_steps 정보가 없어 구간별 성공률을 계산하지 않음"]
    valid = {t: v for t, v in min_steps.items() if isinstance(v, int) and not isinstance(v, bool) and v >= 1}
    out = []
    for label, lo, hi in MIN_STEPS_BINS:
        sel = [r for r in runs if r.task_id in valid and r.passed is not None
               and lo <= valid[r.task_id] and (hi is None or valid[r.task_id] <= hi)]
        out.append(rate_line(f"min_steps {label}: 성공률", sum(r.passed for r in sel), _per_task(sel)) + _warn_if_small(len(sel)))
    excluded_runs = [r for r in runs if r.task_id not in valid]
    if excluded_runs:
        out.append(f"min_steps 없는 과제 {len({r.task_id for r in excluded_runs})}개 제외(실행 {len(excluded_runs)}건)")
    return out


def tool_table(runs: list[Run]) -> list[str]:
    """실행별 도구 이름별 호출 횟수. 커스텀/내장/기타를 구분해서 기록."""
    lines = ["| 실행 | 과제 | 커스텀 | 내장 | 기타 |", "|---|---|---|---|---|"]
    for r in runs:
        groups: dict[str, list[str]] = defaultdict(list)
        for name, n in sorted(r.tool_counts.items()):
            short = name.split("__", 2)[-1] if classify_tool(name) == "custom" else name
            groups[classify_tool(name)].append(f"{short} {n}")
        lines.append(f"| {Path(r.path).name} | {r.task_id} | {', '.join(groups['custom']) or '-'} | "
                     f"{', '.join(groups['builtin']) or '-'} | {', '.join(groups['other']) or '-'} |")
    return lines


def build_report(runs: list[Run], overlap: dict[str, list[str]] | None = None, min_steps: dict | None = None) -> str:
    overlap = overlap or {}
    out: list[str] = []
    out.append(f"# 리포트 (실행 {len(runs)}건)\n")

    # 설정 요약 (모델, 프롬프트 버전, 최대 턴, 도구 설명 버전)
    cfgs = Counter((r.config.get("model"), r.config.get("prompt_version"), r.config.get("max_turns"),
                    r.config.get("tool_desc_version")) for r in runs)
    out.append("## 설정 (모델 / 프롬프트 / 최대 턴 / 도구 설명)")
    for (model, pv, mt, td), n in cfgs.items():
        out.append(f"- {model} / {pv} / max_turns={mt} / {td}: {n}건")

    # 성공률 (선택률과 별도)
    passed, per_task, ungraded = success_stats(runs)
    out.append("\n## 성공률")
    out.append(rate_line("성공률", passed, per_task))
    if ungraded:
        out.append(f"(채점 없는 실행 {ungraded}건은 성공률에서 제외)")

    # 반복 실행 지표 (성공률과 별도 줄)
    out.append("\n## 반복 실행 지표 (반복 2회 이상인 과제만)")
    out.append(pass_k_line(runs))
    out.append(consistency_line(runs))

    # min_steps 구간별 성공률
    out.append("\n## min_steps 구간별 성공률 (분석 전용 필드, 사람이 정한 추정값)")
    out.extend(min_steps_lines(runs, min_steps))

    # 성패 5범주
    cats = Counter(r.category for r in runs)
    out.append("\n## 성패 분류 (subtype x 채점)")
    out.append("| 범주 | 건수 |\n|---|---|")
    for key, label in CATEGORIES:
        if key == "ungraded" and not cats[key]:
            continue
        out.append(f"| {label} | {cats[key]} |")
    out.append(f"턴 제한 실패율(error_max_turns + 채점 실패): "
               + rate_line("", cats["maxturns_fail"], _per_task(runs)).strip())
    out.append(f"턴 제한에 걸렸지만 채점 통과: {cats['maxturns_pass']}건 (별도 집계)")

    # 선택률 (성공률과 별도)
    sel_runs, overall_used, pair_rows = selection_stats(runs, overlap)
    out.append("\n## 커스텀 도구 선택률 (overlap_with가 있는 과제만)")
    excluded = len(runs) - len(sel_runs)
    out.append(rate_line("선택률", overall_used, _per_task(sel_runs)))
    if excluded:
        out.append(f"(overlap_with가 없는 과제의 실행 {excluded}건은 제외)")
    out.append("")
    for pair, d in pair_rows.items():
        c, b = parse_pairs([pair])[0]
        out.append(rate_line(f"{c} 대 {b}:", d["custom_used"], _per_task(d["runs"])) +
                   f" — 커스텀만 {d['custom_only']}, 내장만 {d['builtin_only']}, 둘 다 {d['both']}, 둘 다 아님 {d['neither']}")

    # 보조 지표
    out.append("\n## 실행별 도구 호출 횟수")
    out.extend(tool_table(runs))

    calls = sum(r.tool_calls for r in runs)
    errs = sum(r.tool_errors for r in runs)
    out.append("\n## 기타 지표")
    out.append(f"- 도구 오류율: {errs}/{calls}" + (f" = {100 * errs / calls:.1f}%" if calls else ""))
    out.append("- " + tool_error_split_line(runs))
    turns = [r.num_turns for r in runs if r.num_turns is not None]
    fixed = [min(r.num_turns, r.config["max_turns"]) if r.subtype == "error_max_turns" and r.config.get("max_turns")
             and r.num_turns is not None else r.num_turns for r in runs if r.num_turns is not None]
    if turns:
        out.append(f"- 평균 턴 수: 보고값 {statistics.mean(turns):.2f}, 보정값 {statistics.mean(fixed):.2f} "
                   "(error_max_turns는 설정값+1로 보고되므로 min(num_turns, max_turns)로 보정)")
    costs = [r.cost for r in runs if r.cost is not None]
    if costs:
        out.append(f"- 비용 추정(정가 환산): 합계 ${sum(costs):.4f}, 실행당 평균 ${statistics.mean(costs):.4f}")

    if len(sel_runs) < MIN_SAMPLE:
        out.append(f"\n※ {SMALL_SAMPLE_WARNING} (선택률 계산에 포함된 실행 {len(sel_runs)}건 < {MIN_SAMPLE}건)")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+", help="jsonl 경로 또는 글롭")
    ap.add_argument("--overlap", help="과제id -> overlap_with 목록 JSON")
    a = ap.parse_args(argv)
    files = sorted({f for p in a.paths for f in glob.glob(p)})
    overlap = json.loads(Path(a.overlap).read_text(encoding="utf-8")) if a.overlap else {}
    from . import loader  # min_steps는 과제 정의(JSON)에서 읽는다
    min_steps = {t.id: t.min_steps for t in loader.load_all() if not t.is_todo}
    print(build_report([load_run(f) for f in files], overlap, min_steps))


if __name__ == "__main__":
    main()
