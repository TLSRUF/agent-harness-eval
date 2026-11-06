"""E15 정답 풀이 (replace-word-two-files)."""
from pathlib import Path


def solve(workdir: Path) -> None:
    for name in ("memo1.txt", "memo2.txt"):
        p = workdir / name
        p.write_bytes(p.read_bytes().replace(b"Cat", b"Dog"))  # 바이트 단위로 바꿔 줄바꿈 형식을 보존
