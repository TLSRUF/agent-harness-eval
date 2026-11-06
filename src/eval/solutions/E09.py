"""E09 정답 풀이 (sort-names)."""
from pathlib import Path


def solve(workdir: Path) -> None:
    names = (workdir / "names.txt").read_text(encoding="utf-8").split()
    (workdir / "sorted_names.txt").write_text("\n".join(sorted(names)) + "\n", encoding="utf-8", newline="\n")
