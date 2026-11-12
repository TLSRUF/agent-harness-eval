"""배치 러너(src/eval/batch.py) 테스트. 모델을 호출하지 않는 가짜 query로만 실행한다 (구현보다 먼저 작성)."""
import json
import re
from pathlib import Path

import pytest
from claude_agent_sdk import (
    ClaudeSDKError, RateLimitEvent, RateLimitInfo, ResultMessage, SystemMessage,
)

from src.agent import runner_agent
from src.agent.config import HarnessConfig
from src.agent.guard import ToolGuardError, allowed_tool_names
from src.eval import batch, loader

TASKS = {t.id: t for t in loader.load_all()}
ALLOWED = allowed_tool_names(HarnessConfig())


# ---------------- 가짜 query 도구 ----------------

def init_msg(tools=None):
    return SystemMessage(subtype="init", data={"tools": list(ALLOWED if tools is None else tools), "claude_code_version": "0.0.0-test"})


def rate_event(five=0.50, seven=0.30, status="allowed"):
    info = RateLimitInfo(status=status, rate_limit_type="five_hour", raw={"unifiedWindows": {"five_hour": {"utilization": five}, "seven_day": {"utilization": seven}}})
    return RateLimitEvent(rate_limit_info=info, uuid="u", session_id="s")


def result_msg(**kw):
    base = dict(subtype="success", duration_ms=10, duration_api_ms=5, is_error=False, num_turns=3, session_id="s", total_cost_usd=0.01,
                usage={"input_tokens": 100, "output_tokens": 20, "cache_read_input_tokens": 50, "cache_creation_input_tokens": 10},
                result="done", terminal_reason="completed")
    base.update(kw)
    return ResultMessage(**base)


class Fake:
    """script(prompt, options) -> (messages, exception_or_None). 모든 호출을 calls에 기록한다."""

    def __init__(self, script=None):
        self.calls = []
        self.script = script or (lambda prompt, options: ([init_msg(), rate_event(), result_msg()], None))

    def __call__(self, prompt, options):
        self.calls.append((prompt, options))
        messages, exc = self.script(prompt, options)

        async def gen():
            for m in messages:
                yield m
            if exc is not None:
                raise exc
        return gen()

    def task_calls(self):
        return [(p, o) for p, o in self.calls if o.max_turns != 1 or o.tools != []]

    def probe_calls(self):
        return [(p, o) for p, o in self.calls if o.max_turns == 1 and o.tools == []]


def prompt_to_task(prompt):
    return next(t.id for t in TASKS.values() if t.prompt == prompt)


@pytest.fixture()
def env(tmp_path, monkeypatch):
    out, res = tmp_path / "raw", tmp_path / "results"
    out.mkdir(), res.mkdir()

    def no_input(_):
        raise AssertionError("확인 입력이 호출되면 안 된다")

    class E:
        pass

    e = E()
    e.out, e.res, e.fake = out, res, Fake()
    e.deps = dict(verify_freeze=lambda: [], preflight=None, input_fn=no_input, git_status=lambda: [], cli_version=lambda: "9.9.9-test")

    async def ok_preflight(cfg):
        return {"servers": ["t"], "mcp_tool_tokens": 0}
    e.deps["preflight"] = ok_preflight

    def run(*args, fake=None, **dep_overrides):
        f = fake or e.fake
        e.fake = f
        monkeypatch.setattr(runner_agent, "query", f)
        argv = ["--experiment", "day7check", "--out-dir", str(out), "--results-dir", str(res), *args]
        d = batch.Deps(**{**e.deps, **dep_overrides})
        return batch.main(argv, deps=d)

    e.run = run
    return e


def events(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()]


def run_log(env, task="E01", n=1):
    return env.out / f"day7check_haiku_default_{task}_run{n}.jsonl"


def summary_records(env):
    return events(env.out / "day7check_haiku_default_summary.jsonl")


# ---------------- 이름, 인자 ----------------

def test_log_name_and_argument_rules(env, capsys):
    assert batch.log_name("day7check", "haiku", "default", "H01", 2) == "day7check_haiku_default_H01_run2"
    a = batch.parse_args(["--experiment", "baseline", "--tasks", "E01,H02", "--runs", "3"])
    assert a.runs == 3 and a.config == "default" and a.probe is True and a.yes is False and a.five_hour_stop is None
    assert batch.DEFAULT_FIVE_HOUR_STOP is None                               # 임계 기본값은 비워 둔다
    assert env.run("--tasks", "E01", "--runs", "1", "--yes", "--no-probe", "--config", "nope") == batch.EXIT_REFUSED   # 모르는 설정 이름
    bad = batch.parse_args(["--experiment", "a_b", "--tasks", "E01"])
    with pytest.raises(ValueError):
        batch.validate_names(bad)                                             # 이름에 밑줄이 있으면 파일명을 해석할 수 없다
    assert env.fake.calls == []


def test_task_selection_by_ids_difficulty_and_all(env):
    ids = lambda *a: [t.id for t in batch.select_tasks(batch.parse_args(["--experiment", "x", *a]), list(TASKS.values()))]  # noqa: E731
    assert ids("--tasks", "H02,E01") == ["E01", "H02"]
    assert len(ids("--difficulty", "hard")) == 8 and len(ids("--difficulty", "easy")) == 15
    assert len(ids("--all")) == 40
    with pytest.raises(SystemExit):
        batch.parse_args(["--experiment", "x"])                               # 선택 인자가 없으면 거부
    with pytest.raises(ValueError):
        ids("--tasks", "E01,ZZ9")                                             # 없는 과제 ID


# ---------------- 완료/중단 분류 ----------------

def S(**kw):
    base = dict(task_id="E01", subtype="success", is_error=False, exception=None, result="done", rate_limit_events=[])
    base.update(kw)
    return base


def test_classify_summary_rules():
    assert batch.classify_summary(S())[0] == "complete"
    # 결과와 예외가 둘 다 와도 결과(subtype)가 있으면 완료: error_max_turns 뒤 CLI가 비정상 종료한 경우
    assert batch.classify_summary(S(subtype="error_max_turns", is_error=True, exception="ClaudeSDKError: exit 1"))[0] == "complete"
    assert batch.classify_summary(S(subtype="error_during_execution", is_error=True, result="some failure"))[0] == "complete"
    st, why = batch.classify_summary(S(exception="ToolGuardError: unexpected tools in init message: ['Bash']", subtype=None, result=None))
    assert st == "aborted" and "ToolGuardError" in why
    st, why = batch.classify_summary(S(exception="ClaudeSDKError: boom", subtype=None, result=None))
    assert st == "aborted" and "API" in why
    st, why = batch.classify_summary(S(is_error=True, result="You've hit your usage limit"))
    assert st == "aborted" and "한도" in why
    assert batch.classify_summary(S(subtype=None, result=None, rate_limit_events=[{"status": "rejected"}], exception="x"))[0] == "aborted"


def write_log(path, events_, truncate_tail=False):
    text = "\n".join(json.dumps(e, ensure_ascii=False) for e in events_) + "\n"
    if truncate_tail:
        text += '{"kind": "message", "mess'
    Path(path).write_text(text, encoding="utf-8")


def test_classify_log_states(tmp_path):
    p = tmp_path / "day7check_haiku_default_E01_run1.jsonl"
    assert batch.classify_log(p) == "missing"
    write_log(p, [{"kind": "config"}, {"kind": "message"}])
    assert batch.classify_log(p) == "incomplete"
    write_log(p, [{"kind": "config"}, {"kind": "message"}], truncate_tail=True)      # 강제 종료로 마지막 줄이 잘린 경우
    assert batch.classify_log(p) == "incomplete"
    write_log(p, [{"kind": "config"}, {"kind": "summary", **S()}])
    assert batch.classify_log(p) == "complete"
    write_log(p, [{"kind": "config"}, {"kind": "summary", **S(subtype="error_max_turns", is_error=True, exception="ClaudeSDKError: x")}])
    assert batch.classify_log(p) == "complete"
    write_log(p, [{"kind": "config"}, {"kind": "summary", **S(subtype=None, result=None, exception="ToolGuardError: x")}])
    assert batch.classify_log(p) == "aborted"


# ---------------- 이어하기 ----------------

def seed(env, task, kind, n=1, final_dir=True):
    p = run_log(env, task, n)
    if kind == "complete":
        write_log(p, [{"kind": "config", "task_id": task}, {"kind": "summary", **S(task_id=task)}])
    elif kind == "incomplete":
        write_log(p, [{"kind": "config", "task_id": task}, {"kind": "message", "message": {"x": 1}}])
    elif kind == "maxturns":
        write_log(p, [{"kind": "config"}, {"kind": "summary", **S(task_id=task, subtype="error_max_turns", is_error=True, exception="ClaudeSDKError: exit 1")}])
    elif kind == "guard":
        write_log(p, [{"kind": "config"}, {"kind": "summary", **S(task_id=task, subtype=None, result=None, exception="ToolGuardError: x")}])
    if final_dir:
        d = env.out / f"{p.stem}_final"
        d.mkdir()
        (d / "marker.txt").write_text("old snapshot", encoding="utf-8")
    return p


def test_resume_skips_complete_and_reruns_interrupted_with_archive(env):
    done = seed(env, "E01", "complete")
    before = done.read_bytes()
    cut = seed(env, "E02", "incomplete")
    cut_bytes = cut.read_bytes()
    code = env.run("--tasks", "E01,E02", "--runs", "1", "--yes", "--no-probe")
    assert code == batch.EXIT_OK
    assert [prompt_to_task(p) for p, _ in env.fake.task_calls()] == ["E02"]            # E01은 건너뛰고 E02만 다시 실행
    assert done.read_bytes() == before                                                 # 끝난 파일은 그대로
    kept = env.out / "day7check_haiku_default_E02_run1.jsonl.partial1"
    assert kept.read_bytes() == cut_bytes                                              # 끊긴 파일은 덮어쓰지 않고 보관
    assert (env.out / "day7check_haiku_default_E02_run1_final.partial1" / "marker.txt").read_text(encoding="utf-8") == "old snapshot"   # 스냅샷 폴더도 같은 규칙
    assert batch.classify_log(cut) == "complete"                                       # 새 파일은 끝까지 기록됨
    assert not (env.out / "day7check_haiku_default_E02_run1_final" / "marker.txt").exists()   # 새 스냅샷은 옛 파일과 섞이지 않는다


def test_second_archive_gets_next_number_and_partial_files_are_not_runs(env):
    seed(env, "E01", "incomplete")
    env.run("--tasks", "E01", "--runs", "1", "--yes", "--no-probe")
    p = run_log(env, "E01")
    p.write_text(p.read_text(encoding="utf-8").split('{"kind": "summary"')[0], encoding="utf-8")    # 다시 끊긴 것처럼 만든다
    env.run("--tasks", "E01", "--runs", "1", "--yes", "--no-probe")
    assert (env.out / "day7check_haiku_default_E01_run1.jsonl.partial1").exists() and (env.out / "day7check_haiku_default_E01_run1.jsonl.partial2").exists()
    assert all(not f.name.endswith(".jsonl") or batch.RUN_FILE_RE.match(f.name) or "summary" in f.name for f in env.out.iterdir() if f.is_file())
    assert not batch.RUN_FILE_RE.match("day7check_haiku_default_E01_run1.jsonl.partial1")


def test_error_max_turns_run_is_complete_and_not_rerun(env):
    seed(env, "E01", "maxturns")
    assert env.run("--tasks", "E01", "--runs", "1", "--yes", "--no-probe") == batch.EXIT_OK
    assert env.fake.calls == [] and not list(env.out.glob("*.partial*"))               # 재실행도 보관도 없다


def test_live_error_max_turns_with_exception_is_logged_complete_and_batch_continues(env):
    def script(prompt, options):
        return [init_msg(), rate_event(), result_msg(subtype="error_max_turns", is_error=True, result=None)], ClaudeSDKError("exit 1")
    assert env.run("--tasks", "E01,E02", "--runs", "1", "--yes", "--no-probe", fake=Fake(script)) == batch.EXIT_OK
    assert len(env.fake.task_calls()) == 2                                             # 한 과제의 턴 제한 실패가 배치를 멈추지 않는다
    assert batch.classify_log(run_log(env, "E01")) == "complete"


def test_guard_aborted_run_is_rerun_on_resume(env):
    seed(env, "E01", "guard")
    env.run("--tasks", "E01", "--runs", "1", "--yes", "--no-probe")
    assert len(env.fake.task_calls()) == 1 and (env.out / "day7check_haiku_default_E01_run1.jsonl.partial1").exists()


# ---------------- 시작 전 점검, 확인 프롬프트 ----------------

def test_refuses_when_freeze_does_not_match(env, capsys):
    called = []

    async def pre(cfg):
        called.append(1)
        return {"servers": ["t"]}
    code = env.run("--tasks", "E01", "--runs", "1", "--yes", verify_freeze=lambda: ["변경: src/eval/graders.py (graders)"], preflight=pre)
    assert code == batch.EXIT_REFUSED and env.fake.calls == [] and called == []        # 동결이 다르면 다음 점검도 안 하고 거부
    assert "변경: src/eval/graders.py" in capsys.readouterr().out


def test_refuses_when_visible_servers_are_not_only_t(env, capsys):
    async def pre(cfg):
        raise ToolGuardError("unexpected MCP servers: ['x']")
    assert env.run("--tasks", "E01", "--runs", "1", "--yes", preflight=pre) == batch.EXIT_REFUSED
    assert env.fake.calls == [] and "unexpected MCP servers" in capsys.readouterr().out


def test_confirmation_prompt_n_y_and_yes_flag(env, capsys):
    answers = iter(["n"])
    assert env.run("--tasks", "E01,E02", "--runs", "2", "--no-probe", input_fn=lambda m: next(answers)) == batch.EXIT_DECLINED
    assert env.fake.calls == [] and not list(env.out.glob("*.jsonl"))
    out = capsys.readouterr().out
    assert "예상 호출 수" in out and "4" in out and "측정 전" in out                    # 과제 2 x 반복 2, 어려운 과제 비용은 측정 전
    assert env.run("--tasks", "E01", "--runs", "1", "--no-probe", input_fn=lambda m: "y") == batch.EXIT_OK
    assert len(env.fake.task_calls()) == 1
    # --yes는 입력을 부르지 않는다(env 기본 input_fn은 호출되면 실패한다)
    assert env.run("--tasks", "E02", "--runs", "1", "--yes", "--no-probe") == batch.EXIT_OK


def test_estimate_counts_only_work_left_and_mentions_probes_and_cost_bounds(env, capsys):
    seed(env, "E01", "complete")
    env.run("--tasks", "E01,H01", "--runs", "1", "--no-probe", input_fn=lambda m: "n")
    out = capsys.readouterr().out
    assert "신규 실행 1회" in out and "건너뜀 1" in out
    env.run("--tasks", "H01", "--runs", "1", input_fn=lambda m: "n")
    assert "탐침 호출 2회" in capsys.readouterr().out
    assert "$0.0015" in out and "20" in out                                            # 5턴 데모 상한과 max_turns


def test_dirty_warning_only_for_code_and_data_paths(env, capsys):
    assert env.run("--tasks", "E01", "--runs", "1", "--yes", "--no-probe", git_status=lambda: [" M docs/progress.md", " M tests/test_x.py", "?? results/x.md"]) == batch.EXIT_OK
    assert "경고" not in capsys.readouterr().out                                       # docs/, tests/, results/만 바뀐 건 경고 없음
    answers = iter(["n"])
    code = env.run("--tasks", "E02", "--runs", "1", "--yes", "--no-probe", git_status=lambda: [" M src/agent/runner_agent.py"], input_fn=lambda m: next(answers))
    assert code == batch.EXIT_DECLINED and "경고" in capsys.readouterr().out          # --yes여도 코드 변경은 따로 y/n
    assert env.run("--tasks", "E02", "--runs", "1", "--yes", "--no-probe", "--allow-dirty", git_status=lambda: ["?? fixtures/H01/new.txt"]) == batch.EXIT_OK
    cfg = events(run_log(env, "E02"))[0]
    assert cfg["repro"]["git_dirty"] is True and cfg["repro"]["git_dirty_paths"] == ["fixtures/H01/new.txt"]


def test_relevant_dirty_parsing():
    lines = [" M src/a.py", "?? fixtures/H01/x.txt", " M MANIFEST.json", " M docs/a.md", "?? tests/t.py", "A  README.md", " M src/eval/tasks/E01.json",
             "R  old.py -> src/new.py", "?? results/raw/x.jsonl"]
    assert batch.relevant_dirty(lines) == ["src/a.py", "fixtures/H01/x.txt", "MANIFEST.json", "src/eval/tasks/E01.json", "src/new.py"]


# ---------------- 재현성 필드, 스냅샷 ----------------

def test_config_event_has_repro_fields_without_duplicates(env):
    env.run("--tasks", "E01", "--runs", "1", "--yes", "--no-probe")
    cfg = events(run_log(env))[0]
    assert cfg["kind"] == "config" and cfg["config"]["model"] == "claude-haiku-5-5" and cfg["config"]["max_turns"] == 20   # 베이스라인 기본값 그대로
    r = cfg["repro"]
    for k in ("git_commit", "git_dirty", "git_dirty_paths", "manifest_sha256", "sdk_version", "cli_version", "python_version", "os"):
        assert k in r, k
    assert re.fullmatch(r"[0-9a-f]{64}", r["manifest_sha256"]) and r["cli_version"] == "9.9.9-test" and r["python_version"].startswith("3.")
    assert r["sdk_version"] and r["os"]
    assert not {"model", "max_turns", "prompt_version", "tool_desc_version"} & set(r)   # 이미 config에 있는 항목은 중복하지 않는다


def test_run_task_rejects_duplicate_repro_names(tmp_path, monkeypatch):
    monkeypatch.setattr(runner_agent, "query", Fake())
    import asyncio
    with pytest.raises(ValueError, match="이름이 같은 항목"):
        asyncio.run(runner_agent.run_task("p", HarnessConfig(), log_path=tmp_path / "x.jsonl", config_extra={"model": "x"}))


def test_outputs_are_passed_so_the_snapshot_contains_the_output_file(env):
    out_name = TASKS["E01"].outputs[0]

    def script(prompt, options):
        (Path(options.cwd) / out_name).write_text("made by fake agent\n", encoding="utf-8")
        return [init_msg(), rate_event(), result_msg()], None
    env.run("--tasks", "E01", "--runs", "1", "--yes", "--no-probe", fake=Fake(script))
    snap = env.out / "day7check_haiku_default_E01_run1_final" / out_name
    assert snap.read_text(encoding="utf-8") == "made by fake agent\n"                   # 스냅샷이 results/raw가 아니라 출력 폴더에 저장됨
    assert any(e["kind"] == "snapshot" for e in events(run_log(env)))


# ---------------- 한도 감시 ----------------

def five(env_, value, status="allowed"):
    return Fake(lambda prompt, options: ([init_msg(), rate_event(five=value, status=status), result_msg()], None))


def test_threshold_stops_before_next_run_and_prints_restart(env, capsys):
    code = env.run("--tasks", "E01,E02,E03", "--runs", "1", "--yes", "--no-probe", "--five-hour-stop", "0.40", fake=five(env, 0.45))
    out = capsys.readouterr().out
    assert code == batch.EXIT_STOPPED and len(env.fake.task_calls()) == 1              # 첫 실행 뒤 두 번째를 시작하지 않는다
    assert "five_hour" in out and "0.45" in out and "python -m src.eval.batch" in out and "--tasks E01,E02,E03" in out and "미확인" in out
    assert summary_records(env)[-1]["kind"] == "batch_end" and summary_records(env)[-1]["reason"].startswith("한도 임계")


def test_threshold_equal_stops_and_below_or_unset_does_not(env):
    assert env.run("--tasks", "E01,E02", "--runs", "1", "--yes", "--no-probe", "--five-hour-stop", "0.45", fake=five(env, 0.45)) == batch.EXIT_STOPPED
    assert len(env.fake.task_calls()) == 1
    for p in env.out.glob("*"):
        p.unlink() if p.is_file() else None
    assert env.run("--tasks", "E01,E02", "--runs", "1", "--yes", "--no-probe", "--five-hour-stop", "0.90", fake=five(env, 0.45)) == batch.EXIT_OK
    assert len(env.fake.task_calls()) == 2
    for p in env.out.glob("*"):
        p.unlink() if p.is_file() else None
    assert env.run("--tasks", "E01,E02,E03", "--runs", "1", "--yes", "--no-probe", fake=five(env, 0.99)) == batch.EXIT_OK   # 임계 미설정이면 멈추지 않는다
    assert len(env.fake.task_calls()) == 3


def test_threshold_from_limits_file_and_cli_override(env, tmp_path):
    lim = tmp_path / "limits.json"
    lim.write_text(json.dumps({"five_hour_stop": 0.40}), encoding="utf-8")
    assert env.run("--tasks", "E01,E02", "--runs", "1", "--yes", "--no-probe", "--limits-file", str(lim), fake=five(env, 0.45)) == batch.EXIT_STOPPED
    for p in env.out.glob("*"):
        p.unlink()
    assert env.run("--tasks", "E01,E02", "--runs", "1", "--yes", "--no-probe", "--limits-file", str(lim), "--five-hour-stop", "0.99", fake=five(env, 0.45)) == batch.EXIT_OK


@pytest.mark.parametrize("status,stops", [("allowed", False), ("allowed_warning", True), ("rejected", True), ("something_new", True)])
def test_any_non_allowed_status_stops_after_the_run(env, status, stops):
    code = env.run("--tasks", "E01,E02", "--runs", "1", "--yes", "--no-probe", fake=five(env, 0.10, status=status))
    assert (code == batch.EXIT_STOPPED) is stops and len(env.fake.task_calls()) == (1 if stops else 2)


def test_run_records_limit_values_range_and_unverified_unit(env):
    values = iter([0.20, 0.25, 0.22])
    fake = Fake(lambda p, o: ([init_msg(), rate_event(five=next(values)), result_msg()], None))
    env.run("--tasks", "E01,E02,E03", "--runs", "1", "--yes", "--no-probe", fake=fake)
    runs = [r for r in summary_records(env) if r["kind"] == "run"]
    assert [r["five_hour"] for r in runs] == [0.20, 0.25, 0.22] and all(r["seven_day"] == 0.30 for r in runs)
    assert runs[-1]["observed_five_hour_range"] == [0.20, 0.25]                          # 관찰된 값 범위를 그대로 남긴다
    assert all(r["utilization_unit"] == "미확인" and r["status"] == "complete" for r in runs)


# ---------------- 탐침, 배치 델타 ----------------

def test_probe_runs_at_start_and_end_with_no_tools_one_turn_and_separate_names(env):
    seq = iter([0.20, 0.50, 0.23])                                                      # 탐침(시작), 과제, 탐침(끝)
    fake = Fake(lambda p, o: ([init_msg([]) if o.max_turns == 1 else init_msg(), rate_event(five=next(seq)), result_msg(num_turns=1)], None))
    assert env.run("--tasks", "E01", "--runs", "1", "--yes", fake=fake) == batch.EXIT_OK
    probes = fake.probe_calls()
    assert len(probes) == 2 and len(fake.task_calls()) == 1
    for _, o in probes:
        assert o.model == "claude-haiku-5-5" and o.max_turns == 1 and o.tools == [] and o.allowed_tools == []
        assert o.env.get("ENABLE_CLAUDEAI_MCP_SERVERS") == "false" and not o.mcp_servers
    names = sorted(p.name for p in env.out.glob("probe_*"))
    assert names == ["probe_haiku_day7check-default_inv1_end.jsonl", "probe_haiku_day7check-default_inv1_start.jsonl"]
    assert not any(batch.RUN_FILE_RE.match(p.name) for p in env.out.glob("probe_*"))     # 베이스라인 이어하기 감지에 섞이지 않는다
    rec = {r["kind"]: r for r in summary_records(env) if r["kind"] in ("batch_start", "batch_end")}
    assert rec["batch_start"]["five_hour"] == 0.20 and rec["batch_start"]["source"] == "probe"
    assert rec["batch_end"]["five_hour"] == 0.23 and rec["batch_end"]["source"] == "probe"


def test_no_probe_uses_manual_start_then_first_event_fallback(env):
    values = iter([0.30, 0.34])
    fake = Fake(lambda p, o: ([init_msg(), rate_event(five=next(values), seven=0.40), result_msg()], None))
    env.run("--tasks", "E01,E02", "--runs", "1", "--yes", "--no-probe", "--start-five-hour", "0.25", "--start-seven-day", "0.38", fake=fake)
    assert fake.probe_calls() == []
    rec = {r["kind"]: r for r in summary_records(env) if r["kind"] in ("batch_start", "batch_end")}
    assert rec["batch_start"]["source"] == "manual" and rec["batch_start"]["five_hour"] == 0.25 and rec["batch_start"]["seven_day"] == 0.38
    assert rec["batch_end"]["source"] == "last_event" and rec["batch_end"]["five_hour"] == 0.34
    for p in list(env.out.glob("*")):
        p.unlink()
    fake = Fake(lambda p, o: ([init_msg(), rate_event(five=next(iter([0.30]))), result_msg()], None))
    env.run("--tasks", "E01", "--runs", "1", "--yes", "--no-probe", fake=fake)
    start = [r for r in summary_records(env) if r["kind"] == "batch_start"][0]
    assert start["source"] == "first_event" and "첫 실행" in start["note"]               # 첫 실행분이 델타에서 빠진다는 한계를 적는다


def test_second_invocation_gets_new_probe_numbers_and_summary_is_appended(env):
    env.run("--tasks", "E01", "--runs", "1", "--yes")
    env.run("--tasks", "E02", "--runs", "1", "--yes")
    assert (env.out / "probe_haiku_day7check-default_inv2_start.jsonl").exists()
    assert [r["invocation"] for r in summary_records(env) if r["kind"] == "batch_start"] == [1, 2]


# ---------------- 요약 ----------------

def md_text(env):
    files = sorted(env.res.glob("day7check_haiku_default_*summary*.md"))
    assert files, "요약 파일이 results에 저장되어야 한다"
    return files[-1].read_text(encoding="utf-8")


def test_summary_table_counts_and_report_sections(env, capsys):
    def script(prompt, options):
        tid = prompt_to_task(prompt)
        if tid == "E02":
            (Path(options.cwd) / TASKS["E02"].outputs[0]).write_text("x\n", encoding="utf-8")
        return [init_msg(), rate_event(), result_msg(num_turns=4 if tid == "E01" else 2, total_cost_usd=0.02)], None
    env.run("--tasks", "E01,E02", "--runs", "1", "--yes", "--no-probe", fake=Fake(script))
    text = md_text(env)
    assert capsys.readouterr().out.count("평균 턴") >= 1                                  # 표를 화면에도 출력
    for token in ("통과", "실패", "failure_type", "평균 턴 수 | 3.0", "정가 환산 비용 합계 | $0.0400", "입력 토큰 | 200", "출력 토큰 | 40",
                  "캐시 읽기 토큰 | 100", "캐시 생성 토큰 | 20", "배치 델타", "성공률", "N="):
        assert token in text, token                                                       # report.py의 표본 크기 문구(N=...)가 붙는다
    assert "missing_output" in text or "wrong_value" in text


@pytest.mark.parametrize("start,end,flag", [(0.30, 0.31, True), (0.30, 0.32, True), (0.30, 0.45, False)])
def test_batch_delta_flags_values_at_or_below_measurement_limit(env, start, end, flag):
    seq = iter([start, 0.35, end])
    fake = Fake(lambda p, o: ([init_msg([]) if o.max_turns == 1 else init_msg(), rate_event(five=next(seq)), result_msg()], None))
    env.run("--tasks", "E01", "--runs", "1", "--yes", fake=fake)
    text = md_text(env)
    five_row = next(ln for ln in text.splitlines() if ln.startswith("| five_hour |"))
    assert ("측정 한계 이하일 수 있음" in five_row) is flag                              # seven_day는 값이 그대로라 따로 표시되므로 five_hour 줄만 본다
    assert "단위 미확인" in text and "과제 단위 델타는 쓰지 않는다" in text


def test_batch_delta_unavailable_is_stated(env):
    fake = Fake(lambda p, o: ([init_msg(), result_msg()], None))                          # 한도 이벤트가 하나도 없는 경우
    env.run("--tasks", "E01", "--runs", "1", "--yes", "--no-probe", fake=fake)
    assert "측정 불가" in md_text(env)


def test_aborted_runs_are_not_counted_as_failures_in_the_summary(env):
    env.run("--tasks", "E01", "--runs", "1", "--yes", "--no-probe", fake=Fake(lambda p, o: ([init_msg(["Bash"] + list(ALLOWED))], None)))
    text = md_text(env)
    assert "중단된 실행 | 1" in text and "통과 | 0" in text and "실패 | 0" in text


# ---------------- 중단, 오류 ----------------

def test_keyboard_interrupt_keeps_logs_valid_and_resume_works(env, capsys):
    state = {"n": 0}

    def script(prompt, options):
        state["n"] += 1
        if state["n"] == 2:
            return [init_msg(), rate_event()], KeyboardInterrupt()                       # 두 번째 실행 도중 Ctrl+C
        return [init_msg(), rate_event(), result_msg()], None
    code = env.run("--tasks", "E01,E02,E03", "--runs", "1", "--yes", "--no-probe", fake=Fake(script))
    assert code == batch.EXIT_INTERRUPTED
    for f in env.out.glob("day7check_*_run1.jsonl"):
        for line in f.read_text(encoding="utf-8").splitlines():
            json.loads(line)                                                              # 모든 줄이 온전한 JSON
    assert batch.classify_log(run_log(env, "E01")) == "complete" and batch.classify_log(run_log(env, "E02")) == "incomplete"
    assert not run_log(env, "E03").exists()
    last = summary_records(env)[-1]
    assert last["kind"] == "batch_end" and last["reason"] == "사용자 중단(KeyboardInterrupt)"
    assert "python -m src.eval.batch" in capsys.readouterr().out                          # 이어하기 방법 출력
    assert env.run("--tasks", "E01,E02,E03", "--runs", "1", "--yes", "--no-probe", fake=Fake()) == batch.EXIT_OK
    assert [prompt_to_task(p) for p, _ in env.fake.task_calls()] == ["E02", "E03"]        # E01은 건너뛰고 끊긴 E02부터 이어서
    assert (env.out / "day7check_haiku_default_E02_run1.jsonl.partial1").exists()


def test_tool_guard_error_is_an_aborted_run_and_stops_the_batch(env, capsys):
    fake = Fake(lambda p, o: ([init_msg(["Bash"] + list(ALLOWED))], None))
    assert env.run("--tasks", "E01,E02", "--runs", "1", "--yes", "--no-probe", fake=fake) == batch.EXIT_STOPPED
    assert len(fake.task_calls()) == 1 and batch.classify_log(run_log(env, "E01")) == "aborted"
    assert "ToolGuardError" in capsys.readouterr().out
    assert [r for r in summary_records(env) if r["kind"] == "run"][-1]["status"] == "aborted"


def test_api_or_limit_looking_errors_stop_without_retry(env, capsys):
    fake = Fake(lambda p, o: ([init_msg()], RuntimeError("429 rate limit exceeded")))
    assert env.run("--tasks", "E01,E02", "--runs", "1", "--yes", "--no-probe", fake=fake) == batch.EXIT_STOPPED
    assert len(fake.task_calls()) == 1                                                   # 재시도하지 않는다
    assert "429 rate limit exceeded" in capsys.readouterr().out and batch.classify_log(run_log(env, "E01")) == "aborted"
    fake = Fake(lambda p, o: ([init_msg(), result_msg(is_error=True, result="You've hit your usage limit")], None))
    for f in env.out.glob("*"):
        f.unlink() if f.is_file() else None
    assert env.run("--tasks", "E01,E02", "--runs", "1", "--yes", "--no-probe", fake=fake) == batch.EXIT_STOPPED
    assert len(fake.task_calls()) == 1


# ---------------- 비용 상한 측정값 ----------------

def test_measured_cost_bounds_use_only_batch_logs(env):
    def log(name, task, cost):
        write_log(env.out / name, [{"kind": "config"}, {"kind": "summary", **S(task_id=task, total_cost_usd=cost)}])
    log("day7check_haiku_default_H01_run1.jsonl", "H01", 0.05)
    log("day7check_haiku_default_H02_run1.jsonl", "H02", 0.09)
    log("day7check_haiku_default_E01_run1.jsonl", "E01", 0.01)
    log("day7check_haiku_default_E02_run1.jsonl.partial1", "E02", 9.99)                  # 보관 파일은 제외
    log("probe_haiku_day7check-default_inv1_start.jsonl", "probe", 8.88)                  # 탐침은 제외
    log("day4check_haiku_E01_run1.jsonl", "E01", 7.77)                                    # 옛 규칙 파일은 제외
    b = batch.measured_cost_bounds(env.out)
    assert b == {"H": {"max": 0.09, "n": 2}, "E": {"max": 0.01, "n": 1}}


# ---------------- runs.csv: 호출마다 전체 로그에서 다시 만든다(멱등) ----------------

def read_csv_rows(env):
    import csv
    p = env.res / "day7check_haiku_default_runs.csv"
    with p.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_runs_csv_accumulates_across_invocations_and_is_idempotent(env):
    assert env.run("--tasks", "E01", "--runs", "1", "--yes", "--no-probe") == batch.EXIT_OK
    assert [(r["task"], r["run"]) for r in read_csv_rows(env)] == [("E01", "1")]
    assert env.run("--tasks", "H01", "--runs", "1", "--yes", "--no-probe") == batch.EXIT_OK
    # 두 번째 호출은 H01만 선택했지만 CSV에는 앞 호출의 E01 행도 남아 있어야 한다
    assert [(r["task"], r["run"]) for r in read_csv_rows(env)] == [("E01", "1"), ("H01", "1")]
    assert env.run("--tasks", "E01", "--runs", "2", "--yes", "--no-probe") == batch.EXIT_OK
    assert [(r["task"], r["run"]) for r in read_csv_rows(env)] == [("E01", "1"), ("E01", "2"), ("H01", "1")]
    csv_path = env.res / "day7check_haiku_default_runs.csv"
    before = csv_path.read_bytes()
    assert env.run("--tasks", "E01", "--runs", "2", "--yes", "--no-probe") == batch.EXIT_OK   # 할 일 없음
    assert csv_path.read_bytes() == before                                                    # 멱등: 같은 입력이면 같은 파일


def test_runs_csv_rebuilds_from_logs_and_ignores_other_experiments_and_partials(env):
    import shutil
    assert env.run("--tasks", "E01", "--runs", "1", "--yes", "--no-probe") == batch.EXIT_OK
    src = run_log(env, "E01", 1)
    shutil.copy(src, env.out / "other_haiku_default_E02_run1.jsonl")             # 다른 실험 이름
    shutil.copy(src, env.out / "day7check_haiku_default_E03_run1.jsonl.partial1")   # 보관된 끊긴 실행
    shutil.copy(src, env.out / "day7check_haiku_other_E04_run1.jsonl")           # 다른 설정 이름
    (env.res / "day7check_haiku_default_runs.csv").write_text("stale\n", encoding="utf-8")   # 낡은 파일은 덮어쓴다
    assert env.run("--tasks", "E01", "--runs", "1", "--yes", "--no-probe") == batch.EXIT_OK
    assert [(r["task"], r["run"]) for r in read_csv_rows(env)] == [("E01", "1")]


# ---------------- 실험 A: 설정 이름(--config-name), 이어하기 분리 ----------------

def option_desc(call_options, tool="file_stats"):
    import asyncio
    srv = call_options.mcp_servers["t"]
    r = asyncio.run(srv["instance"]._request_handlers["tools/list"].handler(None, None))
    return {t.name: t.description for t in r.tools}[tool]


def test_config_name_selects_tool_desc_version_and_file_label(env):
    from src.agent import tool_variants
    for name, label, version in [("short", "short", "short"), ("long", "long", "long"), ("long_directive", "longDirective", "long_directive"),
                                 ("longDirective", "longDirective", "long_directive")]:
        assert env.run("--experiment", "expA", "--tasks", "E01", "--runs", "1", "--yes", "--no-probe", "--config-name", name) == batch.EXIT_OK
        log = env.out / f"expA_haiku_{label}_E01_run1.jsonl"
        assert log.exists()
        cfg = next(e for e in events(log) if e.get("kind") == "config")
        assert cfg["config"]["tool_desc_version"] == version                       # 설정은 로그에 그대로 남는다
        assert option_desc(env.fake.task_calls()[-1][1]) == tool_variants.VARIANT_DESCRIPTIONS[version]["file_stats"]
        log.unlink()
        (env.out / f"expA_haiku_{label}_summary.jsonl").unlink()


def test_config_name_and_config_are_the_same_option_and_unknown_is_refused(env):
    assert env.run("--experiment", "expA", "--tasks", "E01", "--runs", "1", "--yes", "--no-probe", "--config", "short") == batch.EXIT_OK
    assert (env.out / "expA_haiku_short_E01_run1.jsonl").exists()
    n = len(env.fake.calls)
    assert env.run("--experiment", "expA", "--tasks", "E01", "--runs", "1", "--yes", "--no-probe", "--config-name", "medium") == batch.EXIT_REFUSED
    assert len(env.fake.calls) == n                                                # 거부되면 호출 없음
    a = batch.parse_args(["--experiment", "expA", "--all", "--config-name", "long_directive"])
    assert a.config == "longDirective"                                            # 밑줄 이름은 파일명용 이름으로 바꾼다


def test_resume_does_not_mix_baseline_and_expA_or_expA_variants(env):
    run = lambda exp, cfg: env.run("--experiment", exp, "--tasks", "E01", "--runs", "1", "--yes", "--no-probe", *(["--config-name", cfg] if cfg else []))  # noqa: E731
    assert run("baseline", None) == batch.EXIT_OK
    n0 = len(env.fake.task_calls())
    assert run("expA", "short") == batch.EXIT_OK                                  # 베이스라인 로그가 있어도 건너뛰지 않는다
    assert len(env.fake.task_calls()) == n0 + 1
    assert run("expA", "short") == batch.EXIT_OK                                  # 같은 이름이면 건너뜀
    assert len(env.fake.task_calls()) == n0 + 1
    assert run("expA", "long") == batch.EXIT_OK                                   # 다른 변형은 별도 실행
    assert len(env.fake.task_calls()) == n0 + 2
    names = sorted(p.name for p in env.out.glob("*_E01_run1.jsonl"))
    assert names == ["baseline_haiku_default_E01_run1.jsonl", "expA_haiku_long_E01_run1.jsonl", "expA_haiku_short_E01_run1.jsonl"]
    import csv
    for stem in ("baseline_haiku_default", "expA_haiku_short", "expA_haiku_long"):
        with (env.res / f"{stem}_runs.csv").open(encoding="utf-8", newline="") as f:
            assert [(r["task"], r["run"]) for r in csv.DictReader(f)] == [("E01", "1")]    # 실험/설정마다 CSV가 따로, 서로의 행이 없다
    assert (env.res / "expA_haiku_short_summary_inv1.md").exists() and (env.res / "expA_haiku_long_summary_inv1.md").exists()


def test_probe_file_name_carries_experiment_and_config_label(env):
    assert env.run("--experiment", "expA", "--tasks", "E01", "--runs", "1", "--yes", "--config-name", "long_directive") == batch.EXIT_OK
    assert (env.out / "probe_haiku_expA-longDirective_inv1_start.jsonl").exists()


# ---------------- 실험 B: --prompt-version, expB, 이어하기 분리 ----------------

def test_prompt_version_option_selects_prompt_and_file_label(env):
    from src.agent import config as hc
    from src.agent.tools import DESCRIPTIONS
    for pv_name, label in [("verify", "verify"), ("verify_tool", "verifyTool"), ("v1", "default")]:
        assert env.run("--experiment", "expB", "--tasks", "E01", "--runs", "1", "--yes", "--no-probe", "--prompt-version", pv_name) == batch.EXIT_OK
        log = env.out / f"expB_haiku_{label}_E01_run1.jsonl"
        assert log.exists(), label
        cfg = next(e for e in events(log) if e.get("kind") == "config")
        assert cfg["config"]["prompt_version"] == pv_name and cfg["config"]["tool_desc_version"] == "default"   # 설정은 로그에 그대로 남는다
        opts = env.fake.task_calls()[-1][1]
        assert opts.system_prompt == (hc.PROMPTS["v1"] if pv_name == "v1" else hc.VARIANT_PROMPTS[pv_name])
        assert option_desc(opts) == DESCRIPTIONS["default"]["file_stats"]


def test_config_name_can_select_prompt_variants_too_and_underscore_alias_works(env):
    a = batch.parse_args(["--experiment", "expB", "--all", "--config-name", "verify_tool"])
    assert a.config == "verifyTool"
    assert env.run("--experiment", "expB", "--tasks", "E01", "--runs", "1", "--yes", "--no-probe", "--config-name", "verifyTool") == batch.EXIT_OK
    assert (env.out / "expB_haiku_verifyTool_E01_run1.jsonl").exists()


def test_prompt_version_conflicts_and_unknown_values_are_refused_without_calls(env):
    n = len(env.fake.calls)
    base = ["--experiment", "expB", "--tasks", "E01", "--runs", "1", "--yes", "--no-probe"]
    assert env.run(*base, "--prompt-version", "v2") == batch.EXIT_REFUSED                         # 모르는 버전
    assert env.run(*base, "--config-name", "short", "--prompt-version", "verify") == batch.EXIT_REFUSED   # 변수 둘을 한 번에 바꾸는 조합
    assert env.run(*base, "--config-name", "verify", "--prompt-version", "verify_tool") == batch.EXIT_REFUSED   # 서로 다른 변형
    assert len(env.fake.calls) == n
    assert env.run(*base, "--config-name", "verify", "--prompt-version", "verify") == batch.EXIT_OK            # 같은 변형이면 허용


def test_resume_does_not_mix_baseline_expA_and_expB(env):
    import csv
    run = lambda exp, *extra: env.run("--experiment", exp, "--tasks", "E01", "--runs", "1", "--yes", "--no-probe", *extra)  # noqa: E731
    assert run("baseline") == batch.EXIT_OK
    n0 = len(env.fake.task_calls())
    assert run("expA", "--config-name", "short") == batch.EXIT_OK
    assert run("expB", "--prompt-version", "verify") == batch.EXIT_OK                  # 다른 실험이라 건너뛰지 않는다
    assert len(env.fake.task_calls()) == n0 + 2
    assert run("expB", "--prompt-version", "verify") == batch.EXIT_OK                  # 같은 이름이면 건너뜀
    assert len(env.fake.task_calls()) == n0 + 2
    assert run("expB", "--prompt-version", "verify_tool") == batch.EXIT_OK             # 다른 변형은 별도 실행
    assert run("expB", "--config-name", "verifyTool") == batch.EXIT_OK                 # 같은 변형을 다른 옵션 이름으로 줘도 같은 파일 -> 건너뜀
    assert len(env.fake.task_calls()) == n0 + 3
    names = sorted(p.name for p in env.out.glob("*_E01_run1.jsonl"))
    assert names == ["baseline_haiku_default_E01_run1.jsonl", "expA_haiku_short_E01_run1.jsonl",
                     "expB_haiku_verifyTool_E01_run1.jsonl", "expB_haiku_verify_E01_run1.jsonl"]
    for stem in ("baseline_haiku_default", "expA_haiku_short", "expB_haiku_verify", "expB_haiku_verifyTool"):
        with (env.res / f"{stem}_runs.csv").open(encoding="utf-8", newline="") as f:
            assert [(r["task"], r["run"]) for r in csv.DictReader(f)] == [("E01", "1")]        # 실험/설정마다 CSV가 따로
    assert (env.res / "expB_haiku_verify_summary_inv1.md").exists() and (env.res / "expB_haiku_verifyTool_summary_inv1.md").exists()


def test_probe_file_name_for_expB(env):
    assert env.run("--experiment", "expB", "--tasks", "E01", "--runs", "1", "--yes", "--prompt-version", "verify_tool") == batch.EXIT_OK
    assert (env.out / "probe_haiku_expB-verifyTool_inv1_start.jsonl").exists()
    assert (env.out / "probe_haiku_expB-verifyTool_inv1_end.jsonl").exists()
