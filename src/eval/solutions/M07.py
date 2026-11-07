"""M07 정답 풀이 (total-deadline-lines). 에이전트 없이 fixture를 읽어 직접 계산한다."""
from pathlib import Path


def solve(workdir: Path) -> None:
    n = 0
    for p in sorted(workdir.glob("*.md")):
        n += sum(1 for ln in p.read_text(encoding="utf-8").splitlines() if "deadline" in ln)
    (workdir / "total.out").write_text(f"줄 수: {n}\n", encoding="utf-8", newline="\n")
