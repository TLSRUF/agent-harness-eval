"""M13 정답 풀이 (top3-by-price). 에이전트 없이 fixture를 읽어 직접 계산한다."""
from pathlib import Path


def solve(workdir: Path) -> None:
    import csv
    with (workdir / "products.csv").open(encoding="utf-8", newline="") as f:
        rows = sorted(csv.DictReader(f), key=lambda r: int(r["price"]), reverse=True)
    (workdir / "top3.out").write_text("\n".join(r["product"] for r in rows[:3]) + "\n", encoding="utf-8", newline="\n")
