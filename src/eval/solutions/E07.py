"""E07 정답 풀이 (list-txt-files)."""
from pathlib import Path


def solve(workdir: Path) -> None:
    names = sorted(p.name for p in workdir.iterdir() if p.is_file() and p.name.endswith(".txt"))
    (workdir / "txt_files.list").write_text("\n".join(names) + "\n", encoding="utf-8")
