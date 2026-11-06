"""E13~E15: 사용자 채점기와 무관하게 fixture의 약속과 정답 풀이 출력을 검증한다.

기대값은 사람이 손으로 센 값을 여기에 직접 적었다 (정답 풀이 코드와 독립).
사용자 채점 함수가 작성되면 로더의 5가지 검증(test_tasks.py)이 따로 이 과제들을 통과시킨다.
"""
import csv
import re
import shutil
from pathlib import Path

from src.eval import loader

FIX = loader.FIXTURES_DIR

WARN_NUMBERS = [4, 9, 15, 22, 27, 33, 41, 47]
WARN_MESSAGES = [
    "queue depth at 80 percent of limit",
    "retry delay exceeds configured soft limit",
    "disk usage on /var/tmp reached 92%",
    "report-weekly input file is older than 7 days",
    "email gateway latency above 2000 ms",
    "archive volume is 85% full",
    "second archive attempt is slower than the first",
    "pending notifications exceed 10 entries",
]


def run_solution(tid, tmp_path) -> Path:
    t = next(x for x in loader.load_all() if x.id == tid)
    wd = tmp_path / tid
    shutil.copytree(t.fixture_dir, wd)
    loader.solution_module(tid).solve(wd)
    return wd


# ---------------- E13 ----------------

def test_e13_fixture_promises():
    lines = (FIX / "E13" / "app.log").read_text(encoding="utf-8").split("\n")
    assert lines[-1] == "" and len(lines) - 1 == 50
    lines = lines[:-1]
    warn_idx = [i for i, ln in enumerate(lines, 1) if "WARN" in ln]
    assert warn_idx == WARN_NUMBERS
    for i in WARN_NUMBERS:
        assert "[WARN] " in lines[i - 1]
    text = "\n".join(lines)
    assert "WARNING" not in text and "warn" not in text and text.count("WARN") == 8
    levels = [re.search(r"\[(\w+)\]", ln).group(1) for ln in lines]
    assert levels.count("WARN") == 8 and levels.count("INFO") == 25
    assert levels.count("DEBUG") == 12 and levels.count("ERROR") == 5
    assert len(set(lines)) == 50  # 모든 줄이 서로 달라 순서/누락 오류를 구분할 수 있다


def test_e13_solution_output_matches_hand_check(tmp_path):
    wd = run_solution("E13", tmp_path)
    got = (wd / "warn.txt").read_text(encoding="utf-8").splitlines()
    assert len(got) == 8
    for line, msg in zip(got, WARN_MESSAGES):
        assert line.endswith(f"[WARN] {msg}"), line
    src = (FIX / "E13" / "app.log").read_text(encoding="utf-8").splitlines()
    assert got == [src[i - 1] for i in WARN_NUMBERS]
    assert (wd / "app.log").read_bytes() == (FIX / "E13" / "app.log").read_bytes()  # 입력 보존


def test_e13_does_not_overlap_e01_content():
    e01 = (FIX / "E01" / "app.log").read_text(encoding="utf-8")
    e13 = (FIX / "E13" / "app.log").read_text(encoding="utf-8")
    msgs01 = {re.sub(r"^\S+ \S+ +\w+ +", "", ln) for ln in e01.splitlines()}
    msgs13 = {re.sub(r"^\S+ \S+ \[\w+\] ", "", ln) for ln in e13.splitlines()}
    assert not (msgs01 & msgs13)


# ---------------- E14 ----------------

def test_e14_fixture_promises():
    with (FIX / "E14" / "orders.csv").open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames
        rows = list(reader)
    assert header == ["order_id", "product", "price", "qty", "region"]
    qtys = [int(r["qty"]) for r in rows]
    assert qtys == [12, 8, 23, 31, 17, 50, 44, 29, 36, 9, 41, 25]
    assert qtys.count(max(qtys)) == 1 and qtys.index(50) == 5 and rows[5]["product"] == "scissors"
    top_price = max(rows, key=lambda r: int(r["price"]))
    assert top_price["product"] == "notebook" and top_price["product"] != rows[5]["product"]  # 함정
    assert (FIX / "E14" / "orders.csv").read_text(encoding="utf-8").count("\n") == 13


def test_e14_product_names_do_not_collide_with_e06():
    with (FIX / "E06" / "sales.csv").open(encoding="utf-8", newline="") as f:
        e06 = {r["item"] for r in csv.DictReader(f)}
    with (FIX / "E14" / "orders.csv").open(encoding="utf-8", newline="") as f:
        e14 = {r["product"] for r in csv.DictReader(f)}
    assert not (e06 & e14)  # 정확히 같은 이름은 없다 (부분 문자열: pen 포함 pencil, book 포함 notebook)


def test_e14_solution_output(tmp_path):
    wd = run_solution("E14", tmp_path)
    assert (wd / "top.txt").read_text(encoding="utf-8").strip() == "제품: scissors"


# ---------------- E15 ----------------

def test_e15_fixture_promises():
    m1 = (FIX / "E15" / "memo1.txt").read_text(encoding="utf-8").splitlines()
    m2 = (FIX / "E15" / "memo2.txt").read_text(encoding="utf-8").splitlines()
    assert len(m1) == 7 and len(m2) == 6

    def cat_lines(ls):
        return {i: ln.count("Cat") for i, ln in enumerate(ls, 1) if "Cat" in ln}

    assert cat_lines(m1) == {2: 1, 5: 1}
    assert cat_lines(m2) == {1: 1, 4: 2}
    text = "\n".join(m1 + m2)
    assert text.count("Cat") == 5
    assert len(re.findall(r"cat", text, re.IGNORECASE)) == 5  # 'cat'이 든 다른 단어(Category, Cats, 소문자 등) 없음
    assert not re.search(r"dog", text, re.IGNORECASE)
    assert not re.search(r"Cats|Category", text)


def test_e15_solution_output(tmp_path):
    wd = run_solution("E15", tmp_path)
    total_dog = 0
    for name, changed in (("memo1.txt", [2, 5]), ("memo2.txt", [1, 4])):
        before = (FIX / "E15" / name).read_text(encoding="utf-8").splitlines()
        after = (wd / name).read_text(encoding="utf-8").splitlines()
        assert len(before) == len(after)
        assert after == [ln.replace("Cat", "Dog") for ln in before]
        assert [i for i, (x, y) in enumerate(zip(before, after), 1) if x != y] == changed  # 나머지 줄은 그대로
        assert "Cat" not in "\n".join(after)
        total_dog += "\n".join(after).count("Dog")
    assert total_dog == 5
