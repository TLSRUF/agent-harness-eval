"""H04 정답 풀이 (docs-with-wrong-line-claims). 에이전트 없이 작업 폴더의 파일을 읽어 직접 계산한다."""
from pathlib import Path


def solve(workdir: Path) -> None:
    wrong = []
    for p in sorted(workdir.glob("*.txt")):
        lines = p.read_text(encoding="utf-8").splitlines()
        claimed = int(lines[0].split(":")[1])
        if claimed != len(lines):  # 첫 줄도 센 실제 줄 수
            wrong.append(p.name)
    (workdir / "wrong_docs.out").write_text("\n".join(sorted(wrong)) + "\n", encoding="utf-8", newline="\n")
