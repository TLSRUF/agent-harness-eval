"""실행 결과 스냅샷: 임시 작업 폴더가 지워지기 전에 과제의 outputs 파일과 내용이 바뀐 입력 파일을 저장한다.

저장된 스냅샷은 모델을 다시 호출하지 않고 채점을 다시 하는 데 쓴다 (src/eval/regrade.py).
- 저장 위치: results/raw/<실행 로그 파일명 줄기>_final/<작업 폴더 기준 상대 경로>  (results/raw는 .gitignore 대상)
- 상한: 파일당 1MB, 실행당 5MB. 넘으면 저장하지 않고 snapshot 이벤트의 skipped에 기록한다.
- 삭제된 입력 파일은 deleted에, 없는 출력 파일은 missing_outputs에 기록한다 (파일로는 표현할 수 없으므로).
"""
from __future__ import annotations

import shutil
from pathlib import Path, PurePosixPath
from typing import Any

MAX_FILE_BYTES = 1_000_000   # 파일당 1MB
MAX_RUN_BYTES = 5_000_000    # 실행당 5MB


def _safe_rel(rel: str) -> bool:
    """작업 폴더 안의 상대 경로인지 (절대 경로, .., 드라이브 문자 거부)."""
    if not rel or "\x00" in rel:
        return False
    p = PurePosixPath(rel.replace("\\", "/"))
    return not p.is_absolute() and ".." not in p.parts and not (len(rel) > 1 and rel[1] == ":")


def changed_inputs(workdir: Path, fixtures_dir: Path) -> tuple[list[str], list[str]]:
    """fixture에 있던 파일 중 (내용이 바뀐 것, 사라진 것)의 상대 경로 목록."""
    changed, deleted = [], []
    for src in sorted(p for p in Path(fixtures_dir).rglob("*") if p.is_file()):
        rel = src.relative_to(fixtures_dir).as_posix()
        dst = Path(workdir) / rel
        if not dst.is_file():
            deleted.append(rel)
        elif dst.read_bytes() != src.read_bytes():
            changed.append(rel)
    return changed, deleted


def take_snapshot(workdir: Path, fixtures_dir: Path | None, outputs: list[str] | None, dest: Path, *,
                  max_file: int = MAX_FILE_BYTES, max_run: int = MAX_RUN_BYTES) -> dict[str, Any]:
    """outputs와 바뀐 입력 파일을 dest 아래에 저장하고 기록(dict)을 반환한다. dest가 이미 있으면 지우고 새로 만든다."""
    workdir, dest = Path(workdir), Path(dest)
    outputs = list(outputs or [])
    changed, deleted = changed_inputs(workdir, fixtures_dir) if fixtures_dir is not None else ([], [])
    candidates: list[str] = []
    for rel in outputs + changed:
        if rel not in candidates:
            candidates.append(rel)
    if dest.exists():
        shutil.rmtree(dest)
    saved: list[dict] = []
    skipped: list[dict] = []
    missing: list[str] = []
    total = 0
    for rel in candidates:
        if not _safe_rel(rel):
            skipped.append({"path": rel, "bytes": None, "reason": "unsafe_path"})
            continue
        src = workdir / rel
        if not src.exists():
            if rel in outputs:
                missing.append(rel)
            continue
        if src.is_symlink() or not src.is_file():
            skipped.append({"path": rel, "bytes": None, "reason": "not_regular_file"})
            continue
        size = src.stat().st_size
        if size > max_file:
            skipped.append({"path": rel, "bytes": size, "reason": "file_over_limit"})
            continue
        if total + size > max_run:
            skipped.append({"path": rel, "bytes": size, "reason": "run_over_limit"})
            continue
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, target)
        saved.append({"path": rel, "bytes": size})
        total += size
    return {"dir": dest.as_posix() if saved else None, "saved": saved, "skipped": skipped, "deleted": deleted,
            "missing_outputs": missing, "total_bytes": total, "max_file_bytes": max_file, "max_run_bytes": max_run}


def restore_workdir(fixtures_dir: Path, snapshot_dir: Path | None, record: dict, target: Path) -> Path:
    """채점을 다시 하기 위한 작업 폴더를 복원한다: fixture 복사 -> 삭제된 입력 제거 -> 저장된 파일 덮어쓰기."""
    target = Path(target)
    shutil.copytree(fixtures_dir, target, dirs_exist_ok=True)
    for rel in record.get("deleted", []):
        if _safe_rel(rel):
            (target / rel).unlink(missing_ok=True)
    for item in record.get("saved", []):
        rel = item["path"]
        if _safe_rel(rel) and snapshot_dir is not None:
            dst = target / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(Path(snapshot_dir) / rel, dst)
    return target
