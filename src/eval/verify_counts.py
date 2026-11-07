"""fixture에서 정답을 다시 세는 독립 검증 스크립트.

fixtures/_gen의 생성기와 코드를 공유하지 않는다. 생성기가 '정한' 값(plants/<ID>.json의 answer)과
이 스크립트가 파일에서 '센' 값이 다르면 로더(검증 6번)가 실패한다.

세기 정의 (이 파일의 구현)
- 줄 수: 바이트 단위로 b"\\n" 개수를 센다 (마지막 줄이 줄바꿈 없이 끝나면 그 줄도 센다).
- 단어 수: 정규식 \\S+ 로 뽑은 덩어리 수 (= 공백으로 구분되는 덩어리).
- 줄 번호: 1부터. 줄은 "\\n"으로 나눈다.
"""
from __future__ import annotations

import csv
import re
from collections import Counter
from pathlib import Path

WORD_THRESHOLD = 20  # M10 프롬프트의 "20개 이상"


def _text(p: Path) -> str:
    return p.read_bytes().decode("utf-8")


def _lines(p: Path) -> list[str]:
    """줄 목록 (끝 줄바꿈 뒤의 빈 조각은 제외)."""
    parts = _text(p).split("\n")
    return parts[:-1] if parts and parts[-1] == "" else parts


def count_lines(p: Path) -> int:
    data = p.read_bytes()
    return data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)


def count_words(p: Path) -> int:
    return len(re.findall(r"\S+", _text(p)))


def count_bytes(p: Path) -> int:
    return len(p.read_bytes())


def _only(d: Path, name: str) -> Path:
    return d / name


# ---------- 과제별 카운터: fixture 폴더 -> 정답(plants의 answer와 같은 모양) ----------

def m01(d: Path):
    return {"count": sum(1 for ln in _lines(d / "gateway.log") if re.search(r"dev-017", ln))}


def m02(d: Path):
    return {"items": [str(i) for i, ln in enumerate(_lines(d / "ci.log"), 1) if re.search(r"\bFAILED\b", ln)]}


def m03(d: Path):
    for i, ln in enumerate(_lines(d / "orders.log"), 1):
        if re.search(r"code=E4021(?!\d)", ln):
            return {"line": i}
    raise AssertionError("E4021 not found")


def m04(d: Path):
    ids = Counter(re.findall(r"BUILD_ID=([0-9a-f]{8})", _text(d / "auth.log")))
    once = [b for b, c in ids.items() if c == 1]
    assert len(once) == 1, f"expected exactly one BUILD_ID that appears once, got {once}"
    return {"value": once[0]}


def m05(d: Path):
    n = sum(1 for ln in _lines(d / "payments.log") if re.search(r"\btimeout\b", ln) and re.search(r"\bretry=3(?!\d)", ln))
    return {"count": n}


def m06(d: Path):
    return {"items": sorted(p.name for p in d.glob("*.conf") if re.search(r"^cache_ttl\b", _text(p), re.M))}


def m07(d: Path):
    return {"count": sum(1 for p in sorted(d.glob("*.md")) for ln in _lines(p) if re.search(r"\bdeadline\b", ln))}


def m08(d: Path):
    hits = sorted(p.name for p in d.glob("*.conf") if re.search(r"^max_connections\s*=\s*500$", _text(p), re.M))
    assert len(hits) == 1, hits
    return {"file": hits[0]}


def m09(d: Path):
    sizes = {p.name: count_lines(p) for p in d.glob("*.txt")}
    top = max(sizes.values())
    winners = sorted(nm for nm, c in sizes.items() if c == top)
    assert len(winners) == 1, winners
    return {"file": winners[0]}


def m10(d: Path):
    return {"items": sorted(p.name for p in d.glob("*.txt") if count_words(p) >= WORD_THRESHOLD)}


def _rows(path: Path):
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def m11(d: Path):
    return {"sum": sum(int(r["qty"]) for r in _rows(d / "orders.csv") if r["region"] == "east")}


def m12(d: Path):
    c = Counter(r["team"] for r in _rows(d / "members.csv"))
    return {"items": [f"{t}: {c[t]}" for t in sorted(c)]}


def m13(d: Path):
    rows = sorted(_rows(d / "products.csv"), key=lambda r: int(r["price"]), reverse=True)
    prices = [int(r["price"]) for r in rows]
    assert len(set(prices)) == len(prices), "price ties"
    return {"items": [r["product"] for r in rows[:3]]}


COUNTERS = {f"M{i:02d}": fn for i, fn in enumerate([m01, m02, m03, m04, m05, m06, m07, m08, m09, m10, m11, m12, m13], 1)}

# ---------- Day 6: 어려운 과제 H01~H08 ----------

def h01(d: Path):
    words = {p.name: count_words(p) for p in sorted(d.glob("*.log"))}
    ranked = sorted(words, key=lambda n: -words[n])
    assert len(set(words.values())) == len(words), "word count ties"
    return {"items": [f"{n}: {words[n]}" for n in ranked[:3]]}


def h02(d: Path):
    return {"sum": sum(c for c in (count_lines(p) for p in sorted(d.glob("*.txt"))) if c >= 100)}


def h03(d: Path):
    docs = {}
    for p in sorted(d.glob("*.md")):
        text = _text(p)
        dates = re.findall(r"^Last updated: (\d{4}-\d{2}-\d{2})$", text, re.M)
        assert len(dates) == 1, (p.name, dates)
        ports = re.findall(r"\b(\d{4,5})\b", re.sub(r"^Last updated: .*$", "", text, flags=re.M))
        assert len(ports) == 1, (p.name, ports)
        docs[p.name] = (dates[0], int(ports[0]))
    latest = max(date for date, _ in docs.values())
    winner = sorted(n for n, (date, _) in docs.items() if date == latest)[0]   # 날짜 동률이면 파일 이름이 알파벳으로 앞선 문서
    return {"port": docs[winner][1]}


def h04(d: Path):
    wrong = []
    for p in sorted(d.glob("*.txt")):
        first = _lines(p)[0]
        m = re.fullmatch(r"# lines: (\d+)", first)
        assert m, (p.name, first)
        if int(m.group(1)) != count_lines(p):   # 첫 줄의 '# lines: N' 줄도 세는 줄에 포함
            wrong.append(p.name)
    return {"items": sorted(wrong)}


def h05(d: Path):
    out = {}
    for p in sorted(d.glob("*.conf")):
        hits = [i for i, ln in enumerate(_lines(p), 1) if ln == "endpoint = http://old.internal:8080"]
        assert len(hits) <= 1, (p.name, hits)
        if hits:
            out[p.name] = hits[0]
    return {"changed": out}


def h06(d: Path):
    cust = {r["id"]: r["name"] for r in _rows(d / "customers.csv")}
    freq = Counter(r["customer_id"] for r in _rows(d / "orders.csv") if r["customer_id"] in cust)   # 목록에 없는 id의 주문은 세지 않는다
    top = freq.most_common(2)
    assert len(top) == 2 and top[0][1] > top[1][1], top
    return {"name": cust[top[0][0]]}


def _run_conf(d: Path, name: str, state: dict, stack: tuple = ()):
    assert name not in stack, f"include cycle at {name}"
    for raw in _lines(d / name):
        line = raw.strip()
        if not line or line.startswith("#"):          # '#'으로 시작하는 줄(주석 처리된 include 포함)은 무시
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip()
        if key == "include":                          # 그 자리에서 처리하고 돌아온다
            _run_conf(d, val, state, stack + (name,))
        else:
            state[key] = val                          # 나중에 처리한 값이 이긴다


def h07(d: Path):
    state: dict = {}
    _run_conf(d, "main.conf", state)
    return {"timeout": int(state["timeout"])}


def h08(d: Path):
    sizes = {p.name: count_bytes(p) for p in sorted(d.glob("*.txt"))}
    top = max(sizes.values())
    tied = sorted(n for n, b in sizes.items() if b == top)      # 바이트 수가 같으면 파일 이름이 알파벳으로 앞선 파일
    return {"file": tied[0], "bytes": top}


COUNTERS.update({"H01": h01, "H02": h02, "H03": h03, "H04": h04, "H05": h05, "H06": h06, "H07": h07, "H08": h08})
