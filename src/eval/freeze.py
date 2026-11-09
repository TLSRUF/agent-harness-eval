"""평가셋 동결: 과제 JSON, fixture, 채점 함수, 정답 풀이의 sha256과 도구 정의 v1, HARNESS_ENV, config 기본값의 해시를 MANIFEST.json에 기록하고 검증한다.

  python -m src.eval.freeze --write    # MANIFEST.json 최초 생성 (이미 있으면 거부, 동결을 다시 하려면 사용자 결정 후 파일을 직접 지운다)
  python -m src.eval.freeze --verify   # 현재 파일이 MANIFEST.json과 같은지 확인 (다르면 종료 코드 1)

코드/JSON 파일은 줄바꿈 변환(CRLF)만 무시하고 해시한다. fixture는 바이트 그대로 해시한다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "MANIFEST.json"
SCHEMA = 1
TASK_ID = re.compile(r"^[EMH]\d{2}$")


def sha256_file(path: Path, *, normalize_newlines: bool) -> str:
    data = path.read_bytes()
    if normalize_newlines:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def _canonical_hash(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def frozen_paths(root: Path) -> dict[str, list[str]]:
    """동결 대상 파일(루트 기준 상대 경로, / 구분). 종류별 목록과 전체('all')."""
    def rel(p: Path) -> str:
        return p.relative_to(root).as_posix()

    tasks = sorted(rel(p) for p in (root / "src/eval/tasks").glob("*.json"))
    fixtures = sorted(rel(p) for d in (root / "fixtures").iterdir() if d.is_dir() and TASK_ID.match(d.name)
                      for p in d.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    graders = [p for p in ("src/eval/graders.py", "src/eval/graders_user.py") if (root / p).exists()]
    solutions = sorted(rel(p) for p in (root / "src/eval/solutions").glob("*.py") if p.name != "__init__.py")
    return {"tasks": tasks, "fixtures": fixtures, "graders": graders, "solutions": solutions,
            "all": tasks + fixtures + graders + solutions}


def tool_definitions_v1() -> dict:
    """베이스라인 도구 정의 v1: 서버 이름, 도구 이름, 기본 설명, 입력 스키마."""
    from src.agent import tools
    value = {"server_name": tools.SERVER_NAME, "tool_names": list(tools.TOOL_NAMES),
             "descriptions_default": tools.DESCRIPTIONS["default"], "schemas": tools.SCHEMAS}
    return {"sha256": _canonical_hash(value), "tool_names": value["tool_names"]}


def harness_env() -> dict:
    from src.agent import runner_agent
    value = dict(runner_agent.HARNESS_ENV)
    return {"value": value, "sha256": _canonical_hash(value)}


def config_defaults() -> dict:
    """config 기본값: 모델 상수, 시스템 프롬프트 v1, 기본 내장 도구, HarnessConfig() 기본 필드."""
    from src.agent import config
    value = {"DEFAULT_MODEL": config.DEFAULT_MODEL, "COMPARE_MODEL": config.COMPARE_MODEL, "PROMPT_v1": config.PROMPTS["v1"],
             "BUILTIN_TOOLS_DEFAULT": list(config.BUILTIN_TOOLS_DEFAULT), **config.HarnessConfig().to_dict()}
    return {"value": value, "sha256": _canonical_hash(value)}


def build_manifest(root: Path = ROOT) -> dict:
    paths = frozen_paths(root)
    section = lambda kind: {p: sha256_file(root / p, normalize_newlines=(kind != "fixtures")) for p in paths[kind]}  # noqa: E731
    return {"schema": SCHEMA, "frozen_on": date.today().isoformat(),
            "note": "평가셋 동결. 아래 파일이 바뀌면 tests/test_freeze.py가 실패한다. 코드/JSON은 CRLF 변환만 무시, fixture는 바이트 그대로.",
            "tasks": section("tasks"), "fixtures": section("fixtures"), "graders": section("graders"), "solutions": section("solutions"),
            "tool_definitions_v1": tool_definitions_v1(), "harness_env": harness_env(), "config_defaults": config_defaults()}


def write_manifest(root: Path = ROOT, path: Path = MANIFEST_PATH) -> dict:
    if path.exists():
        raise FileExistsError(f"{path.name}가 이미 있다. 동결은 한 번만 한다. 다시 하려면 사용자 결정 후 파일을 직접 지운다.")
    m = build_manifest(root)
    path.write_text(json.dumps(m, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return m


def verify(root: Path = ROOT, manifest: dict | None = None) -> list[str]:
    """동결 위반 목록(빈 목록이면 일치). 변경, 없음(삭제), 추가를 모두 잡는다."""
    if manifest is None:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    problems: list[str] = []
    paths = frozen_paths(root)
    for kind in ("tasks", "fixtures", "graders", "solutions"):
        frozen = manifest[kind]
        for p, h in frozen.items():
            f = root / p
            if not f.exists():
                problems.append(f"없음: {p} ({kind})")
            elif sha256_file(f, normalize_newlines=(kind != "fixtures")) != h:
                problems.append(f"변경: {p} ({kind})")
        for p in paths[kind]:
            if p not in frozen:
                problems.append(f"추가: {p} ({kind}, 동결 목록에 없는 새 파일)")
    if tool_definitions_v1()["sha256"] != manifest["tool_definitions_v1"]["sha256"]:
        problems.append("변경: 도구 정의 v1 (이름, 설명, 입력 스키마)")
    if harness_env()["sha256"] != manifest["harness_env"]["sha256"]:
        problems.append("변경: HARNESS_ENV")
    if config_defaults()["sha256"] != manifest["config_defaults"]["sha256"]:
        problems.append("변경: config 기본값")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="평가셋 동결 매니페스트")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", action="store_true")
    g.add_argument("--verify", action="store_true")
    a = ap.parse_args(argv)
    if a.write:
        m = write_manifest()
        print(f"MANIFEST.json 작성: 과제 {len(m['tasks'])}, fixture 파일 {len(m['fixtures'])}, 채점 파일 {len(m['graders'])}, 정답 풀이 {len(m['solutions'])}")
        return 0
    probs = verify()
    print("동결 일치" if not probs else "\n".join(probs))
    return 1 if probs else 0


if __name__ == "__main__":
    sys.exit(main())
