"""M05 정답 풀이 (timeout-and-retry3). 에이전트 없이 fixture를 읽어 직접 계산한다."""
from pathlib import Path


def solve(workdir: Path) -> None:
    lines = (workdir / "payments.log").read_text(encoding="utf-8").splitlines()
    n = sum(1 for ln in lines if "timeout" in ln and "retry=3" in ln)
    (workdir / "both.out").write_text(f"줄 수: {n}\n", encoding="utf-8", newline="\n")
