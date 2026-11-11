"""베이스라인 보고서: 난이도별 성공률, 턴 수 분포, 반복 간 성패가 갈린 과제, 검색 도구 사용, 호출/응답/num_turns 비교.

읽기 전용(모델 호출 없음). 출력 형식은 tests/test_baseline_report.py가 고정한다.
사용: python -m src.eval.baseline_report "results/raw/baseline_haiku_default_*_run*.jsonl"
입력은 `..._run{n}.jsonl`만 읽는다(.partial 보관본, _final 스냅샷 폴더는 제외).
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import re
import statistics
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from src.agent.tools import classify_tool

from . import loader, report

SECTION_TITLES = [
    "a. 난이도별 성공률",
    "b. 과제별 턴 수 분포",
    "c. 반복 간 성패가 갈린 과제",
    "d. 검색 도구 사용 (search_text|Grep 쌍 과제)",
    "e. 실행별 도구 호출 수, 모델 응답 수, 보고된 num_turns",
    "report.py 출력",
]
DIFFICULTY = {"E": "쉬움", "M": "보통", "H": "어려움"}
SEARCH_PAIR = "search_text|Grep"
CEILING = 0.90
RUN_RE = re.compile(r"_run(\d+)\.jsonl$")


@dataclass
class Item:
    run: report.Run
    n: int                 # 반복 번호(파일명)
    responses: int         # 고유 message_id 개수(assistant 메시지 기준)
    no_id: int             # message_id가 없는 assistant 메시지 수
    msg_multi: int         # 한 AssistantMessage 안에 tool_use가 2개 이상인 메시지 수
    id_multi: int          # 같은 message_id 아래 tool_use 합이 2개 이상인 응답 수
    max_in_id: int         # 한 응답 아래 tool_use 최대 개수

    @property
    def task(self) -> str:
        return self.run.task_id

    @property
    def label(self) -> str:
        return f"{self.task}_run{self.n}"

    @property
    def diff(self) -> str:
        return DIFFICULTY.get(self.task[:1], "기타")

    @property
    def outcome(self) -> str:
        if self.run.passed is None:
            return "채점없음"
        return self.run.failure_type or ("pass" if self.run.passed else "fail")


def load_item(path: Path) -> Item:
    run = report.load_run(path)
    by_id: Counter = Counter()
    no_id = msg_multi = 0
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        ev = json.loads(line)
        if ev.get("kind") != "message":
            continue
        m = ev["message"]
        if m.get("_type") != "AssistantMessage":
            continue
        n_tool = sum(1 for b in m.get("content", []) if isinstance(b, dict) and b.get("_type") == "ToolUseBlock")
        msg_multi += n_tool >= 2
        mid = m.get("message_id")
        if mid is None:
            no_id += 1
        else:
            by_id[mid] += n_tool
    return Item(run=run, n=int(RUN_RE.search(Path(path).name).group(1)), responses=len(by_id), no_id=no_id, msg_multi=msg_multi,
                id_multi=sum(1 for v in by_id.values() if v >= 2), max_in_id=max(by_id.values(), default=0))


def _fmt(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else f"{x:.1f}"


def _pct(num: int, den: int) -> str:
    return "n/a" if den == 0 else f"{100 * num / den:.0f}%"


def _per_task(items: list[Item]) -> dict[str, int]:
    return dict(Counter(i.task for i in items))


def _graded(items: list[Item]) -> list[Item]:
    return [i for i in items if i.run.passed is not None]


def _split_tasks(items: list[Item]) -> dict[str, list[Item]]:
    by: dict[str, list[Item]] = {}
    for i in _graded(items):
        by.setdefault(i.task, []).append(i)
    return {t: sorted(v, key=lambda x: x.n) for t, v in by.items() if any(x.run.passed for x in v) and not all(x.run.passed for x in v)}


# ---------------- 섹션 ----------------

def section_a(items: list[Item]) -> list[str]:
    g = _graded(items)
    L = ["| 난이도 | 통과 | 채점된 실행 | 성공률 | 표본 |", "|---|---|---|---|---|"]
    by_diff: dict[str, tuple[int, int]] = {}
    for letter, name in DIFFICULTY.items():
        rs = [i for i in g if i.task[:1] == letter]
        if rs:
            ok = sum(i.run.passed for i in rs)
            by_diff[name] = (ok, len(rs))
            L.append(f"| {name} | {ok} | {len(rs)} | {_pct(ok, len(rs))} | {report.sample_label(_per_task(rs))} |")
    ok_all = sum(i.run.passed for i in g)
    L.append(f"| 전체 | {ok_all} | {len(g)} | {_pct(ok_all, len(g))} | {report.sample_label(_per_task(g))} |")
    ungraded = len(items) - len(g)
    L += ["", f"- 채점 없음 {ungraded}건(성공률 분모에서 제외)"]
    L.append("")
    if not g:
        L.append("천장 효과 점검: 채점된 실행이 없다")
    elif ok_all / len(g) >= CEILING:
        diffs = ", ".join(f"{n} {a}/{b}" for n, (a, b) in by_diff.items())
        L += [f"[천장 효과 알림] 베이스라인 전체 성공률 {ok_all}/{len(g)} = {_pct(ok_all, len(g))} ({report.sample_label(_per_task(g))}). 90% 이상입니다.",
              f"- 난이도별: {diffs}",
              f"- 성패가 갈린 과제: {len(_split_tasks(items))}개",
              "- 영향(가설): 도구 설명, 검증 단계 같은 설정이 성공률을 거의 못 바꿀 수 있어, 성공률 외에 턴 수, 비용, 선택률 변화가 주된 지표가 될 수 있다.",
              "- 확인 요청: 난이도별(특히 성패가 갈린 과제) 결과 중심으로 해석할까요? (예/아니오)"]
    else:
        L.append(f"천장 효과 점검: 전체 성공률 {_pct(ok_all, len(g))} (90% 미만, 알림 없음)")
        full = [f"{n}({a}/{b})" for n, (a, b) in by_diff.items() if a == b]
        if full:
            L.append(f"- 난이도별 100%: {', '.join(full)}")
    return L


def section_b(items: list[Item]) -> list[str]:
    L = ["| 과제 | 난이도 | 실행 수 | 최소 | 중앙값 | 최대 | error_max_turns |", "|---|---|---|---|---|---|---|"]
    for t in sorted({i.task for i in items}):
        rs = [i for i in items if i.task == t]
        turns = [i.run.num_turns for i in rs if i.run.num_turns is not None]
        mt = sum(i.run.subtype == "error_max_turns" for i in rs)
        if turns:
            L.append(f"| {t} | {rs[0].diff} | {len(rs)} | {min(turns)} | {_fmt(statistics.median(turns))} | {max(turns)} | {mt} |")
        else:
            L.append(f"| {t} | {rs[0].diff} | {len(rs)} | - | - | - | {mt} |")
    all_turns = sorted(i.run.num_turns for i in items if i.run.num_turns is not None)
    mt_all = sum(i.run.subtype == "error_max_turns" for i in items)
    L.append("")
    if all_turns:
        p90 = all_turns[math.ceil(0.9 * len(all_turns)) - 1]
        L.append(f"- 전체({len(all_turns)}건): 중앙값 {_fmt(statistics.median(all_turns))}, 90번째 백분위 {p90}, 최대 {all_turns[-1]}, error_max_turns {mt_all}건")
    else:
        L.append(f"- 전체(0건): n/a, error_max_turns {mt_all}건")
    L.append("- 90번째 백분위는 가장 가까운 순위 방식(오름차순 ceil(0.9 x 건수)번째). error_max_turns는 설정값+1로 보고된다(예: max_turns 20이면 21).")
    return L


def section_c(items: list[Item]) -> list[str]:
    g = _graded(items)
    tasks = sorted({i.task for i in g})
    split = _split_tasks(items)
    any_fail = sorted({i.task for i in g if not i.run.passed})
    all_fail = sorted(t for t in tasks if all(not i.run.passed for i in g if i.task == t))
    L = []
    if split:
        L += [f"- 성패가 갈린 과제: {len(split)}개/{len(tasks)}개", "",
              "| 과제 | 난이도 | run별 결과 | run별 턴 수 |", "|---|---|---|---|"]
        for t, rs in sorted(split.items()):
            res = " / ".join(f"run{i.n} {i.outcome}" for i in rs)
            turns = " / ".join("-" if i.run.num_turns is None else str(i.run.num_turns) for i in rs)
            L.append(f"| {t} | {rs[0].diff} | {res} | {turns} |")
    else:
        L.append(f"성패가 갈린 과제 없음({len(tasks)}개 과제 모두 반복 간 결과가 같음)")
    L.append("")
    L.append(f"- 한 번이라도 실패한 과제: {len(any_fail)}개/{len(tasks)}개" + (f" ({', '.join(any_fail)})" if any_fail else ""))
    L.append(f"- 모든 반복에서 실패한 과제: {len(all_fail)}개" + (f" ({', '.join(all_fail)})" if all_fail else ""))
    return L


def _count(run: report.Run, kind: str, short: str) -> int:
    n = 0
    for name, c in run.tool_counts.items():
        if classify_tool(name) != kind:
            continue
        if (kind == "custom" and name.split("__", 2)[-1] == short) or (kind == "builtin" and name == short):
            n += c
    return n


def section_d(items: list[Item], tasks: dict[str, loader.Task]) -> list[str]:
    pair = sorted((i for i in items if SEARCH_PAIR in getattr(tasks.get(i.task), "overlap_with", [])), key=lambda i: (i.task, i.n))
    if not pair:
        return ["쌍 과제 실행 없음"]
    L = ["| 과제 | run | search_text | Grep |", "|---|---|---|---|"]
    both = c_only = b_only = neither = used_c = used_b = 0
    for t in sorted({i.task for i in pair}):
        rs = [i for i in pair if i.task == t]
        sc = sg = 0
        for i in rs:
            c, g = _count(i.run, "custom", "search_text"), _count(i.run, "builtin", "Grep")
            sc, sg = sc + c, sg + g
            L.append(f"| {t} | run{i.n} | {c} | {g} |")
            used_c, used_b = used_c + (c > 0), used_b + (g > 0)
            both += c > 0 and g > 0
            c_only += c > 0 and g == 0
            b_only += g > 0 and c == 0
            neither += c == 0 and g == 0
        L.append(f"| {t} | 합계 | {sc} | {sg} |")
    per = _per_task(pair)
    L += ["", f"- {report.rate_line('search_text 선택률', used_c, per)} (search_text를 한 번이라도 쓴 실행 / 쌍 과제 실행)",
          f"- {report.rate_line('Grep 사용률', used_b, per)} (Grep을 한 번이라도 쓴 실행 / 쌍 과제 실행)",
          f"- search_text만 {c_only}, Grep만 {b_only}, 둘 다 {both}, 둘 다 안 씀 {neither}"]
    if len(pair) < report.MIN_SAMPLE:
        L.append(f"※ {report.SMALL_SAMPLE_WARNING} (쌍 과제 실행 {len(pair)}건 < {report.MIN_SAMPLE}건)")
    return L


def section_e(items: list[Item]) -> list[str]:
    L = ["| 실행 | 도구 호출 수 | 모델 응답 수 | 보고된 num_turns | num_turns - 호출 수 | num_turns - 응답 수 "
         "| 한 메시지 안 tool_use 2개 이상인 메시지 수 | 한 응답(message_id) 안 tool_use 2개 이상인 응답 수 |",
         "|---|---|---|---|---|---|---|---|"]
    rows = sorted(items, key=lambda i: (i.task, i.n))
    for i in rows:
        nt = i.run.num_turns
        L.append(f"| {i.label} | {i.run.tool_calls} | {i.responses} | {'-' if nt is None else nt} | "
                 f"{'-' if nt is None else nt - i.run.tool_calls} | {'-' if nt is None else nt - i.responses} | {i.msg_multi} | {i.id_multi} |")
    k = [i for i in rows if i.run.num_turns is not None]
    eq_calls = sum(i.run.num_turns == i.run.tool_calls + 1 for i in k)
    eq_resp1 = sum(i.run.num_turns == i.responses + 1 for i in k)
    eq_resp = sum(i.run.num_turns == i.responses for i in k)
    L += ["", f"- num_turns = 도구 호출 수 + 1: {eq_calls}/{len(k)}건",
          f"- num_turns = 모델 응답 수 + 1: {eq_resp1}/{len(k)}건",
          f"- num_turns = 모델 응답 수: {eq_resp}/{len(k)}건",
          f"- 한 메시지 안에 tool_use 2개 이상: {sum(i.msg_multi > 0 for i in rows)}/{len(rows)}건 실행(메시지 {sum(i.msg_multi for i in rows)}개)",
          f"- 한 응답(message_id) 안에 tool_use 2개 이상: {sum(i.id_multi > 0 for i in rows)}/{len(rows)}건 실행"
          f"(응답 {sum(i.id_multi for i in rows)}개, 한 응답 최대 tool_use {max((i.max_in_id for i in rows), default=0)}개)",
          "- 모델 응답 수 = assistant 메시지의 고유 message_id 개수(도구 없는 마지막 응답과 생각만 있는 응답 포함)."]
    no_id = sum(i.no_id for i in rows)
    if no_id:
        L.append(f"- message_id가 없는 assistant 메시지 {no_id}개는 응답 수에 넣지 않았다.")
    mt = sum(i.run.subtype == "error_max_turns" for i in rows)
    if mt:
        L.append(f"- error_max_turns {mt}건은 num_turns가 설정값+1로 보고되어 위 관계가 다를 수 있다.")
    return L


def build_baseline_report(paths, tasks: dict[str, loader.Task] | None = None) -> str:
    tasks = tasks or {t.id: t for t in loader.load_all() if not t.is_todo}
    files = sorted(p for p in (Path(x) for x in paths) if p.is_file() and RUN_RE.search(p.name))
    if not files:
        return "# 베이스라인 보고 (baseline_report)\n\n읽을 로그가 없다(..._run{n}.jsonl 파일이 없음).\n"
    items = [load_item(p) for p in files]
    per = _per_task(items)
    lo, hi = min(per.values()), max(per.values())
    m = f"{lo}회" if lo == hi else f"{lo}~{hi}회"
    out = ["# 베이스라인 보고 (baseline_report)", "", f"- 입력: 실행 {len(items)}건(과제 {len(per)}개, 과제당 {m}). .partial 보관본과 _final 스냅샷은 읽지 않는다.", ""]
    bodies = [section_a(items), section_b(items), section_c(items), section_d(items, tasks), section_e(items)]
    for title, body in zip(SECTION_TITLES, bodies):
        out += [f"## {title}", ""] + body + [""]
    overlap = {t: tasks[t].overlap_with for t in per if t in tasks}
    min_steps = {t.id: t.min_steps for t in tasks.values()}
    out += [f"## {SECTION_TITLES[5]}", "", report.build_report([i.run for i in items], overlap, min_steps), ""]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="베이스라인 보고서(읽기 전용, 모델 호출 없음)")
    ap.add_argument("paths", nargs="+", help="jsonl 경로 또는 글롭(예: results/raw/baseline_haiku_default_*_run*.jsonl)")
    a = ap.parse_args(argv)
    files = sorted({f for p in a.paths for f in glob.glob(p)})
    text = build_baseline_report(files)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(text)
    return 0 if files else 1


if __name__ == "__main__":
    sys.exit(main())
