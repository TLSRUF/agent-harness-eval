"""H06 정답 풀이 (cross-reference-most-orders). 에이전트 없이 작업 폴더의 파일을 읽어 직접 계산한다."""
from pathlib import Path


def solve(workdir: Path) -> None:
    import csv
    from collections import Counter
    with (workdir / "customers.csv").open(encoding="utf-8", newline="") as f:
        names = {r["id"]: r["name"] for r in csv.DictReader(f)}
    with (workdir / "orders.csv").open(encoding="utf-8", newline="") as f:
        counts = Counter(r["customer_id"] for r in csv.DictReader(f) if r["customer_id"] in names)
    top_id = counts.most_common(1)[0][0]
    (workdir / "top_customer.out").write_text(f"고객: {names[top_id]}\n", encoding="utf-8", newline="\n")
