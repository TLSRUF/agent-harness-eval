"""H08 정답 풀이 (biggest-file-by-bytes). 에이전트 없이 작업 폴더의 파일을 읽어 직접 계산한다."""
from pathlib import Path


def solve(workdir: Path) -> None:
    sizes = {p.name: p.stat().st_size for p in workdir.glob("*.txt")}
    top = max(sizes.values())
    winner = min(n for n, b in sizes.items() if b == top)  # 크기가 같으면 파일 이름이 알파벳으로 앞선 파일
    (workdir / "biggest.out").write_text(f"파일: {winner}, 바이트: {top}\n", encoding="utf-8", newline="\n")
