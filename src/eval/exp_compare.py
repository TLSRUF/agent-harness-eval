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
# 실험 B(검증 지시): 설정 이름(로그의 prompt_version 값)은 verify_tool이지만 파일/탐침 이름에는 밑줄을 쓰지 않아 verifyTool로 쓴다
COLUMNS_B = ["default", "verify", "verify_tool"]
PREFIXES_B = {"default": "baseline_haiku_default", "verify": "expB_haiku_verify", "verify_tool": "expB_haiku_verifyTool"}
PROBE_NAMES_B = {"default": "baseline-default", "verify": "expB-verify", "verify_tool": "expB-verifyTool"}
SECTION_TITLES_B = ["## 1. 설정 3개 비교", "## 2. 과제별 check_result 사용 횟수 (과제 x 설정, 3회 중)", "## 3. 한도와 배치별 비용"]
CHECK_RESULT_NOTE = "check_result는 파일 존재, 포함 문자열, 최소 줄 수만 확인하며 값의 정확성은 확인하지 않는다. 사용률은 검증 행동의 증가이지 정확성의 증가가 아니다."
# 실험 C(max_turns): 열 이름 = 설정 max_turns(default = baseline, max_turns 20)
COLUMNS_C = ["default", "3", "4", "5", "7"]
PREFIXES_C = {"default": "baseline_haiku_default", **{n: f"expC_haiku_maxTurns{n}" for n in ("3", "4", "5", "7")}}
PROBE_NAMES_C = {"default": "baseline-default", **{n: f"expC-maxTurns{n}" for n in ("3", "4", "5", "7")}}
SECTION_TITLES_C = ["## 1. 설정 5개 비교", "## 2. 한계 판정: 설정 max_turns x 모델 응답 수", "## 3. 한도와 배치별 비용"]
ROWS_C = ["성공률", "정상 종료율", "error_max_turns 건수(비율)", "error_max_turns인데 채점 통과", "평균 모델 응답 수", "평균 num_turns", "실행당 평균 비용"]
# 실험 D(모델 비교): haiku baseline vs sonnet, 같은 (과제, run) 쌍만
COLUMNS_D = ["haiku", "sonnet"]
PREFIXES_D = {"haiku": "baseline_haiku_default", "sonnet": "expD_sonnet_default"}
PROBE_NAMES_D = {"haiku": "baseline-default", "sonnet": "expD-default"}
PROBE_MODELS_D = {"haiku": "haiku", "sonnet": "sonnet"}
# 실험 E(출력 변형): 기준 = expA의 long, 비교 = long + file_stats 출력에 파일 이름
COLUMNS_E = ["long", "long_filename"]
PREFIXES_E = {"long": "expA_haiku_long", "long_filename": "expE_haiku_longFilename"}
PROBE_NAMES_E = {"long": "expA-long", "long_filename": "expE-longFilename"}
SECTION_TITLES_E = ["## 1. long vs long + 파일 이름 출력 (같은 (과제, run) 쌍만)", "## 2. 과제별 통과 횟수 (3회 중)", "## 3. 한도와 배치별 비용"]
ROWS_E = ["성공률", "실패 유형", "file_stats 선택률", "평균 도구 호출 수", "평균 모델 응답 수", "실행당 평균 비용"]
SECTION_TITLES_D = ["## 1. haiku vs sonnet (같은 (과제, run) 쌍만)", "## 2. 한도와 배치별 비용"]
ROWS_D = ["성공률", "error_max_turns 건수", "평균 모델 응답 수", "평균 도구 호출 수", "실행당 평균 비용", "search_text 선택률", "Grep 사용률",
          "file_stats 선택률", "Read 사용률", "일관성 (a) 도구 순서", "일관성 (b) 핵심 인자"]
ROWS_B = ["성공률", "error_max_turns 건수", "check_result 사용률", "평균 num_turns", "평균 모델 응답 수", "평균 도구 호출 수",
          "실행당 평균 비용", "일관성 (a) 도구 순서", "일관성 (b) 핵심 인자"]
SECTION_TITLES = [
    "## 1. 설정 4개 비교",
    "## 2. 과제별 선택률 (과제 x 설정, 3회 중 커스텀 도구를 쓴 횟수)",
    "## 3. 반복별 선택률과 우연 범위",
    "## 4. 정보 효과와 지시 효과 (선택률 차이, 퍼센트 포인트)",
    "## 5. 한도와 배치별 비용",
    "## 6. 견고성: 과제 단위 사용 과제 수와 선택 변화",
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


def collect(raw_dir, prefixes=None) -> dict[str, list[Rec]]:
    """설정별 최종 실행 로그(..._run{n}.jsonl)만 읽는다. .partial 보관본, _final 폴더, 다른 설정은 제외."""
    prefixes = prefixes or PREFIXES
    out: dict[str, list[Rec]] = {c: [] for c in prefixes}
    for col, prefix in prefixes.items():
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

def _sample_cell(labels: dict[str, str], ks: dict[str, int], columns=None) -> str:
    columns = columns or COLUMNS
    uniq = set(labels.values())
    text = next(iter(uniq)) if len(uniq) == 1 else "; ".join(f"{c}: {labels[c]}" for c in columns)
    small = [c for c in columns if 0 < ks[c] < report.MIN_SAMPLE]
    if small:
        text += f" ⚠ {report.SMALL_SAMPLE_WARNING}(30건 미만" + ("" if len(small) == len(columns) else ": " + ", ".join(small)) + ")"
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


def _section1(cols, sels, out: _Out, columns=None, rows=None) -> list[str]:
    columns = columns or COLUMNS
    L = ["| 지표 | " + " | ".join(columns) + " | 표본 |", "|---|" + "---|" * len(columns) + "---|"]
    want = lambda label: rows is None or label in rows  # noqa: E731
    built: dict[str, str] = {}

    def add(label, cells, labels, ks):
        built[label] = f"| {label} | " + " | ".join(cells[c] for c in columns) + f" | {_sample_cell(labels, ks, columns)} |"

    if want("성공률"):
        graded = {c: [r for r in cols[c] if r.run.passed is not None] for c in columns}
        cells, labels, ks = {}, {}, {}
        for c in columns:
            g = graded[c]
            ok = sum(r.run.passed for r in g)
            cells[c] = _fmt_rate(ok, len(g))
            labels[c], ks[c] = report.sample_label(_per_task(g)), len(g)
            out.rec("성공률", c, ok, len(g), _pct(ok, len(g)), labels[c])
        add("성공률", cells, labels, ks)
    if want("error_max_turns 건수"):
        cells, labels, ks = {}, {}, {}
        for c in columns:
            rs = cols[c]
            mt = [r for r in rs if r.run.subtype == "error_max_turns"]
            mp = sum(bool(r.run.passed) for r in mt)
            cells[c] = f"{len(mt)} (통과 {mp})" if rs else "n/a"
            labels[c], ks[c] = report.sample_label(_per_task(rs)), len(rs)
            out.rec("error_max_turns 건수", c, len(mt), len(rs), len(mt) if rs else None, labels[c])
        add("error_max_turns 건수", cells, labels, ks)

    if rows is not None and "정상 종료율" in rows:                                           # 1 - error_max_turns 비율
        cells, labels, ks = {}, {}, {}
        for c in columns:
            rs = cols[c]
            ok = sum(r.run.subtype != "error_max_turns" for r in rs)
            cells[c] = _fmt_rate(ok, len(rs))
            labels[c], ks[c] = report.sample_label(_per_task(rs)), len(rs)
            out.rec("정상 종료율", c, ok, len(rs), _pct(ok, len(rs)), labels[c])
        add("정상 종료율", cells, labels, ks)
    if rows is not None and "실패 유형" in rows:                                             # 채점기가 기록한 failure_type 그대로
        cells, labels, ks = {}, {}, {}
        for c in columns:
            rs = cols[c]
            cnt = Counter(r.run.failure_type or "unknown" for r in rs if r.run.passed is False)
            names = [k for k in report.FAILURE_TYPE_ORDER if k != "pass" and cnt.get(k)] + sorted(k for k in cnt if k not in report.FAILURE_TYPE_ORDER)
            cells[c] = ("n/a" if not rs else ", ".join(f"{k} {cnt[k]}" for k in names) if names else "실패 없음(0건)")
            labels[c], ks[c] = report.sample_label(_per_task(rs)), len(rs)
            out.rec("실패 유형", c, sum(cnt.values()), len(rs), sum(cnt.values()), labels[c])
        add("실패 유형", cells, labels, ks)
    if rows is not None and "error_max_turns 건수(비율)" in rows:                  # 실험 C 전용 행(다른 실험의 기본 행 목록에는 넣지 않는다)
        cells, labels, ks = {}, {}, {}
        for c in columns:
            rs = cols[c]
            k = sum(r.run.subtype == "error_max_turns" for r in rs)
            cells[c] = f"{k} ({100 * k / len(rs):.0f}%, {k}/{len(rs)})" if rs else "n/a"
            labels[c], ks[c] = report.sample_label(_per_task(rs)), len(rs)
            out.rec("error_max_turns 건수(비율)", c, k, len(rs), _pct(k, len(rs)), labels[c])
        add("error_max_turns 건수(비율)", cells, labels, ks)
    if rows is not None and "error_max_turns인데 채점 통과" in rows:
        cells, labels, ks = {}, {}, {}
        for c in columns:
            rs = cols[c]
            mt = [r for r in rs if r.run.subtype == "error_max_turns"]
            k = sum(bool(r.run.passed) for r in mt)
            cells[c] = f"{k}/{len(mt)}" if rs else "n/a"
            labels[c], ks[c] = report.sample_label(_per_task(rs)), len(rs)
            out.rec("error_max_turns인데 채점 통과", c, k, len(mt), _pct(k, len(mt)), labels[c])
        add("error_max_turns인데 채점 통과", cells, labels, ks)

    for name in ["search_text 선택률", "Grep 사용률", "file_stats 선택률", "Read 사용률", "check_result 사용률"]:
        if not want(name):
            continue
        cells, labels, ks = {}, {}, {}
        for c in columns:
            num, den, per = _rate(cols[c], sels[name])
            cells[c] = _fmt_rate(num, den)
            labels[c], ks[c] = report.sample_label(per), den
            out.rec(name, c, num, den, _pct(num, den), labels[c])
        add(name, cells, labels, ks)

    def mean_row(label, getter, fmt):
        if not want(label):
            return
        cells, labels, ks = {}, {}, {}
        for c in columns:
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

    for label, idx in (("일관성 (a) 도구 순서", 1), ("일관성 (b) 핵심 인자", 2)):
        if not want(label):
            continue
        cells, labels, ks = {}, {}, {}
        for c in columns:
            pairs, a, b, per = consistency(cols[c])
            eq = a if idx == 1 else b
            cells[c] = "n/a (0쌍)" if not pairs else f"{100 * eq / pairs:.0f}% ({eq}/{pairs}쌍)"
            labels[c], ks[c] = report.sample_label(per), sum(per.values())
            out.rec(label, c, eq, pairs, _pct(eq, pairs), labels[c])
        add(label, cells, labels, ks)
    order = rows if rows is not None else list(built)
    return L + [built[label] for label in order if label in built]


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


def _section5(cols, raw_dir, out: _Out, columns=None, probe_names=None, probe_models=None) -> list[str]:
    probe_models = probe_models or {}
    columns = columns or COLUMNS
    probe_names = probe_names or PROBE_NAMES
    L = ["| 설정 | 호출 | five_hour 시작 | five_hour 종료 | five_hour 델타 | seven_day 시작 | seven_day 종료 | 실행 수 | 비용 합계 |",
         "|---|---|---|---|---|---|---|---|---|"]
    extra = []
    for c in columns:
        recs = cols[c]
        starts = {}
        for p in sorted(Path(raw_dir).glob(f"probe_{probe_models.get(c, 'haiku')}_{probe_names[c]}_inv*_start.jsonl")):
            m = re.search(r"_inv(\d+)_start\.jsonl$", p.name)
            if m:
                starts[int(m.group(1))] = p
        wins = []
        for n, sp in sorted(starts.items()):
            ep = Path(raw_dir) / f"probe_{probe_models.get(c, 'haiku')}_{probe_names[c]}_inv{n}_end.jsonl"
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


def task_counts(recs: list[Rec], tasks: dict[str, loader.Task]) -> dict[str, dict]:
    """쌍 과제별 (커스텀 도구를 쓴 실행 수 k, 실행 수 m, 쌍 이름)."""
    out = {}
    for t in tasks.values():
        for pair in t.overlap_with:
            if pair not in ("search_text|Grep", "file_stats|Read"):
                continue
            rs = [r for r in recs if r.task == t.id]
            out[t.id] = {"k": sum(r.run.used_custom({pair.split("|")[0]}) for r in rs), "m": len(rs), "pair": pair}
    return out


def _section6(cols, tasks, out: _Out) -> list[str]:
    counts = {c: task_counts(cols[c], tasks) for c in COLUMNS}
    L = ["| 지표 | " + " | ".join(COLUMNS) + " | 표본 |", "|---|" + "---|" * len(COLUMNS) + "---|"]
    for pair, label in (("search_text|Grep", "search_text 쌍 과제 중 한 번이라도 쓴 과제 수"),
                        ("file_stats|Read", "file_stats 쌍 과제 중 한 번이라도 쓴 과제 수")):
        cells, labels, ks = {}, {}, {}
        for c in COLUMNS:
            sub = {t: v for t, v in counts[c].items() if v["pair"] == pair and v["m"] > 0}
            any_n = sum(v["k"] >= 1 for v in sub.values())
            all_n = sum(v["k"] == v["m"] for v in sub.values())
            cells[c] = f"{any_n}/{len(sub)} (3회 모두 {all_n})" if sub else "n/a"
            labels[c] = report.sample_label({t: v["m"] for t, v in sub.items()})
            ks[c] = len(sub)                         # 단위가 과제 수이므로 30 미만 경고는 과제 수 기준
            out.rec(label, c, any_n, len(sub), _pct(any_n, len(sub)), labels[c])
            out.rec(label + "(3회 모두)", c, all_n, len(sub), _pct(all_n, len(sub)), labels[c])
        L.append(f"| {label} | " + " | ".join(cells[c] for c in COLUMNS) + f" | {_sample_cell(labels, ks)} |")
    L.append("")
    for c in ("long", "long_directive"):
        up, down, same = [], [], 0
        for t in sorted(counts[c]):
            if t not in counts["default"] or not counts["default"][t]["m"] or not counts[c][t]["m"]:
                continue
            d, x = counts["default"][t], counts[c][t]
            item = f"{t}({d['k']}/{d['m']}→{x['k']}/{x['m']})"
            if x["k"] > d["k"]:
                up.append(item)
            elif x["k"] < d["k"]:
                down.append(item)
            else:
                same += 1
        for word, lst in (("늘어난", up), ("줄어든", down)):
            L.append(f"- {c} vs default {word} 과제 {len(lst)}개: " + (", ".join(lst) if lst else "없음"))
        L.append(f"- {c} vs default 같은 과제 {same}개")
        out.rec("default 대비 늘어난 과제 수", c, len(up), None, len(up), "")
        out.rec("default 대비 줄어든 과제 수", c, len(down), None, len(down), "")
    L += ["", "- 비교 단위는 과제 1개 x 3회(한 과제 3회 중 사용 횟수)라 1/3 → 2/3 같은 작은 차이는 우연 범위 안일 수 있다(표본이 작아 해석에 주의). 0/3 ↔ 3/3처럼 큰 변화만 참고한다(가설).",
          "- 늘어난/줄어든은 default의 3회 중 사용 횟수와 비교한 값이다. 과제 구성은 쌍 과제 20개(search_text 12, file_stats 8)."]
    return L


def build_compare(cols: dict[str, list[Rec]], raw_dir=".", tasks=None, out: _Out | None = None) -> str:
    tasks = tasks or {t.id: t for t in loader.load_all() if not t.is_todo}
    out = out if out is not None else _Out()
    sels = _selections(tasks)
    head = ["# 실험 A 비교표 (exp_compare)", "",
            "- 입력: " + ", ".join(f"{c} {len(cols[c])}건" for c in COLUMNS) + ". 최종 실행 로그만 읽는다(.partial, _final 제외). 읽기 전용, 모델 호출 없음.",
            "- 열 이름: default = 베이스라인(도구 설명 기본값), short = 짧은 설명, long = 정보 위주 긴 설명, long_directive = long + 우선 사용 지시 한 문장."]
    bodies = [_section1(cols, sels, out), _section2(cols, tasks, out), _section3(cols, sels, out), _section4(cols, sels, out),
              _section5(cols, raw_dir, out), _section6(cols, tasks, out)]
    lines = head + [""]
    for title, body in zip(SECTION_TITLES, bodies):
        lines += [title, ""] + body + [""]
    return "\n".join(lines)


def _section_b_tasks(cols, tasks, out: _Out) -> list[str]:
    """과제 x 설정: check_result를 쓴 횟수(3회 중). default 대비 verify, verify_tool에서 늘어난/줄어든 과제."""
    sel = {c: {} for c in COLUMNS_B}
    for c in COLUMNS_B:
        for t in tasks:
            rs = [r for r in cols[c] if r.task == t]
            sel[c][t] = (sum(r.run.used_custom({"check_result"}) for r in rs), len(rs))
    L = ["| 과제 | " + " | ".join(COLUMNS_B) + " |", "|---|" + "---|" * len(COLUMNS_B)]
    for t in sorted(tasks):
        cells = []
        for c in COLUMNS_B:
            k, m = sel[c][t]
            cells.append(f"{k}/{m}" if m else "n/a")
            if m:
                out.rec("과제별 check_result 사용 횟수", c, k, m, _pct(k, m), report.sample_label({t: m}), task=t)
        L.append(f"| {t} | " + " | ".join(cells) + " |")
    L.append("")
    for c in ("verify", "verify_tool"):
        up, down, same = [], [], 0
        for t in sorted(tasks):
            (dk, dm), (xk, xm) = sel["default"][t], sel[c][t]
            if not dm or not xm:
                continue
            item = f"{t}({dk}/{dm}→{xk}/{xm})"
            if xk > dk:
                up.append(item)
            elif xk < dk:
                down.append(item)
            else:
                same += 1
        for word, lst in (("늘어난", up), ("줄어든", down)):
            L.append(f"- {c} vs default {word} 과제 {len(lst)}개: " + (", ".join(lst) if lst else "없음"))
        L.append(f"- {c} vs default 같은 과제 {same}개")
        out.rec("default 대비 check_result 늘어난 과제 수", c, len(up), None, len(up), "")
        out.rec("default 대비 check_result 줄어든 과제 수", c, len(down), None, len(down), "")
    L += ["", f"- 칸마다 표본은 과제 1개 x 3회뿐이다(총 3건 < {report.MIN_SAMPLE}건). {report.SMALL_SAMPLE_WARNING}. 1/3 -> 2/3 같은 작은 차이는 우연 범위 안일 수 있다(가설)."]
    return L


def _section_pass_by_task(sub, columns, ids, out: _Out) -> list[str]:
    L = ["| 과제 | " + " | ".join(columns) + " |", "|---|" + "---|" * len(columns)]
    for t in ids:
        cells = []
        for c in columns:
            rs = [r for r in sub[c] if r.task == t and r.run.passed is not None]
            k = sum(bool(r.run.passed) for r in rs)
            cells.append(f"{k}/{len(rs)}" if rs else "n/a")
            if rs:
                out.rec("과제별 통과 횟수", c, k, len(rs), _pct(k, len(rs)), report.sample_label({t: len(rs)}), task=t)
        L.append(f"| {t} | " + " | ".join(cells) + " |")
    L += ["", f"- 칸마다 표본은 과제 1개 x 3회뿐이다(총 3건 < {report.MIN_SAMPLE}건). {report.SMALL_SAMPLE_WARNING}."]
    return L


def build_compare_e(cols: dict[str, list[Rec]], raw_dir=".", tasks=None, out: _Out | None = None) -> str:
    """실험 E: expA long(기준) vs expE long + file_stats 파일 이름 출력. 같은 (과제, run) 쌍만 비교하고 범위를 맨 위에 적는다."""
    tasks = tasks or {t.id: t for t in loader.load_all() if not t.is_todo}
    out = out if out is not None else _Out()
    sels = _selections(tasks)
    common = {(r.task, r.n) for r in cols["long"]} & {(r.task, r.n) for r in cols["long_filename"]}
    sub = {c: [r for r in cols[c] if (r.task, r.n) in common] for c in COLUMNS_E}
    ids = sorted({t for t, _ in common})
    head = ["# 실험 E 비교표 (exp_compare)", "",
            f"- 비교 범위: 같은 (과제, run) 쌍 {len(common)}건, 과제 {len(ids)}개({', '.join(ids)}). "
            f"expA long 전체 {len(cols['long'])}건 중 {len(common)}건, expE 전체 {len(cols['long_filename'])}건 중 {len(common)}건을 비교한다(나머지는 제외).",
            "- 열 이름: long = expA의 long 설정(비교 기준), long_filename = 같은 long 설정 + file_stats 출력 앞에 `path: <입력 경로>` 한 줄. "
            "도구 설명 long, 프롬프트 v1, max_turns 20, haiku로 같다.",
            "- 두 조건은 서로 다른 시기에 실행됐다(시기 효과는 분리하지 못함, 가설 수준으로만 해석).",
            "- 실패 유형은 채점기가 기록한 failure_type 그대로다."]
    out.rec("비교 범위(쌍 수)", "long-long_filename", len(common), None, len(common), ", ".join(ids))
    bodies = [_section1(sub, sels, out, COLUMNS_E, ROWS_E), _section_pass_by_task(sub, COLUMNS_E, ids, out),
              _section5(cols, raw_dir, out, COLUMNS_E, PROBE_NAMES_E)]
    lines = head + [""]
    for title, body in zip(SECTION_TITLES_E, bodies):
        lines += [title, ""] + body + [""]
    return "\n".join(lines)


def build_from_dir_e(raw_dir, tasks=None) -> str:
    return build_compare_e(collect(raw_dir, PREFIXES_E), raw_dir, tasks)


def build_compare_b(cols: dict[str, list[Rec]], raw_dir=".", tasks=None, out: _Out | None = None) -> str:
    """실험 B(검증 지시) 비교표: default, verify, verify_tool. 지표는 ROWS_B."""
    tasks = tasks or {t.id: t for t in loader.load_all() if not t.is_todo}
    out = out if out is not None else _Out()
    sels = _selections(tasks)
    head = ["# 실험 B 비교표 (exp_compare)", "",
            "- 입력: " + ", ".join(f"{c} {len(cols[c])}건" for c in COLUMNS_B) + ". 최종 실행 로그만 읽는다(.partial, _final 제외). 읽기 전용, 모델 호출 없음.",
            "- 열 이름: default = 베이스라인(프롬프트 v1), verify = v1 + 일반 검증 지시, verify_tool = verify + 결과를 확인할 도구가 있으면 쓰라는 지시. 도구 설명은 모두 default."]
    bodies = [_section1(cols, sels, out, COLUMNS_B, ROWS_B) + ["", CHECK_RESULT_NOTE], _section_b_tasks(cols, sorted(tasks), out),
              _section5(cols, raw_dir, out, COLUMNS_B, PROBE_NAMES_B)]
    lines = head + [""]
    for title, body in zip(SECTION_TITLES_B, bodies):
        lines += [title, ""] + body + [""]
    return "\n".join(lines)


def limit_verdict(max_turns: int, success_resp: list[int], error_resp: list[int]) -> str:
    """설정 max_turns별 한계 판정. 응답 수는 로그의 고유 message_id 개수. 규칙 후보: '응답 수가 max_turns를 넘으려 할 때 중단(>)' 대 '응답 수 >= max_turns면 중단(>=)'.

    - 응답 수 > 설정값인 success나 응답 수 != 설정값인 error_max_turns가 있으면 응답 수 규칙과 모순이라 확인 불가.
    - 한계에 걸린 실행이 없으면 확인 불가.
    - 에러가 모두 응답 수 == 설정값이고 응답 수 == 설정값인 success가 있으면 > 규칙 지지, >= 규칙 기각.
    - 같은 조건에서 응답 수 == 설정값인 success가 없으면 부분 지지(> 와 >= 구분은 확인 불가).
    """
    s_gt = sum(r > max_turns for r in success_resp)
    s_eq = sum(r == max_turns for r in success_resp)
    e_ne = sum(r != max_turns for r in error_resp)
    if s_gt or e_ne:
        return f"확인 불가(응답 수 규칙과 모순되는 실행이 있음: 응답 수 > 설정값인 success {s_gt}건, 응답 수 != 설정값인 error_max_turns {e_ne}건)"
    if not error_resp:
        top = max(success_resp, default=None)
        return f"확인 불가(한계에 걸린 실행 없음; 응답 수 == 설정값인 success {s_eq}건, success 응답 수 최대 {top})"
    if s_eq:
        return (f"지지(가설 수준): error_max_turns {len(error_resp)}건이 모두 응답 수 == 설정값이고 응답 수 > 설정값인 success가 없다 -> "
                f"응답 수가 max_turns를 넘으려 할 때 중단하는 규칙(> max_turns)과 맞다. 응답 수 == 설정값인 success {s_eq}건이 있어 "
                f"'응답 수 ≥ max_turns면 중단'(≥ 규칙)은 기각")
    return (f"부분 지지: error_max_turns {len(error_resp)}건이 모두 응답 수 == 설정값이고 응답 수 > 설정값인 success가 없다. "
            f"응답 수 == 설정값인 success가 없어 > 와 ≥ 구분은 확인 불가")


def _section_limit(cols, columns, out: _Out) -> list[str]:
    groups: dict[tuple[int, int], list[int]] = defaultdict(lambda: [0, 0])
    succ: dict[int, list[int]] = defaultdict(list)
    errs: dict[int, list[int]] = defaultdict(list)
    other = 0
    for c in columns:
        for r in cols[c]:
            m = r.run.config.get("max_turns")
            if m is None or r.run.subtype not in ("success", "error_max_turns"):
                other += 1
                continue
            resp = r.item.responses
            if r.run.subtype == "success":
                groups[(m, resp)][0] += 1
                succ[m].append(resp)
            else:
                groups[(m, resp)][1] += 1
                errs[m].append(resp)
    L = ["| 설정 max_turns | 모델 응답 수 | success | error_max_turns | 합계 |", "|---|---|---|---|---|"]
    for (m, resp), (ok, er) in sorted(groups.items()):
        L.append(f"| {m} | {resp} | {ok} | {er} | {ok + er} |")
        out.rec("한계 판정 표(success)", f"max_turns{m}", ok, ok + er, None, f"응답 수 {resp}")
        out.rec("한계 판정 표(error_max_turns)", f"max_turns{m}", er, ok + er, None, f"응답 수 {resp}")
    L.append("")
    for m in sorted({m for m, _ in groups}):
        verdict = limit_verdict(m, succ[m], errs[m])
        line = f"- max_turns {m}: {verdict}"
        if errs[m]:
            line += f". 한계에 걸린 실행 {len(errs[m])}건 중 응답 수가 설정값과 같은 실행 {sum(r == m for r in errs[m])}건"
        L.append(line)
        out.rec("한계 판정", f"max_turns{m}", None, None, None, verdict)
    if other:
        L.append(f"- success, error_max_turns가 아닌 종료(또는 max_turns 기록 없음) {other}건은 이 표에서 제외했다.")
    L += ["- 응답 수 = assistant 메시지의 고유 message_id 개수(baseline_report와 같은 정의). 같은 응답 안의 병렬 도구 호출은 한 번으로 센다.",
          "- error_max_turns는 num_turns가 설정값+1로 보고될 수 있어(관찰: Day 3) 응답 수로 비교한다. 이 표는 관찰이며 한계 판정 규칙(>, ≥)은 가설이다.",
          "- 칸의 건수가 작아(대부분 30건 미만) 해석에 주의. 판정이 안 되면 확인 불가로 표시한다."]
    return L


def build_compare_c(cols: dict[str, list[Rec]], raw_dir=".", tasks=None, out: _Out | None = None) -> str:
    """실험 C(max_turns) 비교표: default(20, baseline), 3, 4, 5, 7."""
    tasks = tasks or {t.id: t for t in loader.load_all() if not t.is_todo}
    out = out if out is not None else _Out()
    sels = _selections(tasks)
    head = ["# 실험 C 비교표 (exp_compare)", "",
            "- 입력: " + ", ".join(f"{c} {len(cols[c])}건" for c in COLUMNS_C) + ". 최종 실행 로그만 읽는다(.partial, _final 제외). 읽기 전용, 모델 호출 없음.",
            "- 열 이름 = 설정 max_turns(default = baseline의 max_turns 20). 도구 설명 default, 프롬프트 v1, 모델 haiku로 같다.",
            "- 성공률은 채점 통과 기준이라 error_max_turns인데 통과한 실행도 포함한다(그 건수는 별도 행)."]
    bodies = [_section1(cols, sels, out, COLUMNS_C, ROWS_C), _section_limit(cols, COLUMNS_C, out),
              _section5(cols, raw_dir, out, COLUMNS_C, PROBE_NAMES_C)]
    lines = head + [""]
    for title, body in zip(SECTION_TITLES_C, bodies):
        lines += [title, ""] + body + [""]
    return "\n".join(lines)


def build_from_dir_c(raw_dir, tasks=None) -> str:
    return build_compare_c(collect(raw_dir, PREFIXES_C), raw_dir, tasks)


def build_compare_d(cols: dict[str, list[Rec]], raw_dir=".", tasks=None, out: _Out | None = None) -> str:
    """실험 D(모델 비교): 같은 (과제, run) 쌍에 대해서만 haiku baseline과 sonnet을 비교한다. 비교 범위를 맨 위에 적는다."""
    tasks = tasks or {t.id: t for t in loader.load_all() if not t.is_todo}
    out = out if out is not None else _Out()
    sels = _selections(tasks)
    common = {(r.task, r.n) for r in cols["haiku"]} & {(r.task, r.n) for r in cols["sonnet"]}
    sub = {c: [r for r in cols[c] if (r.task, r.n) in common] for c in COLUMNS_D}
    ids = sorted({t for t, _ in common})
    head = ["# 실험 D 비교표 (exp_compare)", "",
            f"- 비교 범위: 같은 (과제, run) 쌍 {len(common)}건, 과제 {len(ids)}개({', '.join(ids)}). "
            f"haiku baseline 전체 {len(cols['haiku'])}건 중 {len(common)}건, sonnet 전체 {len(cols['sonnet'])}건 중 {len(common)}건을 비교한다(나머지는 제외).",
            "- 입력: 최종 실행 로그만 읽는다(.partial, _final 제외). 읽기 전용, 모델 호출 없음. 도구 설명 default, 프롬프트 v1, max_turns 20으로 같다.",
            "- 일관성은 같은 과제의 반복이 2회 이상인 쌍에서만 계산되어, 과제당 1회 시험이면 n/a다."]
    out.rec("비교 범위(쌍 수)", "haiku-sonnet", len(common), None, len(common), ", ".join(ids))
    bodies = [_section1(sub, sels, out, COLUMNS_D, ROWS_D), _section5(cols, raw_dir, out, COLUMNS_D, PROBE_NAMES_D, PROBE_MODELS_D)]
    lines = head + [""]
    for title, body in zip(SECTION_TITLES_D, bodies):
        lines += [title, ""] + body + [""]
    return "\n".join(lines)


def build_from_dir_d(raw_dir, tasks=None) -> str:
    return build_compare_d(collect(raw_dir, PREFIXES_D), raw_dir, tasks)


def build_from_dir_b(raw_dir, tasks=None) -> str:
    return build_compare_b(collect(raw_dir, PREFIXES_B), raw_dir, tasks)


def build_from_dir(raw_dir, tasks=None) -> str:
    return build_compare(collect(raw_dir), raw_dir, tasks)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="실험 비교표(읽기 전용, 모델 호출 없음)")
    ap.add_argument("--exp", choices=["A", "B", "C", "D", "E"], default="A",
                    help="A: default/short/long/long_directive, B: default/verify/verify_tool, C: default/max_turns 3,4,5,7, D: haiku vs sonnet, E: long vs long + 파일 이름 출력")
    ap.add_argument("--raw-dir", default="results/raw")
    ap.add_argument("--out-md", default=None)
    ap.add_argument("--out-csv", default=None)
    a = ap.parse_args(argv)
    if a.out_md is None:
        a.out_md = f"results/exp{a.exp}_haiku_compare_summary_inv1.md"
    if a.out_csv is None:
        a.out_csv = f"results/exp{a.exp}_haiku_compare_runs.csv"
    prefixes = {"A": PREFIXES, "B": PREFIXES_B, "C": PREFIXES_C, "D": PREFIXES_D, "E": PREFIXES_E}[a.exp]
    builder = {"A": build_compare, "B": build_compare_b, "C": build_compare_c, "D": build_compare_d, "E": build_compare_e}[a.exp]
    cols = collect(a.raw_dir, prefixes)
    baseline_keys = {"A": set(), "B": {"default"}, "C": {"default"}, "D": {"haiku"}, "E": {"long"}}[a.exp]
    if not any(v for k, v in cols.items() if k not in baseline_keys):
        print("읽을 로그가 없다" if a.exp == "A" else f"실험 {a.exp} 로그가 없다(baseline만 있거나 비어 있음)", file=sys.stderr)
        return 1
    out = _Out()
    text = builder(cols, a.raw_dir, None, out)
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
