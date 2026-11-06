"""E02 정답 풀이 (find-file-with-word)."""
from pathlib import Path


def solve(workdir: Path) -> None:
    hits = [p.name for p in sorted(workdir.glob("*.txt")) if "kiwi" in p.read_text(encoding="utf-8")]
    assert len(hits) == 1, hits
    (workdir / "answer.txt").write_text(f"파일: {hits[0]}\n", encoding="utf-8", newline="\n")
