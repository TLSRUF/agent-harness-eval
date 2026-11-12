"""실험 A 비교표: default(=baseline), short, long, long_directive 4개 설정을 열로 놓고 비교한다.

읽기 전용(모델 호출 없음). 동결 대상이 아니다. 출력 형식은 tests/test_exp_compare.py가 고정한다.
사용: python -m src.eval.exp_compare [--raw-dir results/raw] [--out-md ...] [--out-csv ...]

- 선택률(커스텀 도구) = 그 과제의 overlap 쌍에 적힌 커스텀 도구를 한 번이라도 호출한 실행 / 쌍 과제 실행.
- 우연 범위 = 같은 설정 안에서 반복(run1~run3) 사이 선택률의 최대-최소(퍼센트 포인트). 반복이 3개뿐이라 과소추정일 수 있다(가설).
- 모든 값에 표본 크기(N, 과제당 M회, 총 건수)를 붙이고 30건 미만이면 경고한다.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from . import baseline_report as br
from . import loader, report

COLUMNS = ["default", "short", "long", "long_directive"]
PREFIXES = {"default": "baseline_haiku_default", "short": "expA_haiku_short", "long": "expA_haiku_long",
            "long_directive": "expA_haiku_longDirective"}
PROBE_NAMES = {"default": "baseline-default", "short": "expA-short", "long": "expA-long", "long_directive": "expA-longDirective"}
SECTION_TITLES = [
    "## 1. 설정 4개 비교",
    "## 2. 과제별 선택률 (과제 x 설정, 3회 중 커스텀 도구를 쓴 횟수)",
    "## 3. 반복별 선택률과 우연 범위",
    "## 4. 정보 효과와 지시 효과 (선택률 차이, 퍼센트 포인트)",
    "## 5. 한도와 배치별 비용",
]
EPS = 1e-9


@dataclass
class Rec:
    item: br.Item
    input_total: int | None       # input + 캐시 생성 + 캐시 읽기 (summary의 usage)
    ts: str | None                # summary 이벤트 시각

    @property
    def task(self) -> str:
        return self.item.task

    @property
    def n(self) -> int:
        return self.item.n

    @property
    def run(self) -> report.Run:
        return self.item.run


def load_rec(path: Path) -> Rec:
    item = br.load_item(path)
    summ = None
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip() and '"kind": "summary"' in line:
            summ = json.loads(line)
    usage = (summ or {}).get("usage") or {}
    keys = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
    total = sum(int(usage.get(k) or 0) for k in keys) if usage else None
    return Rec(item=item, input_total=total, ts=(summ or {}).get("ts"))


def collect(raw_dir) -> dict[str, list[Rec]]:
    """설정별 최종 실행 로그(..._run{n}.jsonl)만 읽는다. .partial 보관본, _final 폴더, 다른 설정은 제외."""
    out: dict[str, list[Rec]] = {c: [] for c in COLUMNS}
    for col, prefix in PREFIXES.items():
        rx = re.compile("^" + re.escape(prefix) + r"_([EMH]\d+)_run(\d+)\.jsonl$")
        for p in sorted(Path(raw_dir).glob(prefix + "_*_run*.jsonl")):
            if p.is_file() and rx.match(p.name):
                out[col].append(load_rec(p))
    return out


# ---------------- 선택 지표 정의 ----------------

class Sel:
    def __init__(self, label, scope, used):
        self.label, self.scope, self.used = label, scope, used


def _selections(tasks: dict[str, loader.Task]) -> dict[str, Sel]:
    def pair_scope(pair):
        return lambda t: pair in getattr(tasks.get(t), "overlap_with", [])

    def any_pair(t):
        return bool(getattr(tasks.get(t), "overlap_with", []))

    def pooled_used(r: Rec):
        customs = {c for c, _ in report.parse_pairs(tasks[r.task].overlap_with)} if r.task in tasks else set()
        return r.run.used_custom(customs)

    return {
        "search_text 선택률": Sel("search_text 선택률", pair_scope("search_text|Grep"), lambda r: r.run.used_custom({"search_text"})),
        "Grep 사용률": Sel("Grep 사용률", pair_scope("search_text|Grep"), lambda r: r.run.used_builtin({"Grep"})),
        "file_stats 선택률": Sel("file_stats 선택률", pair_scope("file_stats|Read"), lambda r: r.run.used_custom({"file_stats"})),
        "Read 사용률": Sel("Read 사용률", pair_scope("file_stats|Read"), lambda r: r.run.used_builtin({"Read"})),
        "check_result 사용률": Sel("check_result 사용률", lambda t: True, lambda r: r.run.used_custom({"check_result"})),
        "쌍 과제 합산 커스텀 선택률": Sel("쌍 과제 합산 커스텀 선택률", any_pair, pooled_used),
    }


def _per_task(recs: list[Rec]) -> dict[str, int]:
    return dict(Counter(r.task for r in recs))


def _rate(recs: list[Rec], sel: Sel):
    rs = [r for r in recs if sel.scope(r.task)]
    return sum(bool(sel.used(r)) for r in rs), len(rs), _per_task(rs)


def _rep_rates(recs: list[Rec], sel: Sel) -> dict[int, tuple[int, int]]:
    out: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    for r in recs:
        if sel.scope(r.task):
            out[r.n][1] += 1
            out[r.n][0] += bool(sel.used(r))
    return {k: (v[0], v[1]) for k, v in sorted(out.items())}


def _pct(num, den) -> float | None:
    return None if not den else 100 * num / den


def _fmt_rate(num, den) -> str:
    return "n/a" if not den else f"{100 * num / den:.0f}% ({num}/{den})"


def _range_pp(reps: dict[int, tuple[int, int]]) -> float | None:
    vals = [100 * a / b for a, b in reps.values() if b]
    return None if len(vals) < 2 else max(vals) - min(vals)


def judge(effect_pp, range_a, range_b, n_reps_a, n_reps_b) -> str:
    """효과 크기를 두 설정의 반복 간 범위 중 큰 값과 비교한다. 계산이 안 되거나 경계(같음)면 '확인 불가'."""
    if effect_pp is None or range_a is None or range_b is None or n_reps_a < 2 or n_reps_b < 2:
        return "확인 불가"
    noise = max(range_a, range_b)
    size = abs(effect_pp)
    if abs(size - noise) <= EPS:
        return f"작음(효과 크기 0.0 = 범위 {noise:.1f}, 차이 없음)" if size <= EPS else "확인 불가"
    return f"큼(효과 크기 {size:.1f} > 범위 {noise:.1f})" if size > noise else f"작음(효과 크기 {size:.1f} < 범위 {noise:.1f})"


# ---------------- 표 조립 ----------------

def _sample_cell(labels: dict[str, str], ks: dict[str, int]) -> str:
    uniq = set(labels.values())
    text = next(iter(uniq)) if len(uniq) == 1 else "; ".join(f"{c}: {labels[c]}" for c in COLUMNS)
    small = [c for c in COLUMNS if 0 < ks[c] < report.MIN_SAMPLE]
    if small:
        text += f" ⚠ {report.SMALL_SAMPLE_WARNING}(30건 미만" + ("" if len(small) == len(COLUMNS) else ": " + ", ".join(small)) + ")"
    return text


def consistency(recs: list[Rec]):
    """(비교한 쌍 수, 도구 이름 순서가 같은 쌍, 이름과 핵심 인자가 같은 쌍, 대상 과제별 실행 수). report.consistency_line과 같은 규칙."""
    by: dict[str, list[Rec]] = defaultdict(list)
    for r in recs:
        by[r.task].append(r)
    pairs = a = b = 0
    per_task = {}
    for t, rs in by.items():
        if len(rs) < 2:
            continue
        per_task[t] = len(rs)
        names = [[n for n, _ in r.run.seq] for r in rs]
        core = [[(n, report.normalize_args(report.core_args(x), r.run.cwd)) for n, x in r.run.seq] for r in rs]
        for i in range(len(rs)):
            for j in range(i + 1, len(rs)):
                pairs += 1
                a += names[i] == names[j]
                b += core[i] == core[j]
    return pairs, a, b, per_task


class _Out:
    def __init__(self):
        self.records: list[dict] = []

    def rec(self, metric, config, num, den, value, sample, task=""):
        self.records.append({"metric": metric, "config": config, "task": task, "numerator": "" if num is None else num,
                             "denominator": "" if den is None else den, "value": "" if value is None else value, "sample": sample})


def _section1(cols, sels, out: _Out) -> list[str]:
    L = ["| 지표 | " + " | ".join(COLUMNS) + " | 표본 |", "|---|" + "---|" * len(COLUMNS) + "---|"]

    def add(label, cells, labels, ks):
        L.append(f"| {label} | " + " | ".join(cells[c] for c in COLUMNS) + f" | {_sample_cell(labels, ks)} |")

    def per_cfg(fn):
        return {c: fn(c) for c in COLUMNS}

    # 1. 성공률, error_max_turns
    graded = {c: [r for r in cols[c] if r.run.passed is not None] for c in COLUMNS}
    cells, labels, ks = {}, {}, {}
    for c in COLUMNS:
        g = graded[c]
        ok = sum(r.run.passed for r in g)
        cells[c] = _fmt_rate(ok, len(g))
        labels[c], ks[c] = report.sample_label(_per_task(g)), len(g)
        out.rec("성공률", c, ok, len(g), _pct(ok, len(g)), labels[c])
    add("성공률", cells, labels, ks)
    cells, labels, ks = {}, {}, {}
    for c in COLUMNS:
        rs = cols[c]
        mt = [r for r in rs if r.run.subtype == "error_max_turns"]
        mp = sum(bool(r.run.passed) for r in mt)
        cells[c] = f"{len(mt)} (통과 {mp})" if rs else "n/a"
        labels[c], ks[c] = report.sample_label(_per_task(rs)), len(rs)
        out.rec("error_max_turns 건수", c, len(mt), len(rs), len(mt) if rs else None, labels[c])
    add("error_max_turns 건수", cells, labels, ks)

    # 2~4. 선택률/사용률
    for name in ["search_text 선택률", "Grep 사용률", "file_stats 선택률", "Read 사용률", "check_result 사용률"]:
        cells, labels, ks = {}, {}, {}
        for c in COLUMNS:
            num, den, per = _rate(cols[c], sels[name])
            cells[c] = _fmt_rate(num, den)
            labels[c], ks[c] = report.sample_label(per), den
            out.rec(name, c, num, den, _pct(num, den), labels[c])
        add(name, cells, labels, ks)

    # 5~6. 평균
    def mean_row(label, getter, fmt):
        cells, labels, ks = {}, {}, {}
        for c in COLUMNS:
            rs = [r for r in cols[c] if getter(r) is not None]
            cells[c] = fmt(statistics.mean(getter(r) for r in rs)) if rs else "n/a"
            labels[c], ks[c] = report.sample_label(_per_task(rs)), len(rs)
            out.rec(label, c, None, len(rs), statistics.mean(getter(r) for r in rs) if rs else None, labels[c])
        add(label, cells, labels, ks)

    mean_row("평균 num_turns", lambda r: r.run.num_turns, lambda v: f"{v:.1f}")
    mean_row("평균 모델 응답 수", lambda r: r.item.responses, lambda v: f"{v:.1f}")
    mean_row("평균 도구 호출 수", lambda r: r.run.tool_calls, lambda v: f"{v:.1f}")
    mean_row("실행당 평균 비용", lambda r: r.run.cost, lambda v: f"${v:.4f}")
    mean_row("실행당 평균 입력 토큰", lambda r: r.input_total, lambda v: f"{v:.0f}")

    # 7. 일관성
    for label, idx in (("일관성 (a) 도구 순서", 1), ("일관성 (b) 핵심 인자", 2)):
        cells, labels, ks = {}, {}, {}
        for c in COLUMNS:
            pairs, a, b, per = consistency(cols[c])
            eq = a if idx == 1 else b
            cells[c] = "n/a (0쌍)" if not pairs else f"{100 * eq / pairs:.0f}% ({eq}/{pairs}쌍)"
            labels[c], ks[c] = report.sample_label(per), sum(per.values())
            out.rec(label, c, eq, pairs, _pct(eq, pairs), labels[c])
        add(label, cells, labels, ks)
    return L


def _section2(cols, tasks, out: _Out) -> list[str]:
    L = ["| 과제 | 쌍 | " + " | ".join(COLUMNS) + " |", "|---|---|" + "---|" * len(COLUMNS)]
    pair_tasks = sorted((t.id, p) for t in tasks.values() for p in t.overlap_with if p in ("search_text|Grep", "file_stats|Read"))
    for tid, pair in pair_tasks:
        custom = pair.split("|")[0]
        cells = []
        for c in COLUMNS:
            rs = [r for r in cols[c] if r.task == tid]
            k = sum(r.run.used_custom({custom}) for r in rs)
            cells.append(f"{k}/{len(rs)}" if rs else "n/a")
            out.rec("과제별 커스텀 도구 사용 횟수", c, k, len(rs), _pct(k, len(rs)), report.sample_label(_per_task(rs)), task=tid)
        L.append(f"| {tid} | {pair.replace('|', ' vs ')} | " + " | ".join(cells) + " |")   # 표 칸 안의 |는 표를 깨므로 vs로 쓴다
    L += ["", f"- 칸마다 표본은 과제 1개 x 3회뿐이다(총 3건 < {report.MIN_SAMPLE}건). {report.SMALL_SAMPLE_WARNING}. 쌍 과제 {len(pair_tasks)}개(search_text|Grep, file_stats|Read)만 나열한다."]
    return L


RATE_ROWS = ["search_text 선택률", "file_stats 선택률", "쌍 과제 합산 커스텀 선택률", "check_result 사용률"]


def _section3(cols, sels, out: _Out) -> list[str]:
    L = ["| 지표 | 설정 | run1 | run2 | run3 | 범위(최대-최소, pp) | 표본 |", "|---|---|---|---|---|---|---|"]
    for name in RATE_ROWS:
        for c in COLUMNS:
            reps = _rep_rates(cols[c], sels[name])
            cell = [_fmt_rate(*reps[n]) if n in reps else "n/a" for n in (1, 2, 3)]
            rng = _range_pp(reps)
            _, den, per = _rate(cols[c], sels[name])
            sample = report.sample_label(per) + (f" ⚠ {report.SMALL_SAMPLE_WARNING}(30건 미만)" if 0 < den < report.MIN_SAMPLE else "")
            L.append(f"| {name} | {c} | " + " | ".join(cell) + f" | {'n/a' if rng is None else f'{rng:.1f}'} | {sample} |")
            for n, (a, b) in reps.items():
                out.rec(f"{name} run{n}", c, a, b, _pct(a, b), sample)
            out.rec(f"{name} 반복 범위(pp)", c, None, None, rng, sample)
    L += ["", "- run1~run3 = 같은 설정의 반복 번호. 칸은 그 반복에서 쌍 과제 전체를 한 번씩 돌린 결과다(분모 = 그 반복의 쌍 과제 수).",
          "- 반복이 3개뿐이라 이 범위는 실제 반복 변동을 과소추정할 수 있다(가설)."]
    return L


def _section4(cols, sels, out: _Out) -> list[str]:
    L = ["| 지표 | 정보 효과(long - default) | 지시 효과(long_directive - long) | 우연 범위(pp) | 판정 |", "|---|---|---|---|---|"]
    notes = []
    for name in RATE_ROWS:
        rates = {c: _rate(cols[c], sels[name]) for c in COLUMNS}
        pct = {c: _pct(rates[c][0], rates[c][1]) for c in COLUMNS}
        reps = {c: _rep_rates(cols[c], sels[name]) for c in COLUMNS}
        rng = {c: _range_pp(reps[c]) for c in COLUMNS}
        nrep = {c: sum(1 for _, b in reps[c].values() if b) for c in COLUMNS}

        def eff(hi, lo):
            return None if pct[hi] is None or pct[lo] is None else pct[hi] - pct[lo]

        info, direc = eff("long", "default"), eff("long_directive", "long")
        fmt = lambda v: "n/a" if v is None else f"{v:+.1f}pp"  # noqa: E731
        noise = lambda a, b: "n/a" if rng[a] is None or rng[b] is None else f"{max(rng[a], rng[b]):.1f}"  # noqa: E731
        j_info = judge(info, rng["default"], rng["long"], nrep["default"], nrep["long"])
        j_dir = judge(direc, rng["long"], rng["long_directive"], nrep["long"], nrep["long_directive"])
        L.append(f"| {name} | {fmt(info)} | {fmt(direc)} | 정보 {noise('default', 'long')} / 지시 {noise('long', 'long_directive')} "
                 f"| 정보 {j_info} / 지시 {j_dir} |")
        out.rec(f"{name} 정보 효과(pp)", "long-default", None, None, info, "")
        out.rec(f"{name} 지시 효과(pp)", "long_directive-long", None, None, direc, "")
        labels = {c: report.sample_label(rates[c][2]) for c in COLUMNS}
        notes.append(f"- {name} 표본: " + _sample_cell(labels, {c: rates[c][1] for c in COLUMNS}))
    L += ["", "- 정보 효과 = long 선택률 - default 선택률, 지시 효과 = long_directive 선택률 - long 선택률 (합산 선택률 기준 퍼센트 포인트).",
          "- 우연 범위 = 비교하는 두 설정의 '반복 간 선택률 범위(최대-최소)' 중 큰 값. 효과 크기(절댓값) > 범위면 큼, < 범위면 작음, 같거나 반복 2개 미만이거나 n/a면 확인 불가.",
          "- 이 판정은 반복 3개짜리 범위와 비교하는 거친 기준이다. 통계 검정이 아니며, 큼이어도 인과 확정이 아니다(과제 구성, 모델 변동은 따로 통제하지 않았다)."] + notes
    return L


def _read_probe(path: Path):
    ts_cfg = ts_sum = five = seven = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        ev = json.loads(line)
        if ev.get("kind") == "config":
            ts_cfg = ev.get("ts")
        elif ev.get("kind") == "summary":
            ts_sum, five, seven = ev.get("ts"), ev.get("five_hour"), ev.get("seven_day")
    return ts_cfg, ts_sum, five, seven


def _section5(cols, raw_dir, out: _Out) -> list[str]:
    L = ["| 설정 | 호출 | five_hour 시작 | five_hour 종료 | five_hour 델타 | seven_day 시작 | seven_day 종료 | 실행 수 | 비용 합계 |",
         "|---|---|---|---|---|---|---|---|---|"]
    extra = []
    for c in COLUMNS:
        recs = cols[c]
        starts = {}
        for p in sorted(Path(raw_dir).glob(f"probe_haiku_{PROBE_NAMES[c]}_inv*_start.jsonl")):
            m = re.search(r"_inv(\d+)_start\.jsonl$", p.name)
            if m:
                starts[int(m.group(1))] = p
        wins = []
        for n, sp in sorted(starts.items()):
            ep = Path(raw_dir) / f"probe_haiku_{PROBE_NAMES[c]}_inv{n}_end.jsonl"
            if not ep.is_file():
                extra.append(f"- {c} 호출 {n}: 끝 탐침 없음(창을 정할 수 없어 제외)")
                continue
            s_cfg, s_sum, f0, s0 = _read_probe(sp)
            _, e_sum, f1, s1 = _read_probe(ep)
            wins.append((n, s_cfg or s_sum, e_sum, f0, f1, s0, s1))
        if not wins:
            if recs:
                tot = sum(r.run.cost or 0 for r in recs)
                L.append(f"| {c} | - | 탐침 없음 | 탐침 없음 | n/a | 탐침 없음 | 탐침 없음 | {len(recs)} | ${tot:.4f} |")
                out.rec("배치 비용 합계", c, len(recs), None, tot, "탐침 없음")
            continue
        assigned = set()
        for n, t0, t1, f0, f1, s0, s1 in wins:
            inside = [r for r in recs if r.ts and t0 and t1 and t0 <= r.ts <= t1]
            assigned |= {id(r) for r in inside}
            tot = sum(r.run.cost or 0 for r in inside)
            delta = "n/a" if f0 is None or f1 is None else f"{f1 - f0:+.2f}"
            L.append(f"| {c} | {n} | {f0} | {f1} | {delta} | {s0} | {s1} | {len(inside)} | ${tot:.4f} |")
            out.rec("배치 비용 합계", c, len(inside), None, tot, f"호출 {n}")
            out.rec("five_hour 델타", c, None, None, None if f0 is None or f1 is None else f1 - f0, f"호출 {n}")
        outside = [r for r in recs if id(r) not in assigned]
        if outside:
            extra.append(f"- {c}: 탐침 창 밖 {len(outside)}건 ${sum(r.run.cost or 0 for r in outside):.4f}(시각이 어느 탐침 구간에도 없거나 시각 기록 없음)")
    L += [""] + extra + [
        "- five_hour/seven_day는 구독 전체 사용량(탐침 호출로 읽음)이라 다른 사용이 섞일 수 있다. 해상도 0.01, 값마다 +-0.01 잡음이 관찰되어 한 배치 델타는 참고용이다.",
        "- 비용은 정가 환산 추정치이며 구독 한도 소모와는 별개다. 실행 수/비용은 실행 로그 summary 시각이 탐침 시작~끝 사이인 실행의 합이다."]
    return L


def build_compare(cols: dict[str, list[Rec]], raw_dir=".", tasks=None, out: _Out | None = None) -> str:
    tasks = tasks or {t.id: t for t in loader.load_all() if not t.is_todo}
    out = out if out is not None else _Out()
    sels = _selections(tasks)
    head = ["# 실험 A 비교표 (exp_compare)", "",
            "- 입력: " + ", ".join(f"{c} {len(cols[c])}건" for c in COLUMNS) + ". 최종 실행 로그만 읽는다(.partial, _final 제외). 읽기 전용, 모델 호출 없음.",
            "- 열 이름: default = 베이스라인(도구 설명 기본값), short = 짧은 설명, long = 정보 위주 긴 설명, long_directive = long + 우선 사용 지시 한 문장."]
    bodies = [_section1(cols, sels, out), _section2(cols, tasks, out), _section3(cols, sels, out), _section4(cols, sels, out),
              _section5(cols, raw_dir, out)]
    lines = head + [""]
    for title, body in zip(SECTION_TITLES, bodies):
        lines += [title, ""] + body + [""]
    return "\n".join(lines)


def build_from_dir(raw_dir, tasks=None) -> str:
    return build_compare(collect(raw_dir), raw_dir, tasks)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="실험 A 비교표(읽기 전용, 모델 호출 없음)")
    ap.add_argument("--raw-dir", default="results/raw")
    ap.add_argument("--out-md", default="results/expA_haiku_compare_summary_inv1.md")
    ap.add_argument("--out-csv", default="results/expA_haiku_compare_runs.csv")
    a = ap.parse_args(argv)
    cols = collect(a.raw_dir)
    if not any(cols.values()):
        print("읽을 로그가 없다", file=sys.stderr)
        return 1
    out = _Out()
    text = build_compare(cols, a.raw_dir, None, out)
    Path(a.out_md).write_text(text, encoding="utf-8")
    with open(a.out_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["metric", "config", "task", "numerator", "denominator", "value", "sample"])
        w.writeheader()
        w.writerows(out.records)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
