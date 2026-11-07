"""H07 정답 풀이 (include-chain-final-timeout). 에이전트 없이 작업 폴더의 파일을 읽어 직접 계산한다."""
from pathlib import Path


def solve(workdir: Path) -> None:
    state = {}

    def run(name, stack=()):
        assert name not in stack
        for raw in (workdir / name).read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            key, _, value = (x.strip() for x in line.partition("="))
            if key == "include":
                run(value, stack + (name,))
            else:
                state[key] = value

    run("main.conf")
    (workdir / "timeout.out").write_text(f"timeout: {state['timeout']}\n", encoding="utf-8", newline="\n")
