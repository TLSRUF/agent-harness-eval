"""M01~M17 fixture 생성기. 시드를 고정했으므로 다시 실행하면 같은 파일이 만들어진다.

실행: python fixtures/_gen/gen_fixtures.py     (fixtures/M01~M17 과 fixtures/_gen/plants/*.json 을 다시 만든다)

설계
- 정답(개수, 줄 번호 목록, 값)을 먼저 정하고 그에 맞춰 파일을 만든다 (plants/<ID>.json의 answer).
- 함정(대소문자 변형, 접두가 겹치는 값, 다른 줄 본문 속 글자)은 만들지 못하게 생성 중에 assert로 막는다. 같은 검사를 tests/test_m_fixtures.py가 독립적으로 다시 한다.
- 모든 파일은 UTF-8, LF, 끝 줄바꿈으로 끝나고 빈 줄이 없으며 줄 앞뒤 공백이 없다.
- 이 폴더(fixtures/_gen)는 과제 fixture가 아니므로 에이전트의 작업 폴더에 복사되지 않는다(러너는 fixtures/<과제ID>/ 만 복사).
- 이 모듈의 count_words/count_lines는 verify_counts.py, file_stats 도구와 '같은 정의'인지 tests/test_count_definitions.py가 비교한다.
"""
from __future__ import annotations

import json
import random
import re
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURES = HERE.parent
PLANTS = HERE / "plants"


# ---------- 세기 정의 (생성기 쪽 구현) ----------

def count_words(text: str) -> int:
    """단어 = 공백으로 구분되는 덩어리 (정규식 분리로 구현)."""
    stripped = text.strip()
    return len(re.split(r"\s+", stripped)) if stripped else 0


def count_lines(text: str) -> int:
    """줄 수 = 줄바꿈 개수 (마지막 줄이 줄바꿈 없이 끝나면 그 줄도 센다)."""
    return text.count("\n") + (1 if text and not text.endswith("\n") else 0)


# ---------- 공통 보조 ----------

def write_file(d: Path, name: str, lines: list[str]) -> str:
    for ln in lines:
        assert ln != "" and ln == ln.strip() and "\t" not in ln, (name, ln)
    text = "\n".join(lines) + "\n"
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_bytes(text.encode("utf-8"))
    assert count_lines(text) == len(lines)
    return text


def stamps(rng: random.Random, n: int, start: datetime):
    t = start
    for _ in range(n):
        t += timedelta(seconds=rng.randint(1, 9))
        yield f"{t:%Y-%m-%d %H:%M:%S}"


# ---------- M01: IoT 게이트웨이 로그, dev-017이 든 줄 수 ----------

def gen_m01(rng: random.Random, out: Path):
    n, k = 300, 23
    targets = sorted(rng.sample(range(1, n + 1), k))
    devs = [f"dev-{i:03d}" for i in range(1, 41) if i != 17]
    events = [lambda r: f"temp={r.uniform(18, 32):.1f}C", lambda r: f"battery={r.randint(20, 100)}%",
              lambda r: "heartbeat ok", lambda r: f"rssi=-{r.randint(40, 90)}dBm",
              lambda r: f"humidity={r.randint(30, 70)}%", lambda r: f"firmware v{r.randint(1, 3)}.{r.randint(0, 9)} ok"]
    lines = []
    for i, ts in enumerate(stamps(rng, n, datetime(2026, 5, 3, 14, 0, 0)), 1):
        dev = "dev-017" if i in targets else rng.choice(devs)
        lines.append(f"{ts} {rng.choice(['gw-a', 'gw-b'])} {dev} {rng.choice(events)(rng)}")
    text = write_file(out, "gateway.log", lines)
    assert sum(1 for ln in lines if "dev-017" in ln) == k
    assert not re.search(r"(?i)dev-?17(?!\d)|dev017|dev-0170", text.replace("dev-017", ""))
    return {"count": k}, {"planted_lines": targets}


# ---------- M02: CI 로그, FAILED가 든 줄 번호 ----------

def gen_m02(rng: random.Random, out: Path):
    n, k = 250, 11
    targets = sorted(rng.sample(range(1, n + 1), k))
    mods = ["parser", "cache", "router", "auth", "export", "queue"]
    cases = ["basic", "empty", "unicode", "timeout", "overflow", "retry", "order", "limits"]
    lines, rid = [], 40100
    for i in range(1, n + 1):
        rid += rng.randint(1, 3)
        result = "FAILED" if i in targets else rng.choices(["PASSED", "SKIPPED"], weights=[9, 1])[0]
        lines.append(f"[run {rid}] test_{rng.choice(mods)}_{rng.choice(cases)} ... {result}")
    text = write_file(out, "ci.log", lines)
    assert [i for i, ln in enumerate(lines, 1) if "FAILED" in ln] == targets
    assert sum(1 for ln in lines if re.search(r"(?i)fail", ln)) == k  # fail이라는 글자는 FAILED 줄에만
    return {"items": [str(t) for t in targets]}, {"planted_lines": targets}


# ---------- M03: 주문 로그, E4021이 처음 나오는 줄 ----------

def gen_m03(rng: random.Random, out: Path):
    n = 350
    first = rng.randint(90, 220)
    later = sorted(rng.sample(range(first + 5, n + 1), 3))
    positions = [first] + later
    err_other = ["E3001", "E5003", "E4090", "E4020", "E4022"]
    msgs = {"INFO": ["order accepted", "payment captured", "shipment queued", "inventory reserved"],
            "DEBUG": ["cache lookup", "price recalculated", "address validated", "session refreshed"],
            "ERROR": ["order rejected", "payment declined", "stock mismatch", "carrier unavailable"]}
    lines, oid = [], 4000000
    # 앞부분에도 다른 오류 코드를 충분히 넣는다 (E4020, E4022는 E4021과 한 글자만 다른 함정이 아니라 별개 코드)
    for i, ts in enumerate(stamps(rng, n, datetime(2026, 5, 4, 8, 0, 0)), 1):
        oid += rng.randint(1, 5)
        if i in positions:
            level, code = "ERROR", "E4021"
        else:
            level = rng.choices(["INFO", "DEBUG", "ERROR"], weights=[6, 3, 1.6])[0]
            code = {"INFO": "S2000", "DEBUG": "S1000"}.get(level) or rng.choice(err_other)
        lines.append(f"{ts} order-svc {level} order={oid} code={code} {rng.choice(msgs[level])}")
    text = write_file(out, "orders.log", lines)
    hits = [i for i, ln in enumerate(lines, 1) if "E4021" in ln]
    assert hits == positions and hits[0] == first
    assert len(re.findall(r"E4021", text)) == len(re.findall(r"code=E4021 ", text)) == 4  # 접두가 겹치는 코드 없음
    assert all(text.count(c) >= 3 for c in ("E4020", "E4022"))
    return {"line": first}, {"planted_lines": positions}


# ---------- M04: 인증 로그, 정확히 한 번만 나오는 BUILD_ID ----------

def gen_m04(rng: random.Random, out: Path):
    n = 280
    counts = [5, 4, 4, 3, 3, 2, 2, 2, 1]  # 마지막(1번)이 정답, 나머지는 모두 2번 이상
    ids = []
    while len(ids) < len(counts):
        cand = "".join(rng.choice("0123456789abcdef") for _ in range(8))
        letters = sum(c.isalpha() for c in cand)
        if cand not in ids and 2 <= letters <= 6:
            ids.append(cand)
    markers = [bid for bid, c in zip(ids, counts) for _ in range(c)]
    rng.shuffle(markers)
    positions = sorted(rng.sample(range(1, n + 1), len(markers)))
    pos_to_id = dict(zip(positions, markers))
    users = [f"u{rng.randint(1000, 1999)}" for _ in range(40)]
    plain = ["login ok", "token refreshed", "password check passed", "session closed", "mfa challenge sent"]
    lines = []
    for i, ts in enumerate(stamps(rng, n, datetime(2026, 5, 5, 6, 30, 0)), 1):
        if i in pos_to_id:
            lines.append(f"{ts} deploy-agent INFO BUILD_ID={pos_to_id[i]} rollout started on node-{rng.randint(1, 6)}")
        else:
            lines.append(f"{ts} auth-svc INFO user={rng.choice(users)} {rng.choice(plain)}")
    text = write_file(out, "auth.log", lines)
    found = re.findall(r"BUILD_ID=([0-9a-f]{8})", text)
    assert len(found) == len(markers) == text.count("BUILD_ID")
    freq = {b: found.count(b) for b in set(found)}
    unique = [b for b, c in freq.items() if c == 1]
    assert unique == [ids[-1]] and text.count(ids[-1]) == 1  # 정답 값은 파일 어디에도 한 번만
    assert all(c >= 2 for b, c in freq.items() if b != ids[-1])
    assert not re.search(r"[0-9a-f]{8}", re.sub(r"BUILD_ID=[0-9a-f]{8}", "", text).replace("2026", ""))
    return {"value": ids[-1]}, {"planted_lines": [p for p, b in pos_to_id.items() if b == ids[-1]]}


# ---------- M05: 결제 로그, timeout과 retry=3이 둘 다 든 줄 수 ----------

def gen_m05(rng: random.Random, out: Path):
    n = 320
    both, timeout_only, retry3_only = 17, 38, 31
    kinds = ["both"] * both + ["timeout_only"] * timeout_only + ["retry3_only"] * retry3_only
    kinds += ["plain"] * (n - len(kinds))
    rng.shuffle(kinds)
    lines, txn = [], 100000
    for i, (ts, kind) in enumerate(zip(stamps(rng, n, datetime(2026, 5, 6, 9, 0, 0)), kinds), 1):
        txn += rng.randint(1, 4)
        if kind == "both":
            status, retry = "timeout", 3
        elif kind == "timeout_only":
            status, retry = "timeout", rng.randint(0, 2)
        elif kind == "retry3_only":
            status, retry = rng.choice(["ok", "declined"]), 3
        else:
            status, retry = rng.choice(["ok", "declined"]), rng.randint(0, 2)
        lines.append(f"{ts} pay-svc txn={txn:06d} status={status} retry={retry} amount={rng.randint(5, 400)}.{rng.randint(0, 99):02d}")
    text = write_file(out, "payments.log", lines)
    planted = [i for i, k in enumerate(kinds, 1) if k == "both"]
    assert [i for i, ln in enumerate(lines, 1) if "timeout" in ln and "retry=3" in ln] == planted
    # 함정 금지: retry=30/31 같은 접두 겹침, retry 값은 0~3 한 자리, timeout은 소문자 status 값으로만, 대소문자 변형 없음
    assert not re.search(r"retry=3\d", text)
    assert all(re.search(r"retry=[0-3](?= |$)", ln) for ln in lines)
    assert len(re.findall(r"(?i)timeout", text)) == len(re.findall(r"status=timeout", text)) == text.count("timeout")
    assert not re.search(r"Timeout|TIMEOUT|TimeOut", text)
    return {"count": both}, {"planted_lines": planted}


# ---------- M06: 설정 파일 10개, cache_ttl 키가 있는 파일 ----------

CONF_KEYS = ["host", "port", "workers", "log_level", "max_body", "gzip", "retries", "region", "mode", "cache_size",
             "cache_mode", "pool_size", "timeout_ms", "debug", "tls", "bind", "owner", "queue_depth", "batch", "schema"]


def _conf_lines(rng: random.Random, keys: list[str], k_lo: int, k_hi: int, skip_val: str | None = None) -> list[str]:
    chosen = rng.sample(keys, rng.randint(k_lo, k_hi))
    lines = []
    for key in chosen:
        val = rng.choice(["on", "off", "auto", "fast", "slow", str(rng.randint(1, 99)), f"v{rng.randint(1, 9)}"])
        lines.append(f"{key} = {val}")
    return lines


def gen_m06(rng: random.Random, out: Path):
    names = sorted(["analytics", "billing", "catalog", "delivery", "gateway", "inventory", "mailer", "search", "storage", "tracker"])
    planted = sorted(rng.sample(names, 4))
    texts = {}
    for name in names:
        lines = _conf_lines(rng, CONF_KEYS, 12, 19)
        if name in planted:
            lines.insert(rng.randint(0, len(lines)), f"cache_ttl = {rng.randint(30, 900)}")
        texts[name] = write_file(out, f"{name}.conf", lines)
    has = sorted(nm for nm, t in texts.items() if "cache_ttl" in t)
    assert has == planted and all(t.count("cache_ttl") == (1 if nm in planted else 0) for nm, t in texts.items())
    assert not any(re.search(r"(?i)cache_ttl", t) for nm, t in texts.items() if nm not in planted)
    return {"items": [f"{p}.conf" for p in planted]}, {"planted_files": planted}


# ---------- M07: 메모 파일 9개, deadline이 든 줄의 총 수 ----------

PLAIN_NOTES = ["Review the notes for {thing} with the team.", "Book a room for the {thing} meeting.",
               "Send the agenda for {thing} on Monday.", "Update the slides for {thing}.",
               "Ask finance about the budget for {thing}.", "Collect feedback after the {thing} demo.",
               "Archive the old files from {thing}.", "Plan the next steps for {thing}."]
DEADLINE_NOTES = ["The deadline for {thing} moves to {day}.", "Reminder: deadline is on {day} for {thing}.",
                  "We missed the deadline for {thing}."]


def gen_m07(rng: random.Random, out: Path):
    per_file = [3, 0, 2, 1, 4, 0, 2, 1, 1]
    things = ["the report", "the audit", "the launch", "the survey", "the budget", "the demo"]
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    total, texts = 0, {}
    for idx, k in enumerate(per_file, 1):
        n = rng.randint(15, 25)
        slots = set(rng.sample(range(n), k))
        lines = []
        for j in range(n):
            tpl = rng.choice(DEADLINE_NOTES) if j in slots else rng.choice(PLAIN_NOTES)
            lines.append("- " + tpl.format(thing=rng.choice(things), day=rng.choice(days)))
        texts[f"week{idx}.md"] = write_file(out, f"week{idx}.md", lines)
        total += k
    all_lines = [ln for t in texts.values() for ln in t.split("\n") if ln]
    hits = [ln for ln in all_lines if "deadline" in ln]
    assert len(hits) == total == sum(per_file) and all(ln.count("deadline") == 1 for ln in hits)
    joined = "\n".join(all_lines)
    assert not re.search(r"deadlines|Deadline|DEADLINE|DeadLine", joined)  # 복수형과 대문자 변형 금지 (소문자 deadline만 존재)
    return {"count": total}, {"per_file": dict(zip(texts, per_file))}


# ---------- M08: 설정 파일 12개, max_connections = 500 인 파일 ----------

def gen_m08(rng: random.Random, out: Path):
    keys = [k for k in CONF_KEYS if k not in ("timeout_ms",)]
    target_idx = rng.randint(1, 12)
    values = [100, 150, 200, 250, 300, 400, 600, 800, 1000, 1200]
    texts = {}
    for i in range(1, 13):
        lines = []
        for ln in _conf_lines(rng, keys, 9, 18):
            assert "500" not in ln
            lines.append(ln)
        val = 500 if i == target_idx else rng.choice(values)
        lines.insert(rng.randint(0, len(lines)), f"max_connections = {val}")
        texts[f"svc{i:02d}.conf"] = write_file(out, f"svc{i:02d}.conf", lines)
    exact = [nm for nm, t in texts.items() if "max_connections = 500" in t.split("\n")]
    assert exact == [f"svc{target_idx:02d}.conf"]
    assert sum(t.count("500") for t in texts.values()) == 1  # 500은 정답 줄 한 곳에만 (5000, 1500 같은 접두/부분 일치 없음)
    assert all(t.count("max_connections") == 1 for t in texts.values())
    return {"file": f"svc{target_idx:02d}.conf"}, {}


# ---------- M09: 문서 파일 10개, 줄 수가 가장 많은 파일 ----------

SENTENCES = ["The meeting starts at nine.", "Please bring the signed form.", "Lunch is served in the main hall.",
             "The next review is on Friday.", "Parking is limited near the east gate.", "Send questions to the front desk.",
             "The printer on the second floor is broken.", "Remember to lock the storage room.",
             "A short break follows the first session.", "Badges must be visible at all times.",
             "The training room holds twenty people.", "Notes from the last session are posted online."]


def gen_m09(rng: random.Random, out: Path):
    counts = [14, 31, 22, 47, 9, 38, 45, 27, 19, 33]
    rng.shuffle(counts)
    texts = {}
    for i, c in enumerate(counts, 1):
        lines = [f"{rng.choice(SENTENCES)}" for _ in range(c)]
        texts[f"doc_{i:02d}.txt"] = write_file(out, f"doc_{i:02d}.txt", lines)
    best = max(texts, key=lambda nm: count_lines(texts[nm]))
    assert sorted(count_lines(t) for t in texts.values())[-2:] == [45, 47]  # 최댓값 47은 유일, 2등 45
    assert all(t.endswith("\n") and "\n\n" not in t for t in texts.values())
    return {"file": best}, {"lines_per_file": {nm: count_lines(t) for nm, t in texts.items()}}


# ---------- M10: 메모 파일 8개, 단어 수가 20개 이상인 파일 ----------

WORD_POOL = ["river", "stone", "window", "paper", "garden", "morning", "coffee", "table", "silver", "bridge", "candle",
             "forest", "market", "pencil", "ocean", "lantern", "meadow", "harbor", "violet", "copper"]
THRESHOLD = 20


def gen_m10(rng: random.Random, out: Path):
    counts = [5, 9, 12, 19, 20, 21, 27, 36]  # 경계: 19(기준-1), 20(기준과 같음), 21(기준+1)
    rng.shuffle(counts)
    texts, words_of = {}, {}
    for i, c in enumerate(counts, 1):
        words = [rng.choice(WORD_POOL) for _ in range(c)]
        lines, j = [], 0
        while j < c:
            step = min(rng.randint(3, 7), c - j)
            lines.append(" ".join(words[j:j + step]))
            j += step
        name = f"memo_{i:02d}.txt"
        texts[name] = write_file(out, name, lines)
        words_of[name] = c
        assert count_words(texts[name]) == c
    big = sorted(nm for nm, c in words_of.items() if c >= THRESHOLD)
    assert len(big) == 4 and {19, 20, 21} <= set(words_of.values())
    assert all(re.fullmatch(r"[a-z]+( [a-z]+)*", ln) for t in texts.values() for ln in t.split("\n") if ln)  # 구두점 없는 단어, 한 칸 간격
    return {"items": big}, {"words_per_file": words_of, "threshold": THRESHOLD}


# ---------- M11~M13: CSV ----------

def _csv(out: Path, name: str, header: str, rows: list[str]) -> str:
    return write_file(out, name, [header] + rows)


def gen_m11(rng: random.Random, out: Path):
    items = ["cable", "router", "switch", "sensor", "relay", "fuse", "panel", "valve"]
    regions = ["east"] * 5 + ["west"] * 4 + ["north"] * 3 + ["south"] * 2
    rng.shuffle(regions)
    rows, east_sum = [], 0
    for i, reg in enumerate(regions, 1):
        qty = rng.randint(1, 9)
        east_sum += qty if reg == "east" else 0
        rows.append(f"r{200 + i},{rng.choice(items)},{reg},{qty}")
    _csv(out, "orders.csv", "order_id,item,region,qty", rows)
    assert east_sum <= 40
    return {"sum": east_sum}, {}


def gen_m12(rng: random.Random, out: Path):
    names = ["ari", "ben", "chae", "dan", "eun", "fay", "gus", "han", "ivy", "jin", "kai", "lee", "min", "noa", "oz"]
    teams = ["design"] * 4 + ["ops"] * 3 + ["qa"] * 5 + ["sales"] * 3
    rng.shuffle(teams)
    rows = [f"{nm},{tm},{rng.randint(1, 4)}" for nm, tm in zip(names, teams)]
    _csv(out, "members.csv", "member,team,level", rows)
    counts = {t: teams.count(t) for t in sorted(set(teams))}
    return {"items": [f"{t}: {c}" for t, c in counts.items()]}, {}


def gen_m13(rng: random.Random, out: Path):
    tools = ["wrench", "hammer", "chisel", "plane", "drill", "clamp", "level", "vise", "rasp", "awl", "mallet", "tongs"]
    prices = rng.sample(range(15, 251), len(tools))
    rows = [f"{t},{p},{rng.randint(1, 40)}" for t, p in zip(tools, prices)]
    _csv(out, "products.csv", "product,price,stock", rows)
    top = [t for _, t in sorted(zip(prices, tools), reverse=True)[:3]]
    return {"items": top}, {}


# ---------- M14~M17: 수정/변환 (고정 내용) ----------

def gen_m14(rng: random.Random, out: Path):
    lines = ["[server]", "host = 10.0.0.5", "port = 8443", "timeout = 30", "workers = 4",
             "[network]", "retries = 3", "backoff = 3", "idle = 30", "keepalive = yes",
             "[logging]", "level = info", "max_size = 100", "rotate = daily"]
    text = write_file(out, "service.ini", lines)
    assert sum(1 for ln in lines if ln.startswith("timeout")) == 1 and sum(1 for ln in lines if ln.startswith("retries")) == 1
    return None, {}


def gen_m15(rng: random.Random, out: Path):
    lines = ["# legacy service settings", "host = app01", "# primary port", "port = 8080", "workers = 6",
             "# unused since 2019", "mode = standard", "# timeouts below", "connect = 5", "read = 15",
             "# keep in sync with proxy", "proxy = off", "log = /var/log/app.log", "# rotation", "rotate = weekly",
             "retain = 4", "# end of file"]
    text = write_file(out, "legacy.conf", lines)
    # 줄 전체가 #로 시작하는 줄만 있다: 줄 중간 주석, 앞에 공백이 붙은 #, 빈 줄은 없다
    assert all(ln.startswith("#") or "#" not in ln for ln in lines)
    return None, {}


def gen_m16(rng: random.Random, out: Path):
    people = [{"id": 1, "name": "김민준", "city": "서울"}, {"id": 2, "name": "이서연", "city": "부산"},
              {"id": 3, "name": "박지호", "city": "대전"}, {"id": 4, "name": "최유나", "city": "광주"},
              {"id": 5, "name": "정도윤", "city": "인천"}]
    out.mkdir(parents=True, exist_ok=True)
    text = json.dumps(people, ensure_ascii=False, indent=2) + "\n"
    (out / "people.json").write_bytes(text.encode("utf-8"))
    return None, {}


def gen_m17(rng: random.Random, out: Path):
    rows = ["한지우,91", "오세민,67", "송하늘,100", "윤재이,78", "강나래,85"]
    write_file(out, "scores.csv", ["name,score"] + rows)
    return None, {}


GENERATORS = {f"M{i:02d}": fn for i, fn in enumerate(
    [gen_m01, gen_m02, gen_m03, gen_m04, gen_m05, gen_m06, gen_m07, gen_m08, gen_m09, gen_m10,
     gen_m11, gen_m12, gen_m13, gen_m14, gen_m15, gen_m16, gen_m17], 1)}
SEEDS = {tid: 20261100 + i for i, tid in enumerate(GENERATORS, 1)}


def generate_all(fixtures_root: Path = FIXTURES, plants_root: Path = PLANTS) -> None:
    plants_root.mkdir(parents=True, exist_ok=True)
    for tid, fn in GENERATORS.items():
        out = fixtures_root / tid
        if out.exists():
            shutil.rmtree(out)
        answer, meta = fn(random.Random(SEEDS[tid]), out)
        pf = plants_root / f"{tid}.json"
        if answer is None:
            pf.unlink(missing_ok=True)
            continue
        rec = {"id": tid, "seed": SEEDS[tid], "answer": answer, "planted": meta}
        pf.write_bytes((json.dumps(rec, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


if __name__ == "__main__":
    generate_all()
    print("generated:", ", ".join(GENERATORS))
