"""H02 정답 풀이 (sum-lines-of-big-files). 에이전트 없이 작업 폴더의 파일을 읽어 직접 계산한다."""
from pathlib import Path


def solve(workdir: Path) -> None:
    counts = [len(p.read_text(encoding="utf-8").splitlines()) for p in workdir.glob("*.txt")]
    total = sum(c for c in counts if c >= 100)
    (workdir / "total_lines.out").write_text(f"합계: {total}\n", encoding="utf-8", newline="\n")
