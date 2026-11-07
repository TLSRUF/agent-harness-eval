"""M12 정답 풀이 (count-per-team). 에이전트 없이 fixture를 읽어 직접 계산한다."""
from pathlib import Path


def solve(workdir: Path) -> None:
    import csv
    from collections import Counter
    with (workdir / "members.csv").open(encoding="utf-8", newline="") as f:
        c = Counter(r["team"] for r in csv.DictReader(f))
    (workdir / "team_counts.out").write_text("\n".join(f"{t}: {c[t]}" for t in sorted(c)) + "\n", encoding="utf-8", newline="\n")
