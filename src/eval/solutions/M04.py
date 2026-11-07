"""M04 정답 풀이 (unique-build-id). 에이전트 없이 fixture를 읽어 직접 계산한다."""
from pathlib import Path


def solve(workdir: Path) -> None:
    import re
    from collections import Counter
    ids = Counter(re.findall(r"BUILD_ID=(\S+)", (workdir / "auth.log").read_text(encoding="utf-8")))
    once = [b for b, c in ids.items() if c == 1]
    assert len(once) == 1, once
    (workdir / "build.txt").write_text(f"빌드 ID: {once[0]}\n", encoding="utf-8", newline="\n")
