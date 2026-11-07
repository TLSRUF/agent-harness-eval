"""M09 정답 풀이 (longest-file). 에이전트 없이 fixture를 읽어 직접 계산한다."""
from pathlib import Path


def solve(workdir: Path) -> None:
    sizes = {p.name: len(p.read_text(encoding="utf-8").splitlines()) for p in workdir.glob("*.txt")}
    best = max(sizes, key=sizes.get)
    (workdir / "longest.out").write_text(f"가장 긴 파일: {best}\n", encoding="utf-8", newline="\n")
