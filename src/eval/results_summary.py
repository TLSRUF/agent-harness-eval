"""실험 A~F 결과 정리 문서(docs/results.md)를 results/raw 로그에서 만든다. 읽기 전용(모델 호출 없음), 동결 대상 아님.

사용: python -m src.eval.results_summary [--raw-dir results/raw] [--out docs/results.md]

- 표의 수치는 전부 로그에서 계산한다(exp_compare의 계산을 그대로 쓴다). 손으로 옮기지 않는다.
- 관찰(로그에서 읽은 값)과 가설(해석)을 문장 앞 "관찰:" / "가설:"로 구분한다.
- 사용자 이름이나 개인 경로는 출력하지 않는다(로그의 작업 폴더 경로는 읽지도 않는다).
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path

from . import exp_compare as ec
from . import loader, report

EXPS = ["A", "B", "C", "D", "E", "F"]
SMALL = f"{report.SMALL_SAMPLE_WARNING}(30건 미만)"
F_NAMES = {"long": "expFctl", "long_countline": "expF"}
H01_PREFIXES = {"default": "baseline_haiku_default", "long": "expA_haiku_long", "long_filename": "expE_haiku_longFilename",
                "expEctl": "expEctl_haiku_long"}
H01_NOTES = {"default": "baseline(도구 설명 기본값)", "long": "expA(도구 설명 long)", "long_filename": "expE(long + file_stats 출력에 파일 이름)",
             "expEctl": "expE와 같은 시기의 대조(long, 변형 없음)"}
H01_LABELS = ["default", "long", "long_filename", "expEctl"]

# ---------------- 로그 읽기(도구 호출과 결과) ----------------


def _result_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(b.get("text", "")) for b in content if isinstance(b, dict))
    return ""


def calls_with_results(path) -> list[tuple[str, dict, str]]:
    """도구 호출 순서대로 (이름, 입력, 결과 텍스트). 결과가 없으면 빈 문자열."""
    order: list[str] = []
    info: dict[str, list] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        ev = json.loads(line)
        if ev.get("kind") != "message":
            continue
        m = ev["message"]
        if m.get("_type") == "AssistantMessage":
            for b in m.get("content", []):
                if isinstance(b, dict) and b.get("_type") == "ToolUseBlock":
                    info[b["id"]] = [b["name"], b.get("input") or {}, ""]
                    order.append(b["id"])
        elif m.get("_type") == "UserMessage" and isinstance(m.get("content"), list):
            for b in m["content"]:
                if isinstance(b, dict) and b.get("_type") == "ToolResultBlock" and b.get("tool_use_id") in info:
                    info[b["tool_use_id"]][2] = _result_text(b.get("content"))
    return [tuple(info[i]) for i in order]


def _short(name: str) -> str:
    return name.split("__")[-1]


def parse_search_text(text: str) -> tuple[int, int | None]:
    """(돌려준 일치 줄 수, total matches 값 또는 None). 'no matches'와 잘림 안내(truncated)는 줄로 세지 않는다."""
    total = None
    lines = text.splitlines()
    if lines and lines[0].startswith("total matches:"):
        total = int(lines[0].split(":", 1)[1].strip())
        lines = lines[1:]
    return sum(1 for ln in lines if re.match(r"^[^:\n]+:\d+:", ln)), total


def _expected(task) -> int | None:
    try:
        return int(task.grading["params"]["value_tokens"][0])
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def _basename(p: str) -> str:
    return re.split(r"[\\/]", p)[-1]


def _last_write(calls, outputs, name_ok=lambda n: n == "Write"):
    got = None
    for name, inp, _ in calls:
        if name_ok(name) and _basename(str(inp.get("file_path", ""))) in outputs:
            got = str(inp.get("content", ""))
    return got


def agent_value(calls, task) -> int | None:
    """에이전트가 출력 파일에 마지막으로 쓴 내용의 마지막 정수."""
    content = _last_write(calls, set(task.outputs))
    nums = re.findall(r"-?\d+", content or "")
    return int(nums[-1]) if nums else None


def _counts_in(name: str, inp: dict, text: str) -> set[int]:
    """도구 결과가 알려준 '일치 줄 수'로 읽을 수 있는 값들."""
    if name.endswith("search_text"):
        n, total = parse_search_text(text)
        return {n} | ({total} if total is not None else set())
    if name == "Grep":
        if inp.get("output_mode") == "count":
            out = {int(x) for x in re.findall(r"Found (\d+) total", text)}
            out |= {int(x) for x in re.findall(r"^[^:\n]+:(\d+)$", text, re.M)}
            return out
        if inp.get("output_mode") == "content":
            return {sum(1 for ln in text.splitlines() if ln.strip())}
    return set()


# ---------------- 실험 F 메커니즘 ----------------

def mechanism_rows(cols, tasks) -> list[dict]:
    """search_text를 쓴 실행만: 돌려준 일치 줄 수, total matches, 에이전트 숫자, 기대 정답, 통과, Grep count 모드 사용."""
    rows = []
    for c in ec.COLUMNS_F:
        for r in sorted(cols.get(c, []), key=lambda x: (x.task, x.n)):
            calls = calls_with_results(r.run.path)
            st = [x for x in calls if x[0].endswith("search_text")]
            if not st:
                continue
            lines, total = parse_search_text(st[0][2])
            rows.append({"condition": c, "task": r.task, "run": r.n, "search_lines": lines, "total_matches": total,
                         "agent_value": agent_value(calls, tasks[r.task]), "expected": _expected(tasks[r.task]),
                         "passed": r.run.passed, "grep_count_mode": ec._used_grep_count_mode(r)})
    return rows


def failure_rows(cols, tasks) -> list[dict]:
    rows = []
    for c in ec.COLUMNS_F:
        for r in sorted(cols.get(c, []), key=lambda x: (x.task, x.n)):
            if r.run.passed is not False:
                continue
            calls = calls_with_results(r.run.path)
            val, exp = agent_value(calls, tasks[r.task]), _expected(tasks[r.task])
            gave = any(exp in _counts_in(n, i, t) for n, i, t in calls if n != "Write") if exp is not None else False
            if gave and val != exp:
                cause = f"에이전트 실수(도구 출력에 정답 {exp}이 있었으나 {val}로 셈)"
            else:
                cause = "확인 불가(도구 출력에서 정답 개수를 찾지 못함)"
            if not any(n.endswith("search_text") for n, _, _ in calls):
                cause += "; 이 실행은 search_text를 쓰지 않아 변형이 닿지 않았다"
            rows.append({"condition": c, "task": r.task, "run": r.n, "order": [_short(n) for n, _, _ in calls], "agent_value": val,
                         "expected": exp, "diff": None if val is None or exp is None else val - exp, "cause": cause})
    return rows


def reach(cols) -> dict[str, tuple[int, int]]:
    """조건별 (search_text를 쓴 실행 수, 전체 실행 수). 변형(개입)은 search_text 출력에만 닿는다."""
    return {c: (sum(1 for r in cols.get(c, []) if r.run.used_custom({"search_text"})), len(cols.get(c, []))) for c in ec.COLUMNS_F}


def render_mechanism(rows) -> list[str]:
    if not rows:
        return ["로그 없음(search_text를 쓴 실행이 없다)"]
    L = ["| 조건 | 과제/run | search_text가 돌려준 일치 줄 수 | total matches 값 | 에이전트 최종 숫자 | 기대 정답 | 통과 | Grep count 모드 |", "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {F_NAMES[r['condition']]} | {r['task']}/run{r['run']} | {r['search_lines']} | "
                 f"{'-' if r['total_matches'] is None else r['total_matches']} | {'n/a' if r['agent_value'] is None else r['agent_value']} | "
                 f"{'n/a' if r['expected'] is None else r['expected']} | {'통과' if r['passed'] else '실패'} | {'사용' if r['grep_count_mode'] else '미사용'} |")
    return L


def render_failures(rows) -> list[str]:
    if not rows:
        return ["실패 없음(0건)"]
    L = ["| 조건 | 과제/run | 도구 호출 순서(이름만) | 에이전트 출력 vs 정답(차이) | 원인 분류 |", "|---|---|---|---|---|"]
    for r in rows:
        diff = "n/a" if r["diff"] is None else f"{r['diff']:+d}"
        L.append(f"| {F_NAMES[r['condition']]} | {r['task']}/run{r['run']} | {' → '.join(r['order'])} | {r['agent_value']} vs {r['expected']} ({diff}) | {r['cause']} |")
    return L


# ---------------- H01 네 조건 ----------------

def _items(content: str) -> list[str]:
    return [ln.strip() for ln in (content or "").splitlines() if ln.strip()]


def _pair_error(got: list[str], expected: list[str]) -> bool:
    """빠진 항목과 값(숫자)은 같고 파일 이름만 다른 항목이 있는가(예: app_07 값 2675가 app_08에 붙음)."""
    def split(x):
        n, _, v = x.rpartition(":")
        return n.strip(), v.strip()
    miss = [split(x) for x in expected if x not in got]
    extra = [split(x) for x in got if x not in expected]
    return any(mv == ev and mn != en for mn, mv in miss for en, ev in extra)


def h01_rows(raw_dir, tasks) -> list[dict]:
    cols = ec.collect(raw_dir, H01_PREFIXES)
    task = tasks.get("H01")
    expected = list(task.grading["params"]["expected_items"]) if task else []
    res = []
    for c in H01_LABELS:
        recs = [r for r in cols[c] if r.task == "H01" and r.run.passed is not None]
        fails = [r for r in recs if not r.run.passed]
        pairs, outs = 0, set()
        for r in fails:
            got = _items(_last_write(calls_with_results(r.run.path), {"top_words.out"}))
            outs.add(tuple(got))
            pairs += _pair_error(got, expected)
        res.append({"condition": c, "passed": len(recs) - len(fails), "n": len(recs), "failures": len(fails), "pair_errors": pairs,
                    "distinct_failure_outputs": len(outs)})
    return res


def render_h01(rows) -> list[str]:
    L = ["| 조건 | 통과 | 실패 중 짝 오류(이름-값 어긋남) | 실패 출력 종류 | 설명 | 표본 |", "|---|---|---|---|---|---|"]
    for r in rows:
        n = r["n"]
        L.append(f"| {r['condition']} | {'n/a' if n == 0 else str(r['passed']) + '/' + str(n)} | "
                 f"{'n/a' if n == 0 else str(r['pair_errors']) + '/' + str(r['failures'])} | {'n/a' if n == 0 else r['distinct_failure_outputs']} | "
                 f"{H01_NOTES[r['condition']]} | N=1, 과제당 {n}회 / 총 {n}건 ({SMALL}) |")
    return L


# ---------------- 실험 D 과제별 비용 비율 ----------------

def cost_ratio_rows(cols) -> list[dict]:
    common = {(r.task, r.n) for r in cols.get("haiku", [])} & {(r.task, r.n) for r in cols.get("sonnet", [])}
    out = []
    for t in sorted({t for t, _ in common}):
        h = [r.run.cost for r in cols["haiku"] if (r.task, r.n) in common and r.task == t and r.run.cost is not None]
        s = [r.run.cost for r in cols["sonnet"] if (r.task, r.n) in common and r.task == t and r.run.cost is not None]
        if h and s and statistics.mean(h) > 0:
            out.append({"task": t, "haiku": statistics.mean(h), "sonnet": statistics.mean(s), "ratio": statistics.mean(s) / statistics.mean(h), "n": len(h)})
    return out


def render_cost_ratio(rows) -> list[str]:
    if not rows:
        return ["로그 없음(haiku와 sonnet에 공통인 (과제, run) 쌍이 없다)"]
    L = ["| 과제 | haiku 평균 비용 | sonnet 평균 비용 | 비율(sonnet/haiku) | 표본 |", "|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['task']} | ${r['haiku']:.4f} | ${r['sonnet']:.4f} | {r['ratio']:.1f} | N=1, 과제당 {r['n']}회 / 총 {r['n']}건 ({SMALL}) |")
    ratios = [r["ratio"] for r in rows]
    tot = sum(r["sonnet"] for r in rows) / sum(r["haiku"] for r in rows)
    L += ["", f"- 과제별 비율: 중앙값 {statistics.median(ratios):.1f}, 최소 {min(ratios):.1f}, 최대 {max(ratios):.1f}. "
              f"전체 평균 비용 비율(sonnet 합 / haiku 합) {tot:.1f}. 과제 {len(rows)}개, 칸마다 표본이 작다({SMALL})."]
    return L


# ---------------- 절 구성 ----------------

def _pct(num, den):
    return "n/a" if not den else f"{100 * num / den:.0f}% ({num}/{den})"


def _pass(cols, c):
    g = [r for r in cols.get(c, []) if r.run.passed is not None]
    return _pct(sum(bool(r.run.passed) for r in g), len(g))


def _sel(cols, c, sels, name):
    num, den, _ = ec._rate(cols.get(c, []), sels[name])
    return _pct(num, den)


def _normal(cols, c):
    rs = cols.get(c, [])
    return _pct(sum(r.run.subtype != "error_max_turns" for r in rs), len(rs))


def _common_sub(cols, a, b, columns):
    common = {(r.task, r.n) for r in cols[a]} & {(r.task, r.n) for r in cols[b]}
    return {c: [r for r in cols[c] if (r.task, r.n) in common] for c in columns}, common


def _sample_lines(sub, columns, names=None) -> list[str]:
    return [f"- {(names or {}).get(c, c)}: {report.sample_label(ec._per_task(sub[c]))}" if sub[c] else f"- {(names or {}).get(c, c)}: 로그 없음" for c in columns]


def _table(sub, columns, rows, sels) -> list[str]:
    return ec._section1(sub, sels, ec._Out(), columns, rows)


ROWS_A = ["성공률", "error_max_turns 건수", "search_text 선택률", "Grep 사용률", "file_stats 선택률", "Read 사용률", "check_result 사용률",
          "평균 모델 응답 수", "평균 도구 호출 수", "실행당 평균 비용"]
ROWS_B2 = ["성공률", "check_result 사용률", "평균 모델 응답 수", "평균 도구 호출 수", "실행당 평균 비용", "일관성 (a) 도구 순서"]
ROWS_C2 = ["성공률", "정상 종료율", "error_max_turns 건수(비율)", "error_max_turns인데 채점 통과", "평균 모델 응답 수", "실행당 평균 비용"]
ROWS_D2 = ["성공률", "error_max_turns 건수", "평균 모델 응답 수", "평균 도구 호출 수", "실행당 평균 비용", "search_text 선택률", "Grep 사용률", "file_stats 선택률", "Read 사용률"]


def _section(title, question, setting, sample, table, obs, hyp, limits, extra=None) -> list[str]:
    L = [f"## 실험 {title}", "", "### 질문", "", question, "", "### 설정", ""] + setting + ["", "### 표본", ""] + sample + ["", "### 핵심 지표", ""] + table
    for heading, body in (extra or []):
        L += ["", f"**{heading}**", ""] + body
    L += ["", "### 해석", ""] + [f"- 관찰: {o}" for o in obs] + [f"- 가설: {h}" for h in hyp] + ["", "### 한계", ""] + [f"- {x}" for x in limits] + [""]
    return L


def _missing(title, question, setting, limits) -> list[str]:
    return _section(title, question, setting, ["로그 없음(results/raw에 이 실험의 로그가 없다)"], ["로그 없음"],
                    ["로그 없음"], ["로그 없음"], limits)


def _has_logs(cols, columns) -> bool:
    return any(cols[c] for c in columns[1:] if c in cols)


def section_a(raw_dir, tasks, sels):
    cols = ec.collect(raw_dir, ec.PREFIXES)
    title, q = "A — 도구 설명 버전", "도구 설명(default, short, long, long_directive)을 바꾸면 커스텀 도구(search_text, file_stats) 선택과 성공률이 달라지는가?"
    setting = ["도구 설명 버전만 바꾼다(프롬프트 v1, max_turns 20, haiku). default = 베이스라인, short = 짧은 설명, long = 사용 조건을 적은 긴 설명, "
               "long_directive = long + 우선 사용 지시 한 문장."]
    limits = ["과제당 3회뿐이라 반복 사이 우연 범위가 크다(search_text|Grep 쌍 과제 12개, file_stats|Read 쌍 과제 8개).",
              "베이스라인 성공률이 높아 성공률 차이를 볼 여지가 작다(천장 효과).", "선택률은 쌍 과제에서 커스텀 도구를 한 번이라도 호출한 실행의 비율이며 도구가 더 좋아졌다는 뜻이 아니다."]
    if not _has_logs(cols, ec.COLUMNS):
        return _missing(title, q, setting, limits)
    c = ec.COLUMNS
    obs = [f"성공률 " + ", ".join(f"{x} {_pass(cols, x)}" for x in c) + ".",
           "search_text 선택률(search_text|Grep 쌍 과제) " + ", ".join(f"{x} {_sel(cols, x, sels, 'search_text 선택률')}" for x in c) + ".",
           "file_stats 선택률(file_stats|Read 쌍 과제) " + ", ".join(f"{x} {_sel(cols, x, sels, 'file_stats 선택률')}" for x in c) + "."]
    hyp = ["도구 설명에 쓰임새와 반환 정보를 적으면 커스텀 도구 선택이 늘어난다(특히 file_stats). 반복 사이 우연 범위를 넘는지는 exp_compare --exp A의 3~4절로 판정한다.",
           "선택률이 오른 도구가 성공률을 올리는지는 이 데이터로 확인 불가(성공률이 이미 높다)."]
    return _section(title, q, setting, _sample_lines(cols, c), _table(cols, c, ROWS_A, sels), obs, hyp, limits)


def section_b(raw_dir, tasks, sels):
    cols = ec.collect(raw_dir, ec.PREFIXES_B)
    title, q = "B — 검증 지시", "시스템 프롬프트에 검증 지시(verify) 또는 check_result 사용 지시(verify_tool)를 넣으면 검증 행동과 성공률이 달라지는가?"
    setting = ["프롬프트 버전만 바꾼다(default = v1, verify = 끝나기 전 결과 확인 지시, verify_tool = check_result 사용을 명시; 도구 설명 default, max_turns 20, haiku)."]
    limits = ["check_result는 파일 존재, 포함 문자열, 최소 줄 수만 확인하며 값의 정확성은 확인하지 않는다. 사용률은 검증 행동의 증가이지 정확성의 증가가 아니다.",
              "과제당 3회, 베이스라인 성공률이 높아 성공률 차이를 보기 어렵다."]
    if not _has_logs(cols, ec.COLUMNS_B):
        return _missing(title, q, setting, limits)
    c = ec.COLUMNS_B
    obs = ["check_result 사용률 " + ", ".join(f"{x} {_sel(cols, x, sels, 'check_result 사용률')}" for x in c) + ".",
           "성공률 " + ", ".join(f"{x} {_pass(cols, x)}" for x in c) + "."]
    hyp = ["지시문이 검증 행동(check_result 호출)을 늘린다.", "늘어난 검증이 값 오류를 줄이는지는 확인 불가(check_result가 값을 검사하지 않고 성공률도 천장 근처)."]
    return _section(title, q, setting, _sample_lines(cols, c), _table(cols, c, ROWS_B2, sels), obs, hyp, limits)


def section_c(raw_dir, tasks, sels):
    cols = ec.collect(raw_dir, ec.PREFIXES_C)
    title, q = "C — 최대 턴 수", "max_turns를 3, 4, 5, 7로 줄이면 정상 종료율과 성공률은 어떻게 변하는가? (default = max_turns 20)"
    setting = ["max_turns만 바꾼다(도구 설명 default, 프롬프트 v1, haiku). 20은 베이스라인."]
    limits = ["error_max_turns로 끝났지만 파일 결과가 채점을 통과한 실행이 있어 성공률과 정상 종료율은 다른 지표다.",
              "한계 규칙(응답 수가 max_turns를 넘으려 할 때 중단)은 max_turns 3, 4, 5에서만 확인했고 7과 20은 확인 불가(한계에 걸린 실행이 없다).", "과제당 3회."]
    if not _has_logs(cols, ec.COLUMNS_C):
        return _missing(title, q, setting, limits)
    c = ec.COLUMNS_C
    obs = ["정상 종료율(error_max_turns가 아닌 실행) " + ", ".join(f"max_turns {x} {_normal(cols, x)}" for x in c) + ".",
           "성공률 " + ", ".join(f"max_turns {x} {_pass(cols, x)}" for x in c) + "."]
    hyp = ["작은 max_turns에서 성공률이 정상 종료율보다 훨씬 높은 것은 에이전트가 한계에 걸리기 전에 이미 결과 파일을 써 두기 때문이다(채점 통과 건수 행 참고).",
           "한계 판정 규칙은 응답 수 > max_turns일 때 중단(max_turns 3, 4, 5에서 일치, 가설 수준)."]
    return _section(title, q, setting, _sample_lines(cols, c), _table(cols, c, ROWS_C2, sels), obs, hyp, limits)


def section_d(raw_dir, tasks, sels):
    cols = ec.collect(raw_dir, ec.PREFIXES_D)
    title, q = "D — 모델 비교", "같은 하네스 설정에서 sonnet은 haiku보다 성공률과 비용이 얼마나 다른가?"
    setting = ["모델만 바꾼다(haiku = 베이스라인 claude-haiku-5-5, sonnet = claude-sonnet-5-5; 도구 설명 default, 프롬프트 v1, max_turns 20). 같은 (과제, run) 쌍만 비교한다."]
    limits = ["과제당 1회(같은 쌍)라 반복 사이 변동을 알 수 없다.", "두 모델 모두 성공률이 천장이라 정확도 차이는 이 평가셋으로 가릴 수 없다.", "비용은 정가 환산 추정치이며 구독 한도 소모와 별개다."]
    if not _has_logs(cols, ec.COLUMNS_D):
        return _missing(title, q, setting, limits)
    c = ec.COLUMNS_D
    sub, _ = _common_sub(cols, "haiku", "sonnet", c)
    ratio = cost_ratio_rows(cols)
    tot = sum(r["sonnet"] for r in ratio) / sum(r["haiku"] for r in ratio) if ratio else None
    obs = ["성공률 " + ", ".join(f"{x} {_pass(sub, x)}" for x in c) + ".",
           f"전체 평균 비용 비율(sonnet 합 / haiku 합) {tot:.1f}배(과제 {len(ratio)}개)." if tot else "비용 비율: 로그 없음."]
    hyp = ["성공률이 같으므로 이 평가셋에서는 sonnet의 비용 증가에 대응하는 정확도 이득이 보이지 않는다(천장 효과 때문에 더 어려운 평가셋에서의 차이는 확인 불가)."]
    return _section(title, q, setting, _sample_lines(sub, c), _table(sub, c, ROWS_D2, sels), obs, hyp, limits,
                    extra=[("과제별 비용 비율(sonnet/haiku)", render_cost_ratio(ratio))])


def section_e(raw_dir, tasks, sels):
    cols = ec.collect(raw_dir, ec.PREFIXES_E)
    title, q = "E — file_stats 출력에 파일 이름", "file_stats 출력 앞에 `path: <입력 경로>` 한 줄을 붙이면 file_stats|Read 쌍 과제의 오류(특히 H01 짝 오류)가 줄어드는가?"
    setting = ["도구 출력만 바꾼다(`--tool-output-variant filename`: file_stats 출력 앞에 입력 경로 한 줄; 도구 이름, 스키마, 설명은 그대로). 도구 설명 long, 프롬프트 v1, max_turns 20, haiku."]
    limits = ["비교 기준(expA long)과 변형(expE)은 서로 다른 시기에 실행됐고, H01만 같은 시기 대조(expEctl 3회)가 있다.", "과제 8개 x 3회로 30건 미만이다.",
              "H01 실패 원인(이름-값 짝 어긋남)은 실패 출력으로 추정한 것이며 모델 내부 과정은 확인 불가."]
    if not _has_logs(cols, ec.COLUMNS_E):
        return _missing(title, q, setting, limits)
    c = ec.COLUMNS_E
    sub, _ = _common_sub(cols, "long", "long_filename", c)
    h01 = h01_rows(raw_dir, tasks)
    hm = {r["condition"]: r for r in h01}
    obs = ["성공률 " + ", ".join(f"{x} {_pass(sub, x)}" for x in c) + ".",
           "H01 통과: " + ", ".join(f"{k} {hm[k]['passed']}/{hm[k]['n']}" for k in H01_LABELS if hm[k]["n"]) + ". 실패한 실행은 모두 이름-값 짝 오류 유형이다."
           if all(hm[k]["pair_errors"] == hm[k]["failures"] for k in H01_LABELS) else
           "H01 통과: " + ", ".join(f"{k} {hm[k]['passed']}/{hm[k]['n']}" for k in H01_LABELS if hm[k]["n"]) + "."]
    hyp = ["H01의 실패는 file_stats 출력에 파일 이름이 없어 Glob 결과의 순서와 통계를 짝지을 때 한 칸 어긋난 것이다(실패 출력이 모두 같은 어긋남이라는 점에서 나온 가설).",
           "파일 이름 출력이 이를 줄이는지는 미확정: 같은 시기 대조(expEctl)에서도 H01이 일부 통과했다."]
    return _section(title, q, setting, _sample_lines(sub, c), _table(sub, c, ec.ROWS_E, sels), obs, hyp, limits,
                    extra=[("H01 네 조건 비교", render_h01(h01))])


def section_f(raw_dir, tasks, sels):
    cols = ec.collect(raw_dir, ec.PREFIXES_F)
    title, q = "F — search_text 출력에 전체 일치 줄 수", "search_text 출력 맨 앞에 `total matches: <전체 일치 줄 수>`를 붙이면 세기 과제의 오류가 줄고 Grep count 모드 사용이 바뀌는가?"
    setting = ["도구 출력만 바꾼다(`--tool-output-variant countline`: search_text 출력 앞에 MAX_RESULTS 50으로 자르기 전의 일치 줄 수 한 줄; 도구 이름, 스키마, 설명은 그대로). "
               "대조(expFctl)는 변형 없는 long. 도구 설명 long, 프롬프트 v1, max_turns 20, haiku. 대상 과제 E01, M01, M05, M07(search_text|Grep 쌍)."]
    limits = ["변형은 search_text를 호출한 실행에만 닿는다. 두 조건 모두 search_text를 쓴 실행이 소수라 개입이 닿은 표본이 매우 작다.",
              "두 조건은 같은 시기에 연달아 실행했지만 시기 효과가 없다고 확인된 것은 아니다(확인 불가).", "총 20건 x 2 조건, 과제당 5회(30건 미만)."]
    if not _has_logs(cols, ec.COLUMNS_F):
        return _missing(title, q, setting, limits)
    c = ec.COLUMNS_F
    sub, common = _common_sub(cols, "long", "long_countline", c)
    rc = reach(sub)
    (k0, n0), (k1, n1) = rc["long"], rc["long_countline"]
    reach_txt = f"개입이 닿은 실행이 조건당 {k1}/{n1}" if (k0, n0) == (k1, n1) else f"개입이 닿은 실행: expFctl {k0}/{n0}, expF {k1}/{n1}"
    mech, fails = mechanism_rows(sub, tasks), failure_rows(sub, tasks)
    obs = ["성공률 " + ", ".join(f"{F_NAMES[x]} {_pass(sub, x)}" for x in c) + f"(같은 (과제, run) 쌍 {len(common)}건).",
           f"{reach_txt}(search_text를 호출한 실행; 변형은 이 실행의 search_text 출력에만 닿는다).",
           "Grep count 모드 사용률 " + ", ".join(f"{F_NAMES[x]} {_sel(sub, x, sels, 'Grep count 모드 사용률')}" for x in c) + ".",
           f"실패 {len(fails)}건 중 {sum(f['cause'].startswith('에이전트 실수') for f in fails)}건은 도구 출력에 정답 개수가 있었는데 에이전트가 다르게 셌다."]
    hyp = ["효과를 확인하지 못함: 개입이 닿은 실행이 조건당 소수이고 성공률 차이가 1건 수준이라 우연 범위 안이다.",
           "실패는 도구 출력의 문제가 아니라 에이전트가 줄을 직접 세다가 틀린 것으로 보인다(Grep content 출력 줄 수를 직접 센 경우 포함). total matches가 이를 막는지는 개입이 닿은 표본이 작아 확인 불가."]
    return _section(title, q, setting, _sample_lines(sub, c, F_NAMES), _table(sub, c, ec.ROWS_F, sels), obs, hyp, limits,
                    extra=[(f"메커니즘: search_text를 쓴 실행만({len(mech)}건)", render_mechanism(mech)),
                           (f"실패 {len(fails)}건", render_failures(fails))])


SECTIONS = {"A": section_a, "B": section_b, "C": section_c, "D": section_d, "E": section_e, "F": section_f}
TOC_TEXT = {"A": "도구 설명 버전", "B": "검증 지시", "C": "최대 턴 수", "D": "모델 비교", "E": "file_stats 출력에 파일 이름", "F": "search_text 출력에 전체 일치 줄 수"}


def build(raw_dir, tasks=None) -> str:
    tasks = tasks or {t.id: t for t in loader.load_all() if not t.is_todo}
    sels = ec._selections(tasks)
    head = ["# 실험 결과 정리 (A~F)", "",
            "이 문서는 `python -m src.eval.results_summary`가 results/raw 로그에서 만든다(읽기 전용, 모델 호출 없음). 수치를 손으로 고치지 않는다. "
            "모든 비율에 표본 크기(N, 과제당 M회, 총 건수)를 붙였고 30건 미만이면 경고를 표시한다. 해석 절의 \"관찰:\"은 로그에서 읽은 값, \"가설:\"은 해석이다.",
            "", "## 목차", ""]
    head += [f"- 실험 {e} — {TOC_TEXT[e]}" for e in EXPS] + [""]
    body: list[str] = []
    for e in EXPS:
        body += SECTIONS[e](raw_dir, tasks, sels)
    return "\n".join(head + body).rstrip() + "\n"


def _any_logs(raw_dir) -> bool:
    for pre in (ec.PREFIXES, ec.PREFIXES_B, ec.PREFIXES_C, ec.PREFIXES_D, ec.PREFIXES_E, ec.PREFIXES_F):
        if any(ec.collect(raw_dir, pre)[c] for c in list(pre)):
            return True
    return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="실험 A~F 결과 정리 문서 생성(읽기 전용, 모델 호출 없음)")
    ap.add_argument("--raw-dir", default="results/raw")
    ap.add_argument("--out", default="docs/results.md")
    a = ap.parse_args(argv)
    if not _any_logs(a.raw_dir):
        print("읽을 로그가 없다", file=sys.stderr)
        return 1
    text = build(a.raw_dir)
    Path(a.out).write_text(text, encoding="utf-8")
    print(f"{a.out} 생성({len(text.splitlines())}줄)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
