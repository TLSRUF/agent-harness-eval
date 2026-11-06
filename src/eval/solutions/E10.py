"""E10 정답 풀이 (compare-word-counts)."""
from pathlib import Path


def solve(workdir: Path) -> None:
    counts = {n: len((workdir / n).read_text(encoding="utf-8").split()) for n in ("draft1.txt", "draft2.txt")}
    best = max(counts, key=counts.get)
    (workdir / "more.txt").write_text(f"더 긴 파일: {best}\n", encoding="utf-8")
