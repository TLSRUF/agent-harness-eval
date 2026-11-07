"""H03 정답 풀이 (conflicting-docs-latest-wins). 에이전트 없이 작업 폴더의 파일을 읽어 직접 계산한다."""
from pathlib import Path


def solve(workdir: Path) -> None:
    import re
    docs = {}
    for p in sorted(workdir.glob("*.md")):
        text = p.read_text(encoding="utf-8")
        date = re.search(r"^Last updated: (\d{4}-\d{2}-\d{2})$", text, re.M).group(1)
        port = re.search(r"\b(\d{4,5})\b", re.sub(r"^Last updated: .*$", "", text, flags=re.M)).group(1)
        docs[p.name] = (date, port)
    latest = max(d for d, _ in docs.values())
    winner = min(n for n, (d, _) in docs.items() if d == latest)  # 날짜 동률이면 파일 이름이 알파벳으로 앞선 문서
    (workdir / "port.out").write_text(f"포트: {docs[winner][1]}\n", encoding="utf-8", newline="\n")
