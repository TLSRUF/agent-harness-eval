"""재채점: 저장된 실행 결과 스냅샷에 '현재' 채점 함수를 다시 적용한다. 모델을 호출하지 않는다.

사용: python -m src.eval.regrade "results/raw/*.jsonl" [--snapshot-root results/raw]

각 실행 로그(jsonl)에서 task_id, 기존 판정(grade 이벤트), 스냅샷 기록(snapshot 이벤트)을 읽고,
fixture 복사 -> 삭제된 입력 제거 -> 저장된 파일 덮어쓰기로 작업 폴더를 복원해 현재 채점 함수로 다시 채점한다.
기존 판정과 새 판정이 다른 실행을 표로 보여준다. 스냅샷이 없거나 불완전한 실행은 건너뛰고 이유를 알려준다.
"""
from __future__ import annotations

import argparse
import glob
import json
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from src.agent.snapshot import restore_workdir

from . import loader

DEFAULT_SNAPSHOT_ROOT = Path("results") / "raw"


@dataclass
class Regrade:
    path: str
    task_id: str | None
    status: str                      # "regraded" | "skipped"
    reason: str = ""
    old: dict | None = None
    new: dict | None = None
    changed: bool = False
    no_baseline: bool = False        # 기존 판정 기록이 없어 비교할 수 없음


def _read_events(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _old_verdict(events: list[dict]) -> dict | None:
    for ev in reversed(events):
        if ev.get("kind") == "grade" and isinstance(ev.get("graded"), dict):
            return ev["graded"]
    summ = next((e for e in reversed(events) if e.get("kind") == "summary"), None)
    if summ and isinstance(summ.get("graded"), dict):
        return summ["graded"]
    return None


def verdicts_differ(old: dict, new: dict) -> bool:
    if bool(old.get("passed")) != bool(new.get("passed")):
        return True
    return old.get("failure_type") is not None and new.get("failure_type") is not None and old["failure_type"] != new["failure_type"]


def regrade_one(path: Path, tasks: dict[str, loader.Task], snapshot_root: Path) -> Regrade:
    events = _read_events(path)
    cfg = next((e for e in events if e.get("kind") == "config"), None)
    if cfg is None or not cfg.get("task_id"):
        return Regrade(str(path), None, "skipped", "task_id를 알 수 없음(config 이벤트 없음)")
    tid = cfg["task_id"]
    task = tasks.get(tid)
    if task is None:
        return Regrade(str(path), tid, "skipped", f"과제 정의 없음(task_id={tid})")
    snap = next((e for e in events if e.get("kind") == "snapshot"), None)
    if snap is None:
        return Regrade(str(path), tid, "skipped", "스냅샷 없음(이 실행에는 snapshot 이벤트가 없음)")
    if snap.get("error"):
        return Regrade(str(path), tid, "skipped", f"스냅샷 오류: {snap['error']}")
    if snap.get("skipped"):
        return Regrade(str(path), tid, "skipped", f"스냅샷 불완전: 상한 초과 등으로 저장되지 않은 파일 {len(snap['skipped'])}개 "
                                                   f"({[s['path'] for s in snap['skipped']]})")
    snap_dir = Path(snapshot_root) / f"{path.stem}_final"
    if snap.get("saved") and not snap_dir.is_dir():
        return Regrade(str(path), tid, "skipped", f"스냅샷 폴더 없음({snap_dir.as_posix()})")
    grader = loader.resolve_grader(task)
    if grader is None:
        return Regrade(str(path), tid, "skipped", "채점기를 찾을 수 없음")
    tmp = Path(tempfile.mkdtemp(prefix="regrade_"))
    try:
        wd = restore_workdir(task.fixture_dir, snap_dir if snap.get("saved") else None, snap, tmp / "wd")
        try:
            new = grader(wd)
        except Exception as e:  # noqa: BLE001
            return Regrade(str(path), tid, "skipped", f"채점 중 예외: {type(e).__name__}: {e}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    old = _old_verdict(events)
    if old is None:
        return Regrade(str(path), tid, "regraded", old=None, new=new, no_baseline=True)
    return Regrade(str(path), tid, "regraded", old=old, new=new, changed=verdicts_differ(old, new))


def regrade_runs(paths, *, snapshot_root: Path = DEFAULT_SNAPSHOT_ROOT, tasks: dict[str, loader.Task] | None = None) -> list[Regrade]:
    if tasks is None:
        tasks = {t.id: t for t in loader.load_all() if not t.is_todo}
    return [regrade_one(Path(p), tasks, Path(snapshot_root)) for p in sorted(paths)]


def _fmt(v: dict | None) -> str:
    if v is None:
        return "기록 없음"
    ft = v.get("failure_type")
    return ("통과" if v.get("passed") else "실패") + (f"({ft})" if ft else "")


def format_report(results: list[Regrade]) -> str:
    done = [r for r in results if r.status == "regraded"]
    skipped = [r for r in results if r.status == "skipped"]
    changed = [r for r in done if r.changed]
    nobase = [r for r in done if r.no_baseline]
    out = [f"# 재채점 (모델 호출 없음)", "",
           f"실행 {len(results)}건: 재채점 {len(done)}건 (판정 변경 {len(changed)}건, 기존 판정 기록 없음 {len(nobase)}건), 건너뜀 {len(skipped)}건"]
    shown = changed + nobase
    out.append("")
    if shown:
        out += ["| 실행 | 과제 | 기존 판정 | 새 판정 |", "|---|---|---|---|"]
        out += [f"| {Path(r.path).name} | {r.task_id} | {_fmt(r.old)} | {_fmt(r.new)} |" for r in shown]
    else:
        out.append("기존 판정과 새 판정이 다른 실행이 없다." if done else "재채점한 실행이 없다.")
    if skipped:
        out += ["", "건너뜀:"]
        out += [f"- {Path(r.path).name}: {r.reason}" for r in skipped]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("patterns", nargs="+", help="실행 로그 jsonl 경로 또는 글롭")
    ap.add_argument("--snapshot-root", default=str(DEFAULT_SNAPSHOT_ROOT))
    a = ap.parse_args(argv)
    files = sorted({f for p in a.patterns for f in glob.glob(p)})
    print(format_report(regrade_runs(files, snapshot_root=Path(a.snapshot_root))))


if __name__ == "__main__":
    main()
