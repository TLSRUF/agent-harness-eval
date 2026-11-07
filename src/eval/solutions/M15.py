"""M15 정답 풀이 (delete-comment-lines). 에이전트 없이 fixture를 읽어 직접 계산한다."""
from pathlib import Path


def solve(workdir: Path) -> None:
    p = workdir / "legacy.conf"
    keep = [ln for ln in p.read_text(encoding="utf-8").splitlines() if not ln.startswith("#")]
    p.write_text("\n".join(keep) + "\n", encoding="utf-8", newline="\n")
