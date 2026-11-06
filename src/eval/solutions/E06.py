"""E06 정답 풀이 (sum-csv-column)."""
from pathlib import Path


def solve(workdir: Path) -> None:
    import csv
    with (workdir / "sales.csv").open(encoding="utf-8", newline="") as f:
        total = sum(int(r["qty"]) for r in csv.DictReader(f))
    (workdir / "total.txt").write_text(f"합계: {total}\n", encoding="utf-8")
