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


# ====================== Day 6: 어려운 과제 H01~H08 ======================

EXOTIC = re.compile("[\r\u2028\u2029\u0085\x0b\x0c\x1c\x1d\x1e]")  # file_stats(splitlines)가 줄바꿈으로 세는 특수 문자: fixture에 넣지 않는다


def write_hard(d: Path, name: str, lines: list[str]) -> str:
    text = write_file(d, name, lines)
    assert not EXOTIC.search(text), f"{name}: 특수 줄 구분 문자 금지"
    return text


# ---------- H01: 큰 파일 통계. 단어 수가 가장 많은 3개 파일 ----------

H01_LINE_COUNTS = [182, 215, 347, 156, 298, 261, 389, 204, 327, 176]
H01_TEMPLATES = [
    "{ts} INFO worker-{a} job {b} done in {c}ms",
    "{ts} DEBUG cache hit key={b}",
    "{ts} WARN slow query took {c}ms on shard-{a}",
    "{ts} INFO request {b} served status={s}",
    "{ts} ERROR upstream timeout after {c}ms retrying",
    "{ts} INFO heartbeat ok",
]


def gen_h01(rng: random.Random, out: Path):
    names = [f"app_{i:02d}.log" for i in range(1, 11)]
    for _attempt in range(300):
        texts, words, lines_n = {}, {}, {}
        for name, n in zip(names, H01_LINE_COUNTS):
            weights = [rng.random() + 0.15 for _ in H01_TEMPLATES]
            lines = []
            for ts in stamps(rng, n, datetime(2026, 6, 1, 9, 0, 0)):
                tpl = rng.choices(H01_TEMPLATES, weights=weights)[0]
                lines.append(tpl.format(ts=ts, a=rng.randint(1, 9), b=rng.randint(100, 999), c=rng.randint(5, 900), s=rng.choice([200, 200, 200, 404, 500])))
            texts[name] = "\n".join(lines) + "\n"
            words[name], lines_n[name] = count_words(texts[name]), n
        by_w = sorted(names, key=lambda x: -words[x])
        by_l = sorted(names, key=lambda x: -lines_n[x])
        gaps_ok = all(words[by_w[i]] - words[by_w[i + 1]] >= 25 for i in range(3))   # 1~3등 사이와 3등-4등 사이가 25 이상
        if len(set(words.values())) == 10 and set(by_w[:3]) != set(by_l[:3]) and gaps_ok:
            break
    else:
        raise AssertionError("H01 조건을 만족하는 조합을 찾지 못함")
    for name in names:
        write_hard(out, name, texts[name].split("\n")[:-1])
    top3 = by_w[:3]
    assert all(150 <= lines_n[n] <= 400 for n in names)
    return {"items": [f"{n}: {words[n]}" for n in top3]}, {"words_per_file": words, "lines_per_file": lines_n, "top_by_lines": by_l[:3]}


# ---------- H02: 다단계(통계 -> 필터 -> 합). 줄 수가 100줄 이상인 파일들의 줄 수 합 ----------

H02_COUNTS = [18, 41, 63, 77, 99, 100, 101, 112, 29, 54, 88, 35]  # 경계: 99(기준-1), 100(기준), 101(기준+1)
H02_TEMPLATES = ["Invoice batch {n} was archived on shelf {s}.", "Ledger page {n} was reviewed by clerk {c}.",
                 "Receipt bundle {n} moved to cabinet {s}.", "Audit note {n} was signed by clerk {c}."]


def gen_h02(rng: random.Random, out: Path):
    counts = H02_COUNTS[:]
    rng.shuffle(counts)
    texts = {}
    for i, c in enumerate(counts, 1):
        lines = [rng.choice(H02_TEMPLATES).format(n=rng.randint(100, 999), s=rng.randint(1, 40), c=rng.choice("ABCDEFGH")) for _ in range(c)]
        texts[f"part_{i:02d}.txt"] = write_hard(out, f"part_{i:02d}.txt", lines)
    lc = {nm: count_lines(t) for nm, t in texts.items()}
    big = {nm: c for nm, c in lc.items() if c >= 100}
    assert sorted(big.values()) == [100, 101, 112] and {99, 100, 101} <= set(lc.values())
    return {"sum": sum(big.values())}, {"lines_per_file": lc}


# ---------- H03: 충돌하는 문서. 최신 날짜 문서의 포트 (동률이면 파일 이름 알파벳 순) ----------

H03_DOCS = {  # 파일: (Last updated, 포트, 포트 문장)
    "changelog.md": ("2025-11-20", 3000, "Services listen on port {p} by default."),
    "faq.md": ("2026-02-02", 8081, "By default the server uses port {p}."),
    "ops_guide.md": ("2026-03-14", 8443, "The default port is {p}."),
    "readme.md": ("2026-01-05", 8080, "The default port is {p}."),
    "release_notes.md": ("2026-03-01", 9090, "Services listen on port {p} by default."),
    "runbook.md": ("2026-03-14", 9000, "By default the server uses port {p}."),
}
H03_FILLER = ["Check the service logs before restarting.", "Backups run every night at low traffic.",
              "Contact the on-call engineer for urgent issues.", "Keep configuration files under version control.",
              "Restart the worker after changing the schedule.", "Metrics are sent every minute.",
              "Use the staging environment for dry runs.", "Rotate credentials every quarter.",
              "Document every change in the team notes.", "Review alerts at the start of each shift.",
              "Disk usage is checked by the nightly job.", "Escalate unknown errors to the platform team."]


def gen_h03(rng: random.Random, out: Path):
    texts = {}
    for name, (date, port, sentence) in H03_DOCS.items():
        body = rng.sample(H03_FILLER, rng.randint(8, 12))
        body.insert(rng.randint(0, len(body)), sentence.format(p=port))
        title = "# " + name.split(".")[0].replace("_", " ").title()
        texts[name] = write_hard(out, name, [title, f"Last updated: {date}"] + body)
    for name, t in texts.items():
        assert len(re.findall(r"\d{4}-\d{2}-\d{2}", t)) == 1, name                                 # 날짜는 문서마다 하나, 형식은 YYYY-MM-DD
        assert len(re.findall(r"\d{4,5}", re.sub(r"\d{4}-\d{2}-\d{2}", "", t))) == 1, name       # 포트 문장 하나뿐, 다른 네다섯 자리 숫자 없음
        assert not re.search(r"(?i)last updated:(?! \d{4}-\d{2}-\d{2}$)", t, re.M), name
    latest = max(d for d, _, _ in H03_DOCS.values())
    tied = sorted(n for n, (d, _, _) in H03_DOCS.items() if d == latest)
    assert tied == ["ops_guide.md", "runbook.md"] and H03_DOCS[tied[0]][1] != H03_DOCS[tied[1]][1]  # 최신 날짜 동률 한 쌍, 포트가 다름
    return {"port": H03_DOCS[tied[0]][1]}, {"latest": latest, "tied_files": tied}


# ---------- H04: 오류가 섞인 입력. 첫 줄 '# lines: N'이 실제 줄 수와 다른 문서 ----------

H04_TOTALS = [34, 52, 71, 45, 120, 88, 63, 39, 97, 56]  # 헤더 줄을 포함한 실제 줄 수


def gen_h04(rng: random.Random, out: Path):
    names = [f"spec_{i:02d}.txt" for i in range(1, 11)]
    totals = H04_TOTALS[:]
    rng.shuffle(totals)
    wrong_idx = rng.sample(range(10), 3)
    deltas = {wrong_idx[0]: -1, wrong_idx[1]: +1, wrong_idx[2]: +12}   # 오차 1(헤더를 빼고 센 값), 오차 1(하나 더), 크게 틀림
    texts, claims = {}, {}
    for i, (name, total) in enumerate(zip(names, totals)):
        claim = total + deltas.get(i, 0)
        body = [f"Section {k} covers item {rng.randint(10, 99)} of the plan." for k in range(1, total)]
        texts[name] = write_hard(out, name, [f"# lines: {claim}"] + body)
        claims[name] = (claim, total)
    wrong = sorted(n for n, (c, t) in claims.items() if c != t)
    assert len(wrong) == 3 and all(count_lines(texts[n]) == claims[n][1] for n in names)
    assert any(c == t - 1 for c, t in claims.values()) and any(c == t + 1 for c, t in claims.values())  # 오차 1 함정이 실제로 있다
    assert all(t.count("# lines:") == 1 and t.startswith("# lines: ") and sum(1 for ln in t.split("\n") if ln.startswith("#")) == 1 for t in texts.values())
    return {"items": wrong}, {"claims": {n: {"claimed": c, "actual": t} for n, (c, t) in claims.items()}}


# ---------- H05: 대규모 수정. 값이 정확히 같은 endpoint 줄만 바꾼다 ----------

H05_OLD = "endpoint = http://old.internal:8080"
H05_NEW = "endpoint = http://new.internal:9090"
H05_DECOYS = ["# " + H05_OLD, "backup_" + H05_OLD, "endpoint = http://old.internal:8081", H05_OLD + "/health",
              "endpoint = http://old.internal:80800", "endpoint = http://olds.internal:8080"]
H05_KEYS = ["host", "port", "workers", "log_level", "mode", "region", "pool_size", "retries", "tls", "schema", "owner", "batch"]


def gen_h05(rng: random.Random, out: Path):
    names = [f"svc_{i:02d}.conf" for i in range(1, 11)]
    target_files = sorted(rng.sample(names, 6))
    others = [n for n in names if n not in target_files]
    decoys_for = {n: [] for n in names}
    pool = H05_DECOYS * 2
    rng.shuffle(pool)
    for n in others:                      # 바꿀 줄이 없는 파일 4개: 디코이 2개씩
        decoys_for[n] += [pool.pop(), pool.pop()]
    for n in rng.sample(target_files, 3):  # 대상 파일 중 3개에도 디코이 1개
        decoys_for[n].append(pool.pop())
    expected, changed, texts = {}, {}, {}
    for n in names:
        lines = []
        for key in rng.sample(H05_KEYS, rng.randint(6, 11)):
            lines.append(f"{key} = {rng.choice(['on', 'off', 'auto', str(rng.randint(1, 99)), 'v' + str(rng.randint(1, 9))])}")
        for d in decoys_for[n]:
            lines.insert(rng.randint(0, len(lines)), d)
        if n in target_files:
            lines.insert(rng.randint(0, len(lines)), H05_OLD)
        texts[n] = write_hard(out, n, lines)
        expected[n] = "\n".join(H05_NEW if ln == H05_OLD else ln for ln in lines) + "\n"
        if n in target_files:
            changed[n] = lines.index(H05_OLD) + 1
    flat = [ln for t in texts.values() for ln in t.split("\n")]
    assert sum(1 for ln in flat if ln == H05_OLD) == 6 == len(changed)
    assert {d for d in H05_DECOYS} <= set(flat)                         # 디코이 6종이 모두 실제로 쓰였다
    assert all(sum(1 for ln in t.split("\n") if ln == H05_OLD) == (1 if n in target_files else 0) for n, t in texts.items())
    assert not any(ln.startswith(" ") or "new.internal" in ln for ln in flat)
    return {"changed": changed}, {"expected": expected, "decoys_for": decoys_for}


# ---------- H06: 교차 참조. 목록에 있는 고객 중 주문이 가장 많은 고객의 이름 ----------

H06_NAMES = ["Aldo", "Bruna", "Cleo", "Dmitri", "Esme", "Farid", "Greta", "Hugo", "Ines", "Jonas", "Kira", "Lazlo", "Mona", "Nils",
             "Olga", "Pablo", "Quinn", "Rosa", "Silas", "Tara", "Uriel", "Vera", "Wilf", "Xena", "Yusuf", "Zora", "Alma", "Brent",
             "Cyrus", "Dana", "Elio", "Fern", "Gael", "Hana", "Ivor", "Jade", "Knut", "Lena", "Milo", "Nora"]


def gen_h06(rng: random.Random, out: Path):
    ids = [f"c{i:03d}" for i in range(1, 41)]
    lowered = [n.lower() for n in H06_NAMES]
    assert len(set(lowered)) == 40 and not any(a != b and a in b for a in lowered for b in lowered)  # 이름 중복, 부분 문자열 금지
    tiers = ["gold"] * 9 + ["silver"] * 13 + ["basic"] * 18
    rng.shuffle(tiers)
    top, second = rng.sample(ids, 2)
    order_ids = [top] * 8 + [second] * 6 + ["c099"] * 11            # c099는 customers.csv에 없는 id이고 전체에서 가장 많다(함정)
    rest = [i for i in ids if i not in (top, second)]
    extra: list[str] = []
    while len(extra) < 35:
        pick = rng.choice(rest)
        if extra.count(pick) < 5:
            extra.append(pick)
    order_ids += extra
    rng.shuffle(order_ids)
    write_hard(out, "customers.csv", ["id,name,tier"] + [f"{i},{n},{t}" for i, n, t in zip(ids, H06_NAMES, tiers)])
    write_hard(out, "orders.csv", ["order_id,customer_id,qty"] + [f"o{n:03d},{cid},{rng.randint(1, 9)}" for n, cid in enumerate(order_ids, 1)])
    from collections import Counter
    freq = Counter(order_ids)
    known = {k: v for k, v in freq.items() if k in ids}
    ranked = sorted(known.values(), reverse=True)
    assert len(order_ids) == 60 and ranked[0] == 8 and ranked[1] == 6 and freq["c099"] == 11 > ranked[0]
    name_of = dict(zip(ids, H06_NAMES))
    return {"name": name_of[top]}, {"top_id": top, "top_count": 8, "second_id": second, "second_count": 6, "unknown_id": "c099", "unknown_count": 11}


# ---------- H07: 다단계. include 체인을 따라간 최종 timeout ----------

H07_FILES = {
    "main.conf": ["timeout = 10", "include = site.conf", "# include = legacy.conf", "include = base.conf", "mode = fast"],
    "site.conf": ["timeout = 50", "region = eu"],
    "base.conf": ["timeout = 20", "include = net.conf", "retries = 3"],
    "net.conf": ["timeout = 30", "include = tuning.conf", "timeout = 35"],
    "tuning.conf": ["include = deep.conf", "timeout = 40"],
    "deep.conf": ["timeout = 45"],
    "legacy.conf": ["timeout = 77"],     # include가 주석 처리되어 처리되지 않는 파일
    "orphan.conf": ["timeout = 99"],     # 어디에서도 include되지 않는 파일
}


def gen_h07(rng: random.Random, out: Path):
    for name, lines in H07_FILES.items():
        write_hard(out, name, lines)
    answer = 35  # 처리 순서: main(10) -> site(50) -> base(20) -> net(30) -> tuning -> deep(45) -> tuning(40) -> net(35)  -> 이후 timeout 대입 없음
    decoys = {10, 50, 20, 30, 40, 45, 77, 99}
    assert answer not in decoys and len(H07_FILES) == 8
    return {"timeout": answer}, {"trace": ["main L1: 10", "main L2 include site.conf -> site L1: 50", "main L3 주석, 무시",
                                           "main L4 include base.conf -> base L1: 20", "base L2 include net.conf -> net L1: 30",
                                           "net L2 include tuning.conf -> tuning L1 include deep.conf -> deep L1: 45",
                                           "tuning L2: 40", "net L3: 35", "base L3 retries (timeout 아님)", "main L5 mode (timeout 아님)"]}


# ---------- H08: 모호한 지시 + 규칙. 바이트 수가 가장 큰 파일 (글자 수 최대와 다름, 동률은 알파벳 순) ----------

SYLLABLES = "가나다라마바사아자차카타파하거너더러머버서어저처커터퍼허고노도로모보소오조초코토포호구누두루무부수우주추쿠투푸후"
EN_WORDS = ["meeting", "notes", "project", "budget", "review", "schedule", "update", "report", "client", "design", "plan", "team",
            "draft", "status", "action", "item", "follow", "agenda", "summary", "risk"]
H08_SIZES = [("ko", 5016), ("ko", 5016), ("ko", 4992), ("ko", 4380), ("ko", 3900), ("en", 3360), ("ko", 3150), ("ko", 2640), ("en", 2900), ("ko", 1800)]


def _ko_line(n: int, rng: random.Random) -> str:
    """정확히 n바이트(끝 줄바꿈 포함)인 한글 한 줄."""
    body = n - 1
    w = rng.randint(3, 6)
    b = body - (w - 1)                       # 단어 사이 공백 w-1개(각 1바이트)
    k, j = divmod(b, 3)                      # 한글 k자(3바이트) + 영숫자 j자(1바이트)
    assert k >= w
    cuts = sorted(rng.sample(range(1, k), w - 1))
    sizes = [b2 - a2 for a2, b2 in zip([0] + cuts, cuts + [k])]
    words = ["".join(rng.choice(SYLLABLES) for _ in range(sz)) for sz in sizes]
    words[-1] += "".join(str(rng.randint(0, 9)) for _ in range(j))
    line = " ".join(words)
    assert len((line + "\n").encode("utf-8")) == n
    return line


def _en_line(n: int, rng: random.Random) -> str:
    body = n - 1
    s = ""
    while len(s) < body + 12:
        s += rng.choice(EN_WORDS) + " "
    s = s[:body]
    if s.endswith(" "):
        s = s[:-1] + rng.choice("abcdefgh")
    assert len((s + "\n").encode("utf-8")) == n and "  " not in s and s == s.strip()
    return s


def _exact_bytes_file(kind: str, target: int, rng: random.Random) -> list[str]:
    line_fn = _ko_line if kind == "ko" else _en_line
    lines, remaining = [], target
    while remaining > 140:
        size = rng.randint(40, 70)
        lines.append(line_fn(size, rng))
        remaining -= size
    first = remaining // 2
    lines += [line_fn(first, rng), line_fn(remaining - first, rng)]
    return lines


def gen_h08(rng: random.Random, out: Path):
    kinds = H08_SIZES[:]
    rng.shuffle(kinds)
    texts, kind_of = {}, {}
    for i, (kind, size) in enumerate(kinds, 1):
        name = f"note_{i:02d}.txt"
        texts[name] = write_hard(out, name, _exact_bytes_file(kind, size, rng))
        kind_of[name] = kind
        assert len(texts[name].encode("utf-8")) == size, (name, size)
    nbytes = {n: len(t.encode("utf-8")) for n, t in texts.items()}
    nchars = {n: len(t) for n, t in texts.items()}
    top = max(nbytes.values())
    tied = sorted(n for n, b in nbytes.items() if b == top)
    assert len(tied) == 2 and top == 5016                                              # 바이트 최댓값 동률은 정확히 한 쌍
    assert sorted(nbytes.values())[-3] < top                                           # 3등은 최댓값보다 작다
    char_max = max(nchars, key=nchars.get)
    assert char_max not in tied and kind_of[char_max] == "en"                          # 글자 수 최대 파일은 바이트 최대 파일이 아니다
    assert sum(1 for c in nchars.values() if c == nchars[char_max]) == 1
    assert all(count_lines(t) >= 3 and t.endswith("\n") for t in texts.values())
    return {"file": tied[0], "bytes": top}, {"bytes_per_file": nbytes, "chars_per_file": nchars, "tied_files": tied, "char_max_file": char_max}


GENERATORS = {f"M{i:02d}": fn for i, fn in enumerate(
    [gen_m01, gen_m02, gen_m03, gen_m04, gen_m05, gen_m06, gen_m07, gen_m08, gen_m09, gen_m10,
     gen_m11, gen_m12, gen_m13, gen_m14, gen_m15, gen_m16, gen_m17], 1)}
GENERATORS.update({f"H{i:02d}": fn for i, fn in enumerate(
    [gen_h01, gen_h02, gen_h03, gen_h04, gen_h05, gen_h06, gen_h07, gen_h08], 1)})
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
