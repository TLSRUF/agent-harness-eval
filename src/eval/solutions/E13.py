"""E13 정답 풀이 (warn-lines-copy)."""
from pathlib import Path


def solve(workdir: Path) -> None:
    lines = (workdir / "app.log").read_text(encoding="utf-8").splitlines()
    warn = [ln for ln in lines if "WARN" in ln]
    (workdir / "warn.txt").write_text("\n".join(warn) + "\n", encoding="utf-8", newline="\n")
