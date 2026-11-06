"""E03 정답 풀이 (line-and-word-count)."""
from pathlib import Path


def solve(workdir: Path) -> None:
    text = (workdir / "text.txt").read_text(encoding="utf-8")
    (workdir / "stats.txt").write_text(f"줄 수: {len(text.splitlines())}, 단어 수: {len(text.split())}\n", encoding="utf-8", newline="\n")
