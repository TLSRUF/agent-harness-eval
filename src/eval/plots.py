"""그래프 생성 스크립트 (읽기 전용, 모델 호출 없음).

results/raw의 실행 로그를 읽어 results/figures/*.png를 만든다. 로그는 바꾸지 않고, 그림 파일만 출력 폴더에 쓴다.
- 표본 크기(N, 과제당 M회, 총 건수)는 report.sample_label과 같은 규칙으로 센 값을 그림 제목에 자동으로 넣는다(영어 라벨일 때는 같은 값을 영어 문구로).
- 한글 폰트를 찾지 못하면 영어 라벨로 그린다. 개인 경로나 사용자 이름은 제목, 라벨, PNG 메타데이터에 넣지 않는다.
- 각 그림은 만들 수 없으면(해당 실험 로그 없음) 건너뛰고 이유를 알려 준다.

사용: python -m src.eval.plots [--raw-dir results/raw] [--out-dir results/figures] [--lang auto|ko|en]
"""
from __future__ import annotations

import argparse
import statistics
import sys
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.ticker import FuncFormatter, NullFormatter  # noqa: E402

from . import exp_compare as ec  # noqa: E402
from . import loader, report  # noqa: E402

DEFAULT_RAW_DIR = "results/raw"
DEFAULT_OUT_DIR = "results/figures"
FIGURE_NAMES = ["fig1_expA_selection.png", "fig2_expB_check_result.png", "fig3_expC_pass_vs_normal.png",
                "fig4_expD_cost_responses.png", "fig5_expEF_pass_by_task.png", "fig6_consistency.png"]
KO_FONTS = ["Malgun Gothic", "NanumGothic", "NanumBarunGothic", "AppleGothic", "Noto Sans CJK KR", "Noto Sans KR", "Source Han Sans KR"]
PALETTE = ["#4c78a8", "#f58518", "#54a24b", "#b279a2", "#e45756", "#9d755d"]   # 색약에서도 구분되는 범주 색
DPI = 130


class Skip(Exception):
    """이 그림을 만들 데이터가 없다(이유를 메시지에 담는다)."""


@dataclass
class Fig:
    name: str
    path: Path | None
    title: str
    data: dict = field(default_factory=dict)
    panel_titles: dict = field(default_factory=dict)        # 패널별 제목(표본 크기 포함), 테스트와 점검용


# ---------------- 언어, 폰트, 표본 문구 ----------------

def detect_lang(font_names) -> tuple[str, str | None]:
    """설치된 글꼴 이름 목록에서 한글 글꼴을 찾는다. 있으면 ("ko", 글꼴), 없으면 ("en", None)."""
    names = set(font_names)
    for f in KO_FONTS:
        if f in names:
            return "ko", f
    return "en", None


def sample_text(per_task: dict[str, int], lang: str) -> str:
    """report.sample_label과 같은 규칙(과제 수, 과제당 횟수의 최소~최대, 총 건수)을 영어로도 낸다."""
    if lang == "ko":
        return report.sample_label(per_task)
    n, k = len(per_task), sum(per_task.values())
    if n == 0:
        return "N=0 tasks, 0 runs per task / total 0 runs"
    lo, hi = min(per_task.values()), max(per_task.values())
    m = f"{lo}" if lo == hi else f"{lo}~{hi}"
    mm = "" if lo == hi else f" (min {lo})"
    return f"N={n} tasks, {m} runs per task{mm} / total {k} runs"


def _label(per_by_series: dict[str, dict[str, int]], lang: str) -> str:
    labels = {c: sample_text(p, lang) for c, p in per_by_series.items()}
    uniq = set(labels.values())
    return next(iter(uniq)) if len(uniq) == 1 else "; ".join(f"{c}: {v}" for c, v in labels.items())


def _small(dens: list[int], lang: str) -> str:
    return (" [!] 소표본(30건 미만)" if lang == "ko" else " [!] small sample (<30 runs)") if any(0 < d < report.MIN_SAMPLE for d in dens) else ""


def _tr(lang: str, ko: str, en: str) -> str:
    return ko if lang == "ko" else en


def _pct(num: int, den: int) -> float:
    return 100 * num / den if den else 0.0


# ---------------- 공통 그리기 ----------------

def _save(fig, out_dir: Path, name: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / name
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Glyph .* missing")
        fig.savefig(p, dpi=DPI, bbox_inches="tight", metadata={"Software": None})   # 생성 도구 메타데이터도 넣지 않는다
    plt.close(fig)
    return p


def _bar_rates(ax, series: dict[str, dict[str, tuple[int, int]]], ylabel: str):
    """series: {범례 이름: {x 이름: (분자, 분모)}}. 퍼센트 막대와 'k/n' 표기."""
    xs = list(next(iter(series.values())))
    w = 0.8 / len(series)
    for i, (name, vals) in enumerate(series.items()):
        pos = [j + (i - (len(series) - 1) / 2) * w for j in range(len(xs))]
        ys = [_pct(*vals[x]) for x in xs]
        bars = ax.bar(pos, ys, w, label=name, color=PALETTE[i % len(PALETTE)])
        for b, x in zip(bars, xs):
            k, n = vals[x]
            ax.annotate(f"{k}/{n}", (b.get_x() + b.get_width() / 2, b.get_height()), ha="center", va="bottom", fontsize=7)
    ax.set_xticks(range(len(xs)), xs)
    ax.set_ylim(0, 112)
    ax.set_ylabel(ylabel)
    if len(series) > 1:
        ax.legend(fontsize=8, loc="lower right")


def _title(fig, head: str, label: str, fontsize: int = 10):
    fig.subplots_adjust(top=0.78)                      # 두 줄 제목이 각 그림의 부제목과 겹치지 않게 위쪽 여백을 둔다
    fig.suptitle(head + "\n" + label, fontsize=fontsize, y=0.995)


# ---------------- 그림 1~6 ----------------

def fig1(cols, tasks, lang, out_dir):
    cs = [c for c in ec.COLUMNS if cols["A"][c]]
    if len(cs) < 2:
        raise Skip("실험 A 로그가 2개 설정 미만")
    sels = ec._selections(tasks)
    data, pers, dens = {}, {}, []
    for key, name in (("search_text", "search_text 선택률"), ("file_stats", "file_stats 선택률")):
        data[key], pers[key] = {}, {}
        for c in cs:
            num, den, per = ec._rate(cols["A"][c], sels[name])
            data[key][c] = (num, den)
            pers[key][c] = per
            dens.append(den)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), sharey=True)
    for ax, key, ttl in zip(axes, ("search_text", "file_stats"), (_tr(lang, "search_text 선택률 (search_text|Grep 쌍 과제)", "search_text selection rate (search_text|Grep tasks)"),
                                                                 _tr(lang, "file_stats 선택률 (file_stats|Read 쌍 과제)", "file_stats selection rate (file_stats|Read tasks)"))):
        _bar_rates(ax, {_tr(lang, "선택률", "selection rate"): data[key]}, _tr(lang, "선택률(%)", "selection rate (%)"))
        ax.set_title(ttl, fontsize=9)
    label = _tr(lang, "search_text ", "search_text ") + _label(pers["search_text"], lang) + "; file_stats " + _label(pers["file_stats"], lang) + _small(dens, lang)
    head = _tr(lang, "실험 A: 도구 설명별 커스텀 도구 선택률", "Experiment A: custom-tool selection rate by tool description")
    _title(fig, head, label)
    return Fig(FIGURE_NAMES[0], _save(fig, out_dir, FIGURE_NAMES[0]), head + "\n" + label, data)


def fig2(cols, tasks, lang, out_dir):
    cs = [c for c in ec.COLUMNS_B if cols["B"][c]]
    if len(cs) < 2:
        raise Skip("실험 B 로그가 2개 설정 미만")
    sels = ec._selections(tasks)
    data, pers, dens = {}, {}, []
    for c in cs:
        num, den, per = ec._rate(cols["B"][c], sels["check_result 사용률"])
        data[c], pers[c] = (num, den), per
        dens.append(den)
    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    _bar_rates(ax, {_tr(lang, "check_result 사용률", "check_result use rate"): data}, _tr(lang, "사용률(%)", "use rate (%)"))
    label = _label(pers, lang) + _small(dens, lang)
    head = _tr(lang, "실험 B: 설정별 check_result 사용률 (검증 행동의 증가, 정확성의 증가는 아님)", "Experiment B: check_result use rate by prompt (more verification, not more accuracy)")
    _title(fig, head, label)
    return Fig(FIGURE_NAMES[1], _save(fig, out_dir, FIGURE_NAMES[1]), head + "\n" + label, {"check_result": data})


def fig3(cols, tasks, lang, out_dir):
    order = [("3", 3), ("4", 4), ("5", 5), ("7", 7), ("default", 20)]
    have = [(k, x) for k, x in order if cols["C"][k]]
    if len(have) < 2:
        raise Skip("실험 C 로그가 2개 max_turns 미만")
    xs = [x for _, x in have]
    pas, normal, pers, dens = {}, {}, {}, []
    for k, x in have:
        rs = cols["C"][k]
        g = [r for r in rs if r.run.passed is not None]
        pas[x] = (sum(bool(r.run.passed) for r in g), len(g))
        normal[x] = (sum(r.run.subtype != "error_max_turns" for r in rs), len(rs))
        pers[str(x)] = ec._per_task(rs)
        dens.append(len(rs))
    fig, ax = plt.subplots(figsize=(6.8, 4.2))
    pos = list(range(len(xs)))
    ax.plot(pos, [_pct(*pas[x]) for x in xs], marker="o", color=PALETTE[0], label=_tr(lang, "채점 통과율", "grading pass rate"))
    ax.plot(pos, [_pct(*normal[x]) for x in xs], marker="s", linestyle="--", color=PALETTE[1], label=_tr(lang, "정상 종료율 (1 - error_max_turns 비율)", "normal-termination rate (1 - error_max_turns rate)"))
    ax.set_xticks(pos, [str(x) + _tr(lang, " (기본)", " (default)") if x == 20 else str(x) for x in xs])
    ax.set_xlabel("max_turns")
    ax.set_ylabel(_tr(lang, "비율(%)", "rate (%)"))
    ax.set_ylim(0, 105)
    ax.legend(fontsize=8, loc="lower right")
    label = _label(pers, lang) + _small(dens, lang)
    head = _tr(lang, "실험 C: max_turns별 채점 통과율과 정상 종료율", "Experiment C: grading pass rate and normal-termination rate by max_turns")
    _title(fig, head, label)
    return Fig(FIGURE_NAMES[2], _save(fig, out_dir, FIGURE_NAMES[2]), head + "\n" + label, {"x": xs, "pass": pas, "normal": normal})


def fig4(cols, tasks, lang, out_dir):
    common = {(r.task, r.n) for r in cols["D"]["haiku"]} & {(r.task, r.n) for r in cols["D"]["sonnet"]}
    if not common:
        raise Skip("실험 D: haiku와 sonnet에 같은 (과제, run) 쌍이 없음")
    sub = {c: [r for r in cols["D"][c] if (r.task, r.n) in common] for c in ec.COLUMNS_D}

    def mean(rs, get):
        v = [get(r) for r in rs if get(r) is not None]
        return statistics.mean(v) if v else None

    cost = {c: mean(sub[c], lambda r: r.run.cost) for c in ec.COLUMNS_D}
    resp = {c: mean(sub[c], lambda r: r.item.responses) for c in ec.COLUMNS_D}
    if any(v is None or v <= 0 for v in cost.values()):
        raise Skip("실험 D: 비용 기록이 없어 로그 축을 그릴 수 없음")
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(8.5, 4.2))
    for ax, vals, ttl, fmt in ((a1, cost, _tr(lang, "실행당 평균 비용 (로그 축, USD)", "mean cost per run (log axis, USD)"), "${:.4f}"),
                               (a2, resp, _tr(lang, "실행당 평균 모델 응답 수", "mean model responses per run"), "{:.1f}")):
        bars = ax.bar(list(vals), [vals[c] or 0 for c in vals], color=PALETTE[:2])
        for b, c in zip(bars, vals):
            ax.annotate(fmt.format(vals[c]), (b.get_x() + b.get_width() / 2, b.get_height()), ha="center", va="bottom", fontsize=8)
        ax.set_title(ttl, fontsize=9)
    a1.set_yscale("log")
    a1.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:g}"))      # 로그 축 눈금을 일반 글자로(수학 글꼴의 유니코드 빼기 기호 경고를 피한다)
    a1.yaxis.set_minor_formatter(NullFormatter())
    a1.set_ylim(min(cost.values()) / 3, max(cost.values()) * 3)
    a2.set_ylim(0, max(resp.values()) * 1.25)
    label = _label({c: ec._per_task(sub[c]) for c in ec.COLUMNS_D}, lang) + _tr(lang, f" (같은 쌍 {len(common)}건)", f" (same {len(common)} pairs)") + _small([len(common)], lang)
    head = _tr(lang, "실험 D: 같은 과제 집합에서 haiku vs sonnet", "Experiment D: haiku vs sonnet on the same task set")
    _title(fig, head, label)
    return Fig(FIGURE_NAMES[3], _save(fig, out_dir, FIGURE_NAMES[3]), head + "\n" + label,
               {"pairs": len(common), "scale": "log", "cost": cost, "responses": resp})


def _pass_by_task(cols_x, cs, base, other):
    common = {(r.task, r.n) for r in cols_x[base]} & {(r.task, r.n) for r in cols_x[other]}
    sub = {c: [r for r in cols_x[c] if (r.task, r.n) in common] for c in cs}
    ids = sorted({t for t, _ in common})
    data = {}
    for c in cs:
        data[c] = {}
        for t in ids:
            g = [r for r in sub[c] if r.task == t and r.run.passed is not None]
            data[c][t] = (sum(bool(r.run.passed) for r in g), len(g))
    return data, sub, len(common)


def fig5(cols, tasks, lang, out_dir):
    """실험 E는 주 비교(같은 날 연달아 돌린 expEctl 대 expE, H01만)와 보조 비교(3일 전 expA long 대 expE)를 따로 그리고, 실험 F를 옆에 둔다.
    패널 제목마다 그 패널의 표본 크기(과제 수, 과제당 횟수, 총 건수)를 붙인다."""
    specs = (("E", "E", ec.COLUMNS_E_MAIN, "실험 E 주 비교 (expEctl 대 expE, 같은 날)", "Experiment E main (expEctl vs expE, same day)"),
             ("E_aux", "E", ec.COLUMNS_E, "실험 E 보조 (expA long 대 expE, 3일 전)", "Experiment E auxiliary (expA long vs expE, 3 days earlier)"),
             ("F", "F", ec.COLUMNS_F, "실험 F (search_text 출력에 일치 개수)", "Experiment F (match count in search_text output)"))
    panels = []
    for key, src, cs, ttl_ko, ttl_en in specs:
        cx = cols[src]
        if cx[cs[0]] and cx[cs[1]]:
            data, sub, n = _pass_by_task(cx, cs, cs[0], cs[1])
            if n:
                label = _label({c: ec._per_task(sub[c]) for c in cs}, lang)
                panels.append((key, cs, data, sub, n, _tr(lang, ttl_ko, ttl_en) + "\n" + label))
    if not panels:
        raise Skip("실험 E, F 로그가 없음")
    fig, axes = plt.subplots(1, len(panels), figsize=(5.6 * len(panels), 4.2), squeeze=False)
    labels, dens, data_out, panel_titles = [], [], {}, {}
    for ax, (key, cs, data, sub, n, ttl) in zip(axes[0], panels):
        ids = list(data[cs[0]])
        w = 0.8 / len(cs)
        top = 1
        for i, c in enumerate(cs):
            pos = [j + (i - (len(cs) - 1) / 2) * w for j in range(len(ids))]
            ks = [data[c][t][0] for t in ids]
            top = max(top, *(data[c][t][1] for t in ids))
            ax.bar(pos, ks, w, label=c, color=PALETTE[i])
        ax.set_xticks(range(len(ids)), ids, rotation=45, fontsize=8)
        ax.set_ylim(0, top + 0.8)
        ax.set_yticks(range(0, top + 1))
        ax.set_ylabel(_tr(lang, f"통과 횟수 (최대 {top}회)", f"passes (max {top} runs)"))
        ax.set_title(ttl, fontsize=8)
        ax.legend(fontsize=8, loc="lower right")
        labels.append(f"{key}: " + _label({c: ec._per_task(sub[c]) for c in cs}, lang))
        dens.append(n)
        data_out[key] = data
        panel_titles[key] = ttl
    label = "; ".join(labels) + _small(dens, lang)
    head = _tr(lang, "실험 E(주 비교: expEctl 대 expE, 보조: expA long 대 expE)와 F: 조건별 과제별 통과 횟수",
               "Experiments E (main: expEctl vs expE; auxiliary: expA long vs expE) and F: passes per task by condition")
    _title(fig, head, label, fontsize=9)
    return Fig(FIGURE_NAMES[4], _save(fig, out_dir, FIGURE_NAMES[4]), head + "\n" + label, data_out, panel_titles)


def fig6(cols, tasks, lang, out_dir):
    series = {c: cols["A"][c] for c in ec.COLUMNS}
    series.update({c: cols["B"][c] for c in ("verify", "verify_tool")})
    order, args, pers = {}, {}, {}
    for c, rs in series.items():
        pairs, a, b, per = ec.consistency(rs)
        if pairs:
            order[c], args[c], pers[c] = (a, pairs), (b, pairs), per
    if not order:
        raise Skip("일관성을 계산할 반복 2회 이상의 로그가 없음")
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 4.2), sharey=True)
    _bar_rates(a1, {_tr(lang, "일치율", "agreement"): order}, _tr(lang, "쌍 일치율(%)", "pair agreement (%)"))
    _bar_rates(a2, {_tr(lang, "일치율", "agreement"): args}, _tr(lang, "쌍 일치율(%)", "pair agreement (%)"))
    a1.set_title(_tr(lang, "(a) 도구 호출 순서 일치율", "(a) tool-call order agreement"), fontsize=9)
    a2.set_title(_tr(lang, "(b) 핵심 인자까지 일치율", "(b) tool name + key-argument agreement"), fontsize=9)
    for ax in (a1, a2):
        ax.tick_params(axis="x", labelrotation=30, labelsize=8)
    label = _label(pers, lang) + _tr(lang, " (같은 과제의 실행 쌍 기준)", " (pairs of runs of the same task)") + _small([sum(p for _, p in order.values())], lang)
    head = _tr(lang, "일관성: 설정별 도구 순서와 핵심 인자 일치율", "Consistency: tool-order and key-argument agreement by config")
    _title(fig, head, label)
    return Fig(FIGURE_NAMES[5], _save(fig, out_dir, FIGURE_NAMES[5]), head + "\n" + label, {"order": order, "args": args})


BUILDERS = [fig1, fig2, fig3, fig4, fig5, fig6]


# ---------------- 진입점 ----------------

def generate_all(raw_dir, out_dir, lang: str | None = None, tasks=None) -> tuple[list[Fig], list[str]]:
    """그림을 모두 만든다. 반환: (만든 그림 목록, 건너뛴 그림과 이유 목록). 입력 로그는 읽기만 한다."""
    names = {f.name for f in font_manager.fontManager.ttflist}
    auto_lang, font = detect_lang(names)
    if lang in (None, "auto"):
        lang = auto_lang
    if lang == "ko" and font:
        plt.rcParams["font.family"] = font
    plt.rcParams["axes.unicode_minus"] = False
    tasks = tasks or {t.id: t for t in loader.load_all() if not t.is_todo}
    cols = {"A": ec.collect(raw_dir, ec.PREFIXES), "B": ec.collect(raw_dir, ec.PREFIXES_B), "C": ec.collect(raw_dir, ec.PREFIXES_C),
            "D": ec.collect(raw_dir, ec.PREFIXES_D), "E": ec.collect(raw_dir, ec.PREFIXES_E), "F": ec.collect(raw_dir, ec.PREFIXES_F)}
    figs, skipped = [], []
    for build, name in zip(BUILDERS, FIGURE_NAMES):
        try:
            figs.append(build(cols, tasks, lang, Path(out_dir)))
        except Skip as e:
            skipped.append(f"{name}: {e}")
    return figs, skipped


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="실험 결과 그래프(읽기 전용, 모델 호출 없음)")
    ap.add_argument("--raw-dir", default=DEFAULT_RAW_DIR)
    ap.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    ap.add_argument("--lang", choices=["auto", "ko", "en"], default="auto", help="auto: 한글 글꼴이 있으면 ko, 없으면 en")
    a = ap.parse_args(argv)
    figs, skipped = generate_all(a.raw_dir, a.out_dir, a.lang)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    for f in figs:
        print(f"{f.path.name}: {f.title.splitlines()[0]}")
    for s in skipped:
        print("건너뜀 - " + s, file=sys.stderr)
    return 0 if figs else 1


if __name__ == "__main__":
    sys.exit(main())
