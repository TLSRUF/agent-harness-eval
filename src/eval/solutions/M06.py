"""M06 정답 풀이 (files-with-cache-ttl). 에이전트 없이 fixture를 읽어 직접 계산한다."""
from pathlib import Path


def solve(workdir: Path) -> None:
    names = sorted(p.name for p in workdir.glob("*.conf") if "cache_ttl" in p.read_text(encoding="utf-8"))
    (workdir / "cache_files.out").write_text("\n".join(names) + "\n", encoding="utf-8", newline="\n")
