"""E08 정답 풀이 (find-line-number)."""
from pathlib import Path


def solve(workdir: Path) -> None:
    lines = (workdir / "notes.txt").read_text(encoding="utf-8").splitlines()
    nums = [i for i, ln in enumerate(lines, 1) if "TODO" in ln]
    assert len(nums) == 1, nums
    (workdir / "line.txt").write_text(f"줄 번호: {nums[0]}\n", encoding="utf-8", newline="\n")
