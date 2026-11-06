"""E05 정답 풀이 (edit-config-value)."""
from pathlib import Path


def solve(workdir: Path) -> None:
    p = workdir / "settings.ini"
    lines = p.read_text(encoding="utf-8").splitlines()
    out = ["debug = true" if ln.strip().startswith("debug") else ln for ln in lines]
    p.write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")
