"""M03 정답 풀이 (first-error-line). 에이전트 없이 fixture를 읽어 직접 계산한다."""
from pathlib import Path


def solve(workdir: Path) -> None:
    lines = (workdir / "orders.log").read_text(encoding="utf-8").splitlines()
    first = next(i for i, ln in enumerate(lines, 1) if "E4021" in ln)
    (workdir / "first_line.txt").write_text(f"줄 번호: {first}\n", encoding="utf-8", newline="\n")
