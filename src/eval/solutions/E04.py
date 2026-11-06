"""E04 정답 풀이 (read-config-port)."""
from pathlib import Path


def solve(workdir: Path) -> None:
    for line in (workdir / "server.conf").read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("port"):
            port = line.split("=", 1)[1].strip()
    (workdir / "port.txt").write_text(f"포트: {port}\n", encoding="utf-8", newline="\n")
