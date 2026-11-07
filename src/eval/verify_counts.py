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
