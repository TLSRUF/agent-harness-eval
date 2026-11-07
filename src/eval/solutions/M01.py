"""M01 정답 풀이 (count-device-lines). 에이전트 없이 fixture를 읽어 직접 계산한다."""
from pathlib import Path


def solve(workdir: Path) -> None:
    n = sum(1 for ln in (workdir / "gateway.log").read_text(encoding="utf-8").splitlines() if "dev-017" in ln)
    (workdir / "result.txt").write_text(f"줄 수: {n}\n", encoding="utf-8", newline="\n")
