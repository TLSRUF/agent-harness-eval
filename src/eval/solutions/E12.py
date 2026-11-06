"""E12 정답 풀이 (first-and-last-line)."""
from pathlib import Path


def solve(workdir: Path) -> None:
    lines = (workdir / "log.txt").read_text(encoding="utf-8").splitlines()
    (workdir / "first_last.txt").write_text(f"{lines[0]}\n{lines[-1]}\n", encoding="utf-8")
