"""E01 정답 풀이 (count-error-lines)."""
from pathlib import Path


def solve(workdir: Path) -> None:
    text = (workdir / "app.log").read_text(encoding="utf-8")
    n = sum(1 for line in text.splitlines() if "ERROR" in line)
    (workdir / "result.txt").write_text(f"ERROR 줄 수: {n}\n", encoding="utf-8", newline="\n")
