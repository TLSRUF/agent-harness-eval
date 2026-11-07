"""M08 정답 풀이 (file-with-max-connections-500). 에이전트 없이 fixture를 읽어 직접 계산한다."""
from pathlib import Path


def solve(workdir: Path) -> None:
    names = [p.name for p in sorted(workdir.glob("*.conf")) if "max_connections = 500" in p.read_text(encoding="utf-8").splitlines()]
    assert len(names) == 1, names
    (workdir / "conn_file.out").write_text(f"파일: {names[0]}\n", encoding="utf-8", newline="\n")
