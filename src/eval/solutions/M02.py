"""M02 정답 풀이 (failed-test-lines). 에이전트 없이 fixture를 읽어 직접 계산한다."""
from pathlib import Path


def solve(workdir: Path) -> None:
    lines = (workdir / "ci.log").read_text(encoding="utf-8").splitlines()
    nums = [str(i) for i, ln in enumerate(lines, 1) if "FAILED" in ln]
    (workdir / "failed_lines.out").write_text("\n".join(nums) + "\n", encoding="utf-8", newline="\n")
