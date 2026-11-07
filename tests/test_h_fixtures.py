"""H01~H08 fixture 검증. 생성기와 코드를 공유하지 않고 함정, 크기, 정답을 독립적으로 다시 검사한다."""
import importlib.util
import json
import re
from collections import Counter
from pathlib import Path

import pytest

from src.eval import loader, verify_counts

FIX = loader.FIXTURES_DIR
PLANTS = loader.PLANTS_DIR
H_IDS = [f"H0{i}" for i in range(1, 9)]

spec = importlib.util.spec_from_file_location("gen_fixtures_for_h_test", FIX / "_gen" / "gen_fixtures.py")
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

EXOTIC = re.compile("[\r\u2028\u2029\u0085\x0b\x0c\x1c\x1d\x1e]")


def files(tid):
    return sorted((FIX / tid).iterdir())


def text(tid, name):
    return (FIX / tid / name).read_bytes().decode("utf-8")


def lines(tid, name):
    return text(tid, name).split("\n")[:-1]


def plant(tid):
    return json.loads((PLANTS / f"{tid}.json").read_text(encoding="utf-8"))


# ---------------- 재생성 동일성, 크기, 깨끗한 텍스트 ----------------

def test_regeneration_is_byte_identical_for_hard_tasks(tmp_path):
    gen.generate_all(tmp_path / "fx", tmp_path / "pl")
    for tid in H_IDS:
        assert {p.name: p.read_bytes() for p in (tmp_path / "fx" / tid).iterdir()} == {p.name: p.read_bytes() for p in files(tid)}, tid
        assert (tmp_path / "pl" / f"{tid}.json").read_bytes() == (PLANTS / f"{tid}.json").read_bytes(), tid


@pytest.mark.parametrize("tid,n_files", [("H01", 10), ("H02", 12), ("H03", 6), ("H04", 10), ("H05", 10), ("H06", 2), ("H07", 8), ("H08", 10)])
def test_file_counts(tid, n_files):
    assert len(files(tid)) == n_files


@pytest.mark.parametrize("tid", H_IDS)
def test_files_are_clean_text_without_special_line_separators(tid):
    for p in files(tid):
        data = p.read_bytes()
        t = data.decode("utf-8")                        # UTF-8
        assert b"\r" not in data and t.endswith("\n") and not EXOTIC.search(t), p
        for n, ln in enumerate(t.split("\n")[:-1], 1):
            assert ln != "" and ln == ln.strip() and "\t" not in ln, (p.name, n)   # 빈 줄 없음, 앞뒤 공백 없음


def test_no_long_line_overlap_with_easy_and_medium_fixtures():
    """의미 있는 줄(30자 이상)이 쉬움/보통 과제의 fixture와 겹치지 않는다."""
    ts = re.compile(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d ")
    other = set()
    for d in FIX.glob("[EM][0-9][0-9]"):
        for p in d.iterdir():
            if p.is_file():
                other |= {ts.sub("", ln) for ln in p.read_bytes().decode("utf-8").split("\n") if len(ln) >= 30}
    for tid in H_IDS:
        for p in files(tid):
            for ln in lines(tid, p.name):
                assert ts.sub("", ln) not in other or len(ln) < 30, (tid, p.name, ln)


# ---------------- H01: 큰 파일 통계 ----------------

def test_h01_top3_by_words_differs_from_top3_by_lines_and_has_clear_gaps():
    words = {p.name: len(p.read_bytes().decode("utf-8").split()) for p in files("H01")}
    nlines = {p.name: len(lines("H01", p.name)) for p in files("H01")}
    assert all(150 <= n <= 400 for n in nlines.values())                        # 큰 파일: 150~400줄
    assert len(set(words.values())) == 10                                       # 단어 수 동률 없음
    by_w = sorted(words, key=lambda n: -words[n])
    by_l = sorted(nlines, key=lambda n: -nlines[n])
    assert set(by_w[:3]) != set(by_l[:3])                                       # 줄 수 순위와 단어 수 순위가 다른 함정
    assert all(words[by_w[i]] - words[by_w[i + 1]] >= 25 for i in range(3))     # 1~4등 사이에 25단어 이상 간격
    assert plant("H01")["answer"]["items"] == [f"{n}: {words[n]}" for n in by_w[:3]]


# ---------------- H02 ----------------

def test_h02_boundary_files_and_sum():
    counts = {p.name: len(lines("H02", p.name)) for p in files("H02")}
    assert {99, 100, 101} <= set(counts.values())                               # 기준(100) -1, 기준, +1 경계 파일
    big = sorted(c for c in counts.values() if c >= 100)
    assert big == [100, 101, 112] and sum(big) == plant("H02")["answer"]["sum"] == 313


# ---------------- H03 ----------------

def test_h03_dates_ports_tie_rule():
    info = {}
    for p in files("H03"):
        t = text("H03", p.name)
        dates = re.findall(r"\d{4}-\d{2}-\d{2}", t)
        assert len(dates) == 1 and re.search(r"^Last updated: \d{4}-\d{2}-\d{2}$", t, re.M)   # 날짜 하나, 형식 YYYY-MM-DD
        assert not re.search(r"(?i)\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.? \d", t)   # 다른 날짜 형식 없음
        ports = re.findall(r"\d{4,5}", t.replace(dates[0], ""))
        assert len(ports) == 1
        info[p.name] = (dates[0], int(ports[0]))
    latest = max(d for d, _ in info.values())
    tied = sorted(n for n, (d, _) in info.items() if d == latest)
    assert tied == ["ops_guide.md", "runbook.md"]                               # 최신 날짜 동률 한 쌍
    assert info["ops_guide.md"][1] != info["runbook.md"][1]                     # 둘의 포트는 다르다
    assert len({port for _, port in info.values()}) >= 4                        # 문서마다 서로 다른 포트를 적은 충돌 상황
    assert plant("H03")["answer"] == {"port": info["ops_guide.md"][1]} == {"port": 8443}
    second = sorted({d for d, _ in info.values()})[-2]
    assert second < latest                                                      # 동률이 아닌 문서들은 모두 더 오래됨


# ---------------- H04 ----------------

def test_h04_claims_and_off_by_one_traps():
    wrong, minus1, plus1 = [], [], []
    for p in files("H04"):
        ls = lines("H04", p.name)
        m = re.fullmatch(r"# lines: (\d+)", ls[0])
        assert m and not any(ln.startswith("#") for ln in ls[1:])               # 헤더 줄 하나뿐
        claim, actual = int(m.group(1)), len(ls)                                # 실제 줄 수는 첫 줄 포함
        if claim != actual:
            wrong.append(p.name)
        if claim == actual - 1:
            minus1.append(p.name)                                               # 헤더를 빼고 센 값(오차 1 함정)
        if claim == actual + 1:
            plus1.append(p.name)
    assert wrong == plant("H04")["answer"]["items"] and len(wrong) == 3
    assert len(minus1) == 1 and len(plus1) == 1 and set(minus1 + plus1) <= set(wrong)   # 오차 1짜리 둘 다 정답 목록에 포함


# ---------------- H05 ----------------

def test_h05_exact_target_lines_and_all_decoy_kinds():
    old = "endpoint = http://old.internal:8080"
    decoys = ["# " + old, "backup_" + old, "endpoint = http://old.internal:8081", old + "/health",
              "endpoint = http://old.internal:80800", "endpoint = http://olds.internal:8080"]
    seen_decoys, changed = set(), {}
    for p in files("H05"):
        ls = lines("H05", p.name)
        exact = [i for i, ln in enumerate(ls, 1) if ln == old]
        assert len(exact) <= 1
        if exact:
            changed[p.name] = exact[0]
        seen_decoys |= {ln for ln in ls if ln in decoys}
        assert not any("new.internal" in ln for ln in ls)
    assert len(changed) == 6 and changed == plant("H05")["answer"]["changed"]
    assert seen_decoys == set(decoys)                                           # 디코이 6종이 모두 실제로 쓰였다
    task_expected = plant("H05")["planted"]["expected"]
    for p in files("H05"):
        orig = lines("H05", p.name)
        exp = task_expected[p.name].split("\n")[:-1]
        assert [i for i, (a, b) in enumerate(zip(orig, exp), 1) if a != b] == ([changed[p.name]] if p.name in changed else [])
        assert len(orig) == len(exp)


# ---------------- H06 ----------------

def test_h06_unknown_id_is_the_most_frequent_but_must_be_ignored():
    import csv
    def rows(name):
        with (FIX / "H06" / name).open(encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))
    cust = {r["id"]: r["name"] for r in rows("customers.csv")}
    orders = rows("orders.csv")
    freq = Counter(r["customer_id"] for r in orders)
    assert len(cust) == 40 and len(orders) == 60 and len(set(cust.values())) == 40
    unknown = {k: v for k, v in freq.items() if k not in cust}
    assert unknown == {"c099": 11}
    known = Counter({k: v for k, v in freq.items() if k in cust})
    (top_id, top_n), (_, second_n) = known.most_common(2)
    assert top_n == 8 and second_n == 6 and unknown["c099"] > top_n             # 함정: 전체 최다는 목록에 없는 id
    assert cust[top_id] == plant("H06")["answer"]["name"]
    names = [n.lower() for n in cust.values()]
    assert not any(a != b and a in b for a in names for b in names)             # 이름이 다른 이름의 일부가 아님


# ---------------- H07 ----------------

def test_h07_chain_trace_and_decoys():
    conf = {p.name: lines("H07", p.name) for p in files("H07")}
    assert len(conf) == 8
    # 이 테스트가 직접 구현한 인터프리터로 처리 순서를 따라간다
    trace = []
    def run(name, state):
        for ln in conf[name]:
            if ln.startswith("#"):
                continue
            key, _, val = [x.strip() for x in ln.partition("=")]
            if key == "include":
                run(val, state)
            else:
                state[key] = val
                if key == "timeout":
                    trace.append((name, int(val)))
    state = {}
    run("main.conf", state)
    assert int(state["timeout"]) == plant("H07")["answer"]["timeout"] == 35
    assert trace == [("main.conf", 10), ("site.conf", 50), ("base.conf", 20), ("net.conf", 30), ("deep.conf", 45),
                     ("tuning.conf", 40), ("net.conf", 35)]
    visited = {n for n, _ in trace} | {"tuning.conf"}
    outside = {"legacy.conf", "orphan.conf"}
    assert outside.isdisjoint(visited) and "# include = legacy.conf" in conf["main.conf"]
    outside_values = {int(conf[n][0].split("=")[1]) for n in outside}
    assert 35 not in outside_values and outside_values == {77, 99}              # 체인 밖 파일의 timeout은 정답과 다름
    # 흔한 오답은 모두 정답과 다르다: 첫 값, 가장 깊은 파일, 마지막으로 읽은 파일, 단순 합류
    assert {10, 45, 40, 50, 20, 30} .isdisjoint({35})


# ---------------- H08 ----------------

def test_h08_bytes_chars_and_tie():
    nbytes = {p.name: len(p.read_bytes()) for p in files("H08")}
    nchars = {p.name: len(p.read_bytes().decode("utf-8")) for p in files("H08")}
    top = max(nbytes.values())
    tied = sorted(n for n, b in nbytes.items() if b == top)
    assert len(tied) == 2 and top == 5016                                       # 바이트 최댓값 동률은 정확히 한 쌍
    assert sorted(nbytes.values())[-3] < top
    char_max = max(nchars, key=nchars.get)
    assert char_max not in tied and list(nchars.values()).count(nchars[char_max]) == 1   # 글자 수 최대 파일은 바이트 최대 파일이 아님
    assert nbytes[char_max] < top < 6000
    assert plant("H08")["answer"] == {"file": tied[0], "bytes": top} and tied[0] < tied[1]   # 알파벳 규칙으로 정답이 하나
    for p in files("H08"):                                                       # 모두 한글을 쓰는 파일인지(바이트 > 글자 수)
        if nbytes[p.name] != nchars[p.name]:
            assert nbytes[p.name] > nchars[p.name]


# ---------------- 생성기가 정한 값 = 독립 검색으로 센 값 ----------------

@pytest.mark.parametrize("tid", H_IDS)
def test_planted_answer_equals_independent_count(tid):
    assert plant(tid)["answer"] == verify_counts.COUNTERS[tid](FIX / tid)


def test_loader_check6_passes_for_all_h_answers_and_fails_when_changed():
    def fake(tid, answer):
        return loader.Task(id=tid, slug="x", rev=1, difficulty="hard", prompt="p", fixture=tid, outputs=[], grading={},
                           overlap_with=[], hand_check="h", raw={"answer": answer})
    for tid in H_IDS:
        assert loader.check_plant(fake(tid, plant(tid)["answer"])) == [], tid
    bad = loader.check_plant(fake("H02", {"sum": 312}))
    assert bad and "[6]" in bad[0]
