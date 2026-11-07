"""스냅샷(실행 결과 저장)과 재채점: 합성 스냅샷과 가짜 query로 확인한다. 모델은 호출하지 않는다."""
import asyncio
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from claude_agent_sdk import ResultMessage

from src.agent import runner_agent, snapshot
from src.agent.config import HarnessConfig
from src.agent.snapshot import MAX_FILE_BYTES, MAX_RUN_BYTES, restore_workdir, take_snapshot
from src.eval import loader, regrade

E01 = next(t for t in loader.load_all() if t.id == "E01")  # app.log 입력, result.txt 출력, 정답 "ERROR 줄 수: 4"


# ---------------- take_snapshot ----------------

def make_dirs(tmp_path, fixtures: dict[str, str], work: dict[str, str]):
    fx, wd = tmp_path / "fx", tmp_path / "wd"
    fx.mkdir()
    wd.mkdir()
    for name, text in fixtures.items():
        (fx / name).parent.mkdir(parents=True, exist_ok=True)
        (fx / name).write_bytes(text.encode("utf-8"))
    for name, text in work.items():
        (wd / name).parent.mkdir(parents=True, exist_ok=True)
        (wd / name).write_bytes(text.encode("utf-8"))
    return fx, wd


def test_limits_are_one_mb_per_file_and_five_mb_per_run():
    assert MAX_FILE_BYTES == 1_000_000 and MAX_RUN_BYTES == 5_000_000


def test_snapshot_saves_outputs_and_changed_inputs_only(tmp_path):
    fx, wd = make_dirs(tmp_path, {"a.txt": "A", "b.txt": "B", "c.txt": "C"},
                       {"a.txt": "A", "b.txt": "B changed", "out.txt": "result", "scratch.tmp": "x"})  # c.txt 삭제됨
    rec = take_snapshot(wd, fx, ["out.txt"], tmp_path / "snap")
    assert [s["path"] for s in rec["saved"]] == ["out.txt", "b.txt"]          # 출력 + 바뀐 입력. 안 바뀐 a.txt와 임의 파일은 저장 안 함
    assert rec["deleted"] == ["c.txt"] and rec["skipped"] == [] and rec["missing_outputs"] == []
    assert (tmp_path / "snap" / "out.txt").read_text(encoding="utf-8") == "result"
    assert (tmp_path / "snap" / "b.txt").read_text(encoding="utf-8") == "B changed"
    assert not (tmp_path / "snap" / "a.txt").exists() and not (tmp_path / "snap" / "scratch.tmp").exists()
    assert rec["dir"] == (tmp_path / "snap").as_posix() and rec["total_bytes"] == len("result") + len("B changed")


def test_snapshot_records_missing_outputs_and_creates_no_dir_when_nothing_saved(tmp_path):
    fx, wd = make_dirs(tmp_path, {"a.txt": "A"}, {"a.txt": "A"})
    rec = take_snapshot(wd, fx, ["out.txt"], tmp_path / "snap")
    assert rec["saved"] == [] and rec["missing_outputs"] == ["out.txt"] and rec["dir"] is None
    assert not (tmp_path / "snap").exists()


def test_snapshot_file_over_limit_is_not_saved_and_recorded(tmp_path):
    fx, wd = make_dirs(tmp_path, {"a.txt": "A"}, {"a.txt": "A", "big.out": "x" * 11, "small.out": "ok"})
    rec = take_snapshot(wd, fx, ["big.out", "small.out"], tmp_path / "snap", max_file=10)
    assert [s["path"] for s in rec["saved"]] == ["small.out"]
    assert rec["skipped"] == [{"path": "big.out", "bytes": 11, "reason": "file_over_limit"}]
    assert not (tmp_path / "snap" / "big.out").exists()


def test_snapshot_run_total_limit(tmp_path):
    fx, wd = make_dirs(tmp_path, {}, {"a.out": "x" * 6, "b.out": "y" * 6, "c.out": "z" * 3})
    rec = take_snapshot(wd, fx, ["a.out", "b.out", "c.out"], tmp_path / "snap", max_file=10, max_run=10)
    assert [s["path"] for s in rec["saved"]] == ["a.out", "c.out"]           # 6 + 3 = 9 <= 10, b(6)는 6+6 > 10이라 건너뜀
    assert [(s["path"], s["reason"]) for s in rec["skipped"]] == [("b.out", "run_over_limit")]
    assert rec["total_bytes"] == 9


def test_snapshot_exactly_at_limits_is_saved(tmp_path):
    fx, wd = make_dirs(tmp_path, {}, {"a.out": "x" * 10})
    rec = take_snapshot(wd, fx, ["a.out"], tmp_path / "snap", max_file=10, max_run=10)
    assert rec["saved"] == [{"path": "a.out", "bytes": 10}] and rec["skipped"] == []


def test_snapshot_rejects_unsafe_output_paths(tmp_path):
    fx, wd = make_dirs(tmp_path, {}, {"ok.out": "1"})
    (tmp_path / "outside.txt").write_text("secret", encoding="utf-8")
    rec = take_snapshot(wd, fx, ["../outside.txt", "C:/Windows/win.ini", "/etc/passwd", "ok.out"], tmp_path / "snap")
    assert [s["path"] for s in rec["saved"]] == ["ok.out"]
    assert {s["path"] for s in rec["skipped"]} == {"../outside.txt", "C:/Windows/win.ini", "/etc/passwd"}
    assert all(s["reason"] == "unsafe_path" for s in rec["skipped"])
    assert not (tmp_path / "outside.txt").parent.joinpath("snap", "outside.txt").exists()


def test_snapshot_replaces_stale_directory(tmp_path):
    fx, wd = make_dirs(tmp_path, {}, {"out.txt": "new"})
    (tmp_path / "snap").mkdir()
    (tmp_path / "snap" / "stale.txt").write_text("old", encoding="utf-8")
    take_snapshot(wd, fx, ["out.txt"], tmp_path / "snap")
    assert sorted(p.name for p in (tmp_path / "snap").iterdir()) == ["out.txt"]


def test_restore_workdir_roundtrip(tmp_path):
    fx, wd = make_dirs(tmp_path, {"a.txt": "A", "b.txt": "B", "c.txt": "C"}, {"a.txt": "A", "b.txt": "B2", "out.txt": "O"})
    rec = take_snapshot(wd, fx, ["out.txt"], tmp_path / "snap")
    back = restore_workdir(fx, tmp_path / "snap", rec, tmp_path / "restored")
    assert {p.name: p.read_bytes() for p in back.iterdir()} == {p.name: p.read_bytes() for p in wd.iterdir()}


# ---------------- 러너 연결 ----------------

def _fake_query(writes: dict[str, str]):
    async def q(prompt, options):
        for name, text in writes.items():
            (Path(options.cwd) / name).write_bytes(text.encode("utf-8"))
        yield ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False, num_turns=1,
                            session_id="s", total_cost_usd=0.0, usage={}, result="ok", terminal_reason="completed")
    return q


def test_runner_saves_snapshot_before_workdir_is_deleted(tmp_path, monkeypatch):
    raw = tmp_path / "rawdir"
    monkeypatch.setattr(runner_agent, "RAW_DIR", raw)
    monkeypatch.setattr(runner_agent, "query", _fake_query({"result.txt": "ERROR 줄 수: 4\n"}))
    log = tmp_path / "logs" / "demo_haiku_x_run1.jsonl"
    s = asyncio.run(runner_agent.run_task(E01.prompt, HarnessConfig(), log_path=log, task_id="E01",
                                          fixtures_dir=E01.fixture_dir, grader=loader.make_grader(E01), outputs=E01.outputs))
    assert s["graded"]["passed"] is True
    snap_dir = raw / "demo_haiku_x_run1_final"
    assert (snap_dir / "result.txt").read_text(encoding="utf-8") == "ERROR 줄 수: 4\n"
    assert not (snap_dir / "app.log").exists()                                     # 입력이 안 바뀌었으면 저장하지 않음
    events = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]
    assert [e["kind"] for e in events][-3:] == ["grade", "snapshot", "summary"]
    ev = next(e for e in events if e["kind"] == "snapshot")
    assert [x["path"] for x in ev["saved"]] == ["result.txt"] and ev["deleted"] == [] and ev["skipped"] == []
    # 같은 스냅샷으로 재채점하면 같은 판정
    res = regrade.regrade_runs([log], snapshot_root=raw)
    assert res[0].status == "regraded" and res[0].changed is False and res[0].new["failure_type"] == "pass"


def test_runner_records_skipped_files_in_jsonl_when_over_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(runner_agent, "RAW_DIR", tmp_path / "rawdir")
    monkeypatch.setattr(runner_agent, "query", _fake_query({"result.txt": "x" * 50}))
    monkeypatch.setattr(snapshot, "MAX_FILE_BYTES", 10)
    # take_snapshot의 기본값은 함수 정의 시점에 고정되므로 러너가 호출하는 함수를 한도 10으로 감싼다
    orig = runner_agent.take_snapshot
    monkeypatch.setattr(runner_agent, "take_snapshot", lambda *a, **k: orig(*a, max_file=10, **k))
    log = tmp_path / "r.jsonl"
    asyncio.run(runner_agent.run_task(E01.prompt, HarnessConfig(), log_path=log, task_id="E01",
                                      fixtures_dir=E01.fixture_dir, outputs=E01.outputs))
    ev = next(json.loads(x) for x in log.read_text(encoding="utf-8").splitlines() if '"kind": "snapshot"' in x)
    assert ev["saved"] == [] and [s["reason"] for s in ev["skipped"]] == ["file_over_limit"] and ev["dir"] is None
    assert not (tmp_path / "rawdir" / "r_final").exists()


def test_snapshot_dir_is_gitignored_and_never_committed():
    r = subprocess.run(["git", "check-ignore", "-q", "results/raw/anything_final/result.txt"], cwd=loader.ROOT)
    assert r.returncode == 0  # 0 = 무시됨
    tracked = subprocess.run(["git", "ls-files", "results"], cwd=loader.ROOT, capture_output=True, text=True).stdout.split()
    assert all("_final" not in t for t in tracked)


# ---------------- 재채점 ----------------

GOOD = "ERROR 줄 수: 4\n"
PASS_V = {"passed": True, "failure_type": "pass", "reason": ""}


def synth(tmp_path, name, *, task_id="E01", files=None, old=PASS_V, deleted=(), skipped=(), event=True, snap_error=None):
    """합성 실행 로그와 스냅샷 폴더를 만든다."""
    raw = tmp_path / "raw"
    raw.mkdir(exist_ok=True)
    log = raw / f"{name}.jsonl"
    events = [{"kind": "config", "task_id": task_id, "config": {}}]
    if old is not None:
        events.append({"kind": "grade", "graded": old})
    if event:
        saved = []
        for rel, text in (files or {}).items():
            p = raw / f"{name}_final" / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(text.encode("utf-8"))
            saved.append({"path": rel, "bytes": len(text.encode("utf-8"))})
        ev = {"kind": "snapshot", "dir": None, "saved": saved, "skipped": list(skipped), "deleted": list(deleted), "missing_outputs": []}
        if snap_error:
            ev = {"kind": "snapshot", "error": snap_error}
        events.append(ev)
    events.append({"kind": "summary", "graded": old})
    log.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in events) + "\n", encoding="utf-8")
    return log


def test_regrade_pass_and_fail_unchanged(tmp_path):
    ok = synth(tmp_path, "ok", files={"result.txt": GOOD})
    bad = synth(tmp_path, "bad", files={"result.txt": "ERROR 줄 수: 5\n"}, old={"passed": False, "failure_type": "wrong_value"})
    res = {Path(r.path).stem: r for r in regrade.regrade_runs([ok, bad], snapshot_root=tmp_path / "raw")}
    assert res["ok"].new["failure_type"] == "pass" and res["ok"].changed is False
    assert res["bad"].new["failure_type"] == "wrong_value" and res["bad"].changed is False
    out = regrade.format_report(list(res.values()))
    assert "판정 변경 0건" in out and "기존 판정과 새 판정이 다른 실행이 없다" in out


def test_regrade_detects_changed_verdicts(tmp_path):
    cases = {
        "pass_to_fail": dict(files={"result.txt": "ERROR 줄 수: 5\n"}, old=PASS_V),                       # 예전 채점기는 통과시켰다
        "fail_to_pass": dict(files={"result.txt": GOOD}, old={"passed": False, "failure_type": "wrong_value"}),
        "type_only": dict(files={"result.txt": "ERROR 줄 수: 4줄\n"}, old={"passed": False, "failure_type": "wrong_value"}),  # 새 채점기는 format_error
        "input_deleted": dict(files={"result.txt": GOOD}, deleted=["app.log"], old=PASS_V),               # 입력 삭제는 unexpected_change
        "input_changed": dict(files={"result.txt": GOOD, "app.log": "tampered\n"}, old=PASS_V),
    }
    logs = [synth(tmp_path, n, **kw) for n, kw in cases.items()]
    res = {Path(r.path).stem: r for r in regrade.regrade_runs(logs, snapshot_root=tmp_path / "raw")}
    assert all(r.changed for r in res.values()), {k: (v.old, v.new) for k, v in res.items()}
    assert res["pass_to_fail"].new["failure_type"] == "wrong_value"
    assert res["fail_to_pass"].new["failure_type"] == "pass"
    assert res["type_only"].new["failure_type"] == "format_error"
    assert res["input_deleted"].new["failure_type"] == "unexpected_change"
    assert res["input_changed"].new["failure_type"] == "unexpected_change"
    out = regrade.format_report(list(res.values()))
    assert "판정 변경 5건" in out and "| pass_to_fail.jsonl | E01 | 통과(pass) | 실패(wrong_value) |" in out
    assert "| fail_to_pass.jsonl | E01 | 실패(wrong_value) | 통과(pass) |" in out


def test_regrade_old_verdict_without_failure_type_compares_pass_flag_only(tmp_path):
    """Day 3~4 시절 로그처럼 passed만 있는 기존 판정은 통과 여부만 비교한다."""
    same = synth(tmp_path, "legacy_same", files={"result.txt": GOOD}, old={"passed": True})
    diff = synth(tmp_path, "legacy_diff", files={"result.txt": "ERROR 줄 수: 9\n"}, old={"passed": True})
    res = {Path(r.path).stem: r for r in regrade.regrade_runs([same, diff], snapshot_root=tmp_path / "raw")}
    assert res["legacy_same"].changed is False and res["legacy_diff"].changed is True


def test_regrade_skips_runs_without_usable_snapshot_and_says_why(tmp_path):
    no_event = synth(tmp_path, "old_run", files=None, event=False)
    unknown = synth(tmp_path, "unk", task_id="ZZ99", files={"result.txt": GOOD})
    incomplete = synth(tmp_path, "inc", files={"result.txt": GOOD},
                       skipped=[{"path": "big.out", "bytes": 9, "reason": "file_over_limit"}])
    err = synth(tmp_path, "err", snap_error="OSError: disk full")
    gone = synth(tmp_path, "gone", files={"result.txt": GOOD})
    shutil.rmtree(tmp_path / "raw" / "gone_final")
    ok = synth(tmp_path, "ok", files={"result.txt": GOOD})
    res = {Path(r.path).stem: r for r in regrade.regrade_runs([no_event, unknown, incomplete, err, gone, ok], snapshot_root=tmp_path / "raw")}
    assert res["ok"].status == "regraded"
    assert all(res[k].status == "skipped" for k in ("old_run", "unk", "inc", "err", "gone"))
    assert "스냅샷 없음" in res["old_run"].reason and "과제 정의 없음" in res["unk"].reason
    assert "스냅샷 불완전" in res["inc"].reason and "스냅샷 오류" in res["err"].reason and "스냅샷 폴더 없음" in res["gone"].reason
    out = regrade.format_report(list(res.values()))
    assert "건너뜀 5건" in out and "- old_run.jsonl: 스냅샷 없음" in out


def test_regrade_no_output_in_snapshot_means_missing_output(tmp_path):
    """에이전트가 출력 파일을 만들지 않은 실행: 저장된 파일 없음 -> missing_output으로 재채점."""
    log = synth(tmp_path, "nofile", files={}, old={"passed": False, "failure_type": "missing_output"})
    r = regrade.regrade_runs([log], snapshot_root=tmp_path / "raw")[0]
    assert r.status == "regraded" and r.new["failure_type"] == "missing_output" and r.changed is False


def test_regrade_run_without_baseline_is_listed_but_not_counted_as_changed(tmp_path):
    log = synth(tmp_path, "nobase", files={"result.txt": GOOD}, old=None)
    r = regrade.regrade_runs([log], snapshot_root=tmp_path / "raw")[0]
    assert r.no_baseline and not r.changed and r.new["passed"] is True
    out = regrade.format_report([r])
    assert "기존 판정 기록 없음 1건" in out and "| nobase.jsonl | E01 | 기록 없음 | 통과(pass) |" in out


def test_regrade_grader_exception_is_skipped_with_reason(tmp_path, monkeypatch):
    log = synth(tmp_path, "boom", files={"result.txt": GOOD})
    def broken(task):
        def g(wd):
            raise RuntimeError("grader bug")
        return g
    monkeypatch.setattr(loader, "resolve_grader", broken)
    r = regrade.regrade_runs([log], snapshot_root=tmp_path / "raw")[0]
    assert r.status == "skipped" and "채점 중 예외" in r.reason and "grader bug" in r.reason


def test_regrade_cli_prints_table_and_does_not_touch_repo_files(tmp_path, capsys):
    synth(tmp_path, "a_ok", files={"result.txt": GOOD})
    synth(tmp_path, "b_changed", files={"result.txt": "ERROR 줄 수: 5\n"})
    synth(tmp_path, "c_nosnap", files=None, event=False)
    before = {p: p.stat().st_mtime for p in (loader.ROOT / "fixtures" / "E01").iterdir()}
    regrade.main([str(tmp_path / "raw" / "*.jsonl"), "--snapshot-root", str(tmp_path / "raw")])
    out = capsys.readouterr().out
    assert "재채점 2건 (판정 변경 1건" in out and "건너뜀 1건" in out
    assert "| b_changed.jsonl | E01 | 통과(pass) | 실패(wrong_value) |" in out and "- c_nosnap.jsonl: 스냅샷 없음" in out
    assert before == {p: p.stat().st_mtime for p in (loader.ROOT / "fixtures" / "E01").iterdir()}


def test_regrade_never_calls_the_model():
    src = Path(regrade.__file__).read_text(encoding="utf-8")
    assert "claude_agent_sdk" not in src and "query(" not in src and "runner_agent" not in src


def test_regrade_on_existing_raw_logs_skips_them_all(capsys):
    """results/raw의 기존 로그(스냅샷 기능 이전)는 스냅샷이 없으므로 모두 건너뛴다. 로컬에 로그가 없으면 건너뛰는 테스트."""
    logs = sorted(Path(loader.ROOT / "results" / "raw").glob("*.jsonl"))
    if not logs:
        pytest.skip("results/raw에 로그가 없음")
    res = regrade.regrade_runs(logs, snapshot_root=loader.ROOT / "results" / "raw")
    legacy = [r for r in res if "_final" not in r.path]
    assert all(r.status == "skipped" for r in legacy)
