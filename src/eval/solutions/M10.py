"""M10 정답 풀이 (files-with-many-words). 에이전트 없이 fixture를 읽어 직접 계산한다."""
from pathlib import Path


def solve(workdir: Path) -> None:
    names = sorted(p.name for p in workdir.glob("*.txt") if len(p.read_text(encoding="utf-8").split()) >= 20)
    (workdir / "big_files.out").write_text("\n".join(names) + "\n", encoding="utf-8", newline="\n")
