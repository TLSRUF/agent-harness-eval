"""E14 정답 풀이 (max-qty-product)."""
from pathlib import Path


def solve(workdir: Path) -> None:
    import csv
    with (workdir / "orders.csv").open(encoding="utf-8", newline="") as f:
        best = max(csv.DictReader(f), key=lambda r: int(r["qty"]))
    (workdir / "top.txt").write_text(f"제품: {best['product']}\n", encoding="utf-8", newline="\n")
