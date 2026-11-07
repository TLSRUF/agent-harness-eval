"""H01 정답 풀이 (top3-by-word-count). 에이전트 없이 작업 폴더의 파일을 읽어 직접 계산한다."""
from pathlib import Path


def solve(workdir: Path) -> None:
    words = {p.name: len(p.read_text(encoding="utf-8").split()) for p in workdir.glob("*.log")}
    top = sorted(words, key=lambda n: -words[n])[:3]
    (workdir / "top_words.out").write_text("\n".join(f"{n}: {words[n]}" for n in top) + "\n", encoding="utf-8", newline="\n")
