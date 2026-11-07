"""M01~M17 fixture 검증. 생성기와 코드를 공유하지 않고, 함정과 크기 규칙을 독립적으로 다시 검사한다."""
import importlib.util
import json
import re
from pathlib import Path

import pytest

from src.eval import loader, verify_counts

FIX = loader.FIXTURES_DIR
PLANTS = loader.PLANTS_DIR

spec = importlib.util.spec_from_file_location("gen_fixtures_for_m_test", FIX / "_gen" / "gen_fixtures.py")
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

M_IDS = [f"M{i:02d}" for i in range(1, 18)]
ANSWER_IDS = [f"M{i:02d}" for i in range(1, 14)]


def text(tid, name):
    return (FIX / tid / name).read_bytes().decode("utf-8")


def lines(tid, name):
    return text(tid, name).split("\n")[:-1]


def plant(tid):
    return json.loads((PLANTS / f"{tid}.json").read_text(encoding="utf-8"))


# ---------------- 재생성 동일성 ----------------

def test_regeneration_is_byte_identical(tmp_path):
    gen.generate_all(tmp_path / "fx", tmp_path / "pl")
    for tid in M_IDS:
        new = {p.name: p.read_bytes() for p in (tmp_path / "fx" / tid).iterdir()}
        old = {p.name: p.read_bytes() for p in (FIX / tid).iterdir()}
        assert new == old, tid
        if tid in ANSWER_IDS:
            assert (tmp_path / "pl" / f"{tid}.json").read_bytes() == (PLANTS / f"{tid}.json").read_bytes(), tid
        else:
            assert not (PLANTS / f"{tid}.json").exists() and not (tmp_path / "pl" / f"{tid}.json").exists()


# ---------------- 크기 규칙 ----------------

@pytest.mark.parametrize("tid", ["M01", "M02", "M03", "M04", "M05"])
def test_big_log_is_one_file_of_200_to_400_lines(tid):
    files = sorted((FIX / tid).iterdir())
    assert len(files) == 1
    assert 200 <= len(lines(tid, files[0].name)) <= 400


@pytest.mark.parametrize("tid,lo,hi", [("M06", 8, 12), ("M07", 8, 12), ("M08", 8, 12), ("M09", 8, 12), ("M10", 8, 12)])
def test_multi_file_tasks_have_8_to_12_files(tid, lo, hi):
    assert lo <= len(list((FIX / tid).iterdir())) <= hi


def test_exact_file_counts():
    assert [len(list((FIX / t).iterdir())) for t in ("M06", "M07", "M08", "M09", "M10")] == [10, 9, 12, 10, 8]


@pytest.mark.parametrize("tid", M_IDS)
def test_files_are_clean_text(tid):
    for p in sorted((FIX / tid).iterdir()):
        data = p.read_bytes()
        t = data.decode("utf-8")  # UTF-8로 디코드 가능
        assert b"\r" not in data and t.endswith("\n"), p
        if p.suffix == ".json":
            continue  # JSON 들여쓰기 줄은 앞 공백이 있다
        for n, ln in enumerate(t.split("\n")[:-1], 1):
            assert ln != "" and ln == ln.strip() and "\t" not in ln, (p.name, n)  # 빈 줄 없음, 앞뒤 공백 없음


# ---------------- 함정 금지: 큰 로그 ----------------

def test_m01_dev017():
    ls = lines("M01", "gateway.log")
    hit = [ln for ln in ls if "dev-017" in ln]
    assert len(hit) == plant("M01")["answer"]["count"] == 23
    rest = "\n".join(ls).replace("dev-017", "")
    assert not re.search(r"(?i)dev-?0?17(?!\d)|dev-?17", rest)          # 변형 없음
    assert all(re.fullmatch(r"\S+ \S+ gw-[ab] dev-\d{3} \S.*", ln) for ln in ls)
    assert all(ln.split()[3] == "dev-017" for ln in hit)                   # 다른 줄 본문 속에 끼어 있지 않음


def test_m02_failed():
    ls = lines("M02", "ci.log")
    nums = [i for i, ln in enumerate(ls, 1) if "FAILED" in ln]
    assert [str(n) for n in nums] == plant("M02")["answer"]["items"] and len(nums) == 11
    assert [i for i, ln in enumerate(ls, 1) if re.search(r"(?i)fail", ln)] == nums  # failed/Failed 같은 변형 없음
    assert all(re.search(r"\.\.\. (PASSED|SKIPPED|FAILED)$", ln) for ln in ls)


def test_m03_e4021():
    ls = lines("M03", "orders.log")
    first = next(i for i, ln in enumerate(ls, 1) if "E4021" in ln)
    assert first == plant("M03")["answer"]["line"]
    t = "\n".join(ls)
    assert not re.search(r"E4021\d|\dE4021|(?i:e4021)(?<!E4021)", t)       # 접두/접미가 겹치는 코드, 소문자 변형 없음
    assert len(re.findall(r"E4021", t)) >= 3
    assert len(re.findall(r"E4020", t)) >= 3 and len(re.findall(r"E4022", t)) >= 3  # 한 글자 다른 별개 코드도 존재


def test_m04_build_id():
    t = text("M04", "auth.log")
    ids = re.findall(r"BUILD_ID=([0-9a-f]{8})", t)
    assert len(ids) == t.count("BUILD_ID") == 26
    freq = {i: ids.count(i) for i in set(ids)}
    once = [i for i, c in freq.items() if c == 1]
    assert once == [plant("M04")["answer"]["value"]] and t.count(once[0]) == 1
    assert len(freq) == 9 and sum(1 for c in freq.values() if c >= 2) == 8
    assert not re.search(r"(?i)build_id=(?![0-9a-f]{8}\b)", t) and "build_id" not in t and "Build_Id" not in t


def test_m05_timeout_retry3_traps():
    ls = lines("M05", "payments.log")
    t = "\n".join(ls)
    both = [i for i, ln in enumerate(ls, 1) if "timeout" in ln and "retry=3" in ln]
    assert len(both) == plant("M05")["answer"]["count"] == 17
    # 사용자 요구: retry=30, retry=31 같은 접두가 겹치는 값 금지
    assert not re.search(r"retry=3\d", t) and not re.search(r"retry=\d{2,}", t)
    assert all(re.fullmatch(r"\S+ \S+ pay-svc txn=\d{6} status=(ok|declined|timeout) retry=[0-3] amount=\d+\.\d{2}", ln) for ln in ls)
    # 사용자 요구: Timeout, TIMEOUT 같은 대소문자 변형 금지, timeout은 status 값으로만 존재
    assert not re.search(r"Timeout|TIMEOUT|TimeOut|timeOut", t)
    assert len(re.findall(r"(?i)timeout", t)) == len(re.findall(r"status=timeout\b", t))
    # 정답이 두 조건의 교집합이라는 것: 각 조건만 가진 줄이 충분히 있다
    only_timeout = [ln for ln in ls if "status=timeout" in ln and "retry=3" not in ln]
    only_retry3 = [ln for ln in ls if "retry=3" in ln and "timeout" not in ln]
    assert len(only_timeout) >= 30 and len(only_retry3) >= 20


# ---------------- 함정 금지: 여러 파일 ----------------

def test_m06_cache_ttl():
    names = sorted(p.name for p in (FIX / "M06").iterdir())
    has = [n for n in names if "cache_ttl" in text("M06", n)]
    assert has == plant("M06")["answer"]["items"] and len(has) == 4
    for n in names:
        t = text("M06", n)
        assert t.count("cache_ttl") == (1 if n in has else 0) and not re.search(r"(?i)cache_ttl", t.replace("cache_ttl", ""))
        assert re.search(r"^cache_ttl = \d+$", t, re.M) if n in has else True


def test_m07_deadline():
    total, per = 0, {}
    for p in sorted((FIX / "M07").iterdir()):
        ls = p.read_bytes().decode("utf-8").split("\n")[:-1]
        k = sum(1 for ln in ls if "deadline" in ln)
        per[p.name] = k
        total += k
        assert all(ln.count("deadline") <= 1 for ln in ls)
        assert not re.search(r"deadlines|Deadline|DEADLINE|Deadlines", "\n".join(ls))
    assert total == plant("M07")["answer"]["count"] == 14 and 0 in per.values()


def test_m08_max_connections():
    hits = []
    for p in sorted((FIX / "M08").iterdir()):
        t = p.read_bytes().decode("utf-8")
        assert t.count("max_connections") == 1
        if "max_connections = 500" in t.split("\n"):
            hits.append(p.name)
        # 500이 접두/부분으로 겹치는 값(5000, 1500, 500x)이 어디에도 없다
        assert len(re.findall(r"500", t)) == (1 if p.name in hits else 0)
    assert hits == [plant("M08")["answer"]["file"]]


def test_m09_longest_is_unique():
    counts = {p.name: len(p.read_bytes().decode("utf-8").split("\n")) - 1 for p in sorted((FIX / "M09").iterdir())}
    top = sorted(counts.values())
    assert top[-1] == 47 and top[-2] == 45
    assert [n for n, c in counts.items() if c == 47] == [plant("M09")["answer"]["file"]]
    assert plant("M09")["planted"]["lines_per_file"] == counts


def test_m10_boundary_files():
    words = {p.name: len(p.read_bytes().decode("utf-8").split()) for p in sorted((FIX / "M10").iterdir())}
    vals = sorted(words.values())
    assert vals == [5, 9, 12, 19, 20, 21, 27, 36]
    assert {19, 20, 21} <= set(vals)                                   # 기준-1, 기준, 기준+1 경계 파일
    big = sorted(n for n, w in words.items() if w >= 20)
    assert big == plant("M10")["answer"]["items"] and len(big) == 4
    exact = [n for n, w in words.items() if w == 20]
    assert len(exact) == 1 and exact[0] in big
    for p in (FIX / "M10").iterdir():
        for ln in p.read_bytes().decode("utf-8").split("\n")[:-1]:
            assert re.fullmatch(r"[a-z]+( [a-z]+)*", ln)               # 구두점 없는 단어, 한 칸 간격


# ---------------- CSV, 수정, 변환 ----------------

def test_m11_m12_m13_answers():
    import csv
    def rows(tid, name):
        with (FIX / tid / name).open(encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))
    r11 = rows("M11", "orders.csv")
    assert len(r11) == 14 and {r["region"] for r in r11} == {"east", "west", "north", "south"}
    assert sum(int(r["qty"]) for r in r11 if r["region"] == "east") == plant("M11")["answer"]["sum"] <= 40
    r12 = rows("M12", "members.csv")
    assert len(r12) == 15 and plant("M12")["answer"]["items"] == ["design: 4", "ops: 3", "qa: 5", "sales: 3"]
    r13 = rows("M13", "products.csv")
    prices = [int(r["price"]) for r in r13]
    assert len(set(prices)) == len(prices) == 12
    top = [r["product"] for r in sorted(r13, key=lambda r: -int(r["price"]))[:3]]
    assert top == plant("M13")["answer"]["items"]


def test_m14_keys_are_unique_targets():
    ls = lines("M14", "service.ini")
    assert [ln for ln in ls if ln.startswith("timeout")] == ["timeout = 30"]
    assert [ln for ln in ls if ln.startswith("retries")] == ["retries = 3"]
    assert "backoff = 3" in ls and "idle = 30" in ls                   # 같은 값을 가진 다른 키(정밀도 확인용)


def test_m15_comment_lines_are_whole_line_only():
    ls = lines("M15", "legacy.conf")
    comments = [ln for ln in ls if ln.startswith("#")]
    assert len(comments) == 7
    assert not [ln for ln in ls if "#" in ln and not ln.startswith("#")]      # 줄 중간 주석 없음
    assert not [ln for ln in ls if ln.lstrip().startswith("#") and not ln.startswith("#")]  # 앞에 공백 붙은 # 없음
    assert all(ln for ln in ls)                                                # 빈 줄 없음


def test_m16_m17_inputs():
    people = json.loads(text("M16", "people.json"))
    assert len(people) == 5 and all(list(o) == ["id", "name", "city"] for o in people)
    assert all(isinstance(o["id"], int) for o in people)
    scores = lines("M17", "scores.csv")
    assert scores[0] == "name,score" and len(scores) == 6 and all("," in ln and ln.count(",") == 1 for ln in scores)


# ---------------- E 시리즈와 내용이 겹치지 않음 ----------------

def _strip_ts(ln: str) -> str:
    return re.sub(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d ", "", ln)


def test_no_content_overlap_with_easy_tasks():
    easy_lines = {_strip_ts(ln) for t in ("E01", "E13") for ln in lines(t, "app.log")}
    easy_messages = {re.sub(r"^(INFO|WARN|ERROR|DEBUG)\s+|^\[\w+\] ", "", ln) for ln in easy_lines}
    easy_bytes = {p.read_bytes() for d in FIX.glob("E[0-9][0-9]") for p in d.iterdir() if p.name != ".gitkeep"}
    for tid in M_IDS:
        for p in (FIX / tid).iterdir():
            assert p.read_bytes() not in easy_bytes, (tid, p.name)
            for ln in p.read_bytes().decode("utf-8").split("\n")[:-1]:
                assert _strip_ts(ln) not in easy_lines and ln not in easy_messages, (tid, p.name, ln)


# ---------------- 생성기가 정한 값 = 독립 검색으로 센 값 ----------------

@pytest.mark.parametrize("tid", ANSWER_IDS)
def test_planted_answer_equals_independent_count(tid):
    assert plant(tid)["answer"] == verify_counts.COUNTERS[tid](FIX / tid)


def fake_task(tid, answer):
    return loader.Task(id=tid, slug="x", rev=1, difficulty="medium", prompt="p", fixture=tid, outputs=[], grading={},
                       overlap_with=[], hand_check="h", raw={"answer": answer})


def test_loader_check6_passes_when_all_three_agree():
    for tid in ANSWER_IDS:
        assert loader.check_plant(fake_task(tid, plant(tid)["answer"])) == []


def test_loader_check6_fails_when_values_differ(tmp_path):
    ok = plant("M01")["answer"]
    # 1) 과제 JSON의 answer가 다름
    assert any("[6]" in e for e in loader.check_plant(fake_task("M01", {"count": ok["count"] + 1})))
    # 2) 생성기가 정한 값(plants)이 다름
    (tmp_path / "M01.json").write_text(json.dumps({"id": "M01", "answer": {"count": 99}}), encoding="utf-8")
    assert any("[6]" in e for e in loader.check_plant(fake_task("M01", ok), plants_dir=tmp_path))
    # 3) 독립 검색이 센 값이 다름 (카운터를 바꿔치기)
    (tmp_path / "M01.json").write_text(json.dumps({"id": "M01", "answer": ok}), encoding="utf-8")
    errs = loader.check_plant(fake_task("M01", ok), plants_dir=tmp_path, counters={"M01": lambda d: {"count": 7}})
    assert errs and "[6]" in errs[0] and "독립 검색" in errs[0]
    # 4) 카운터 누락 / plants 누락 / answer 누락
    assert any("카운터가 없음" in e for e in loader.check_plant(fake_task("M01", ok), plants_dir=tmp_path, counters={}))
    assert any("plants 파일이 없음" in e for e in loader.check_plant(fake_task("M02", plant("M02")["answer"]), plants_dir=tmp_path))
    t = fake_task("M01", ok)
    t.raw.pop("answer")
    assert any("answer가 없음" in e for e in loader.check_plant(t, plants_dir=tmp_path))
    # 5) 카운터가 예외를 내면 실패로 보고
    def boom(d):
        raise AssertionError("two answers")
    assert any("예외" in e for e in loader.check_plant(fake_task("M01", ok), plants_dir=tmp_path, counters={"M01": boom}))


def test_loader_check6_skips_hand_made_tasks():
    t = fake_task("E01", None)
    t.raw.pop("answer")
    assert loader.check_plant(t) == []
