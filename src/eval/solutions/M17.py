"""M17 정답 풀이 (csv-to-json). 에이전트 없이 fixture를 읽어 직접 계산한다."""
from pathlib import Path


def solve(workdir: Path) -> None:
    import csv
    import json
    with (workdir / "scores.csv").open(encoding="utf-8", newline="") as f:
        rows = [{"name": r["name"], "score": r["score"]} for r in csv.DictReader(f)]
    (workdir / "scores.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
