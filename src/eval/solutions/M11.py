"""M11 정답 풀이 (sum-east-qty). 에이전트 없이 fixture를 읽어 직접 계산한다."""
from pathlib import Path


def solve(workdir: Path) -> None:
    import csv
    with (workdir / "orders.csv").open(encoding="utf-8", newline="") as f:
        total = sum(int(r["qty"]) for r in csv.DictReader(f) if r["region"] == "east")
    (workdir / "east_total.txt").write_text(f"합계: {total}\n", encoding="utf-8", newline="\n")
