"""H05 정답 풀이 (bulk-endpoint-replace). 에이전트 없이 작업 폴더의 파일을 읽어 직접 계산한다."""
from pathlib import Path


def solve(workdir: Path) -> None:
    old, new = "endpoint = http://old.internal:8080", "endpoint = http://new.internal:9090"
    for p in sorted(workdir.glob("*.conf")):
        lines = p.read_text(encoding="utf-8").splitlines()
        p.write_text("\n".join(new if ln == old else ln for ln in lines) + "\n", encoding="utf-8", newline="\n")
