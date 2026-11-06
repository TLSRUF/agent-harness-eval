"""E11 정답 풀이 (create-greeting-file)."""
from pathlib import Path


def solve(workdir: Path) -> None:
    (workdir / "greeting.txt").write_text("안녕하세요, 하네스!\n", encoding="utf-8", newline="\n")
