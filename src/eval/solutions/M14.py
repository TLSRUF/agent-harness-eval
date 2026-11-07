"""M14 정답 풀이 (edit-two-values). 에이전트 없이 fixture를 읽어 직접 계산한다."""
from pathlib import Path


def solve(workdir: Path) -> None:
    p = workdir / "service.ini"
    out = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        if ln.startswith("timeout"):
            ln = "timeout = 60"
        elif ln.startswith("retries"):
            ln = "retries = 5"
        out.append(ln)
    p.write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")
