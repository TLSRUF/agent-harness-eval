"""M16 정답 풀이 (json-to-csv). 에이전트 없이 fixture를 읽어 직접 계산한다."""
from pathlib import Path


def solve(workdir: Path) -> None:
    import json
    people = json.loads((workdir / "people.json").read_text(encoding="utf-8"))
    cols = list(people[0].keys())
    rows = [",".join(cols)] + [",".join(str(p[c]) for c in cols) for p in people]
    (workdir / "people.csv").write_text("\n".join(rows) + "\n", encoding="utf-8", newline="\n")
