"""Day 6 새 채점 부품 단위 테스트 (구현보다 먼저 작성): multi_edit_file (여러 파일의 줄 단위 수정, 디코이 줄 보존).

한국어가 붙은 값, 소수, 줄바꿈 경계를 포함한다.
"""
import shutil
from pathlib import Path

import pytest

from src.eval.graders import GRADERS, grade_multi_edit_file

NEW = "endpoint = http://new.internal:9090"
OLD = "endpoint = http://old.internal:8080"

FIXTURE = {
    "a.conf": f"name = alpha\n{OLD}\n# {OLD}\nmode = fast\n",
    "b.conf": f"backup_{OLD}\n{OLD}\nretries = 3\n",
    "c.conf": f"endpoint = http://old.internal:8081\n{OLD}/health\n# {OLD}\n",  # 바꿀 줄이 없는 파일
    "d.conf": f"level = info\n{OLD}\n",
}
EXPECTED = {
    "a.conf": FIXTURE["a.conf"].replace(f"\n{OLD}\n", f"\n{NEW}\n", 1),
    "b.conf": FIXTURE["b.conf"].replace(f"\n{OLD}\n", f"\n{NEW}\n", 1),
    "c.conf": FIXTURE["c.conf"],
    "d.conf": FIXTURE["d.conf"].replace(OLD, NEW),
}
PARAMS = {"files": list(FIXTURE), "expected": EXPECTED}


@pytest.fixture
def env(tmp_path):
    fx, wd = tmp_path / "fx", tmp_path / "wd"
    fx.mkdir()
    for n, t in FIXTURE.items():
        (fx / n).write_bytes(t.encode("utf-8"))
    shutil.copytree(fx, wd)
    return fx, wd


def put(wd, name, text):
    (wd / name).write_bytes(text.encode("utf-8"))


def apply(wd, **texts):
    """EXPECTED를 기본으로 하고 일부 파일만 다른 내용으로 바꿔 쓴다. 키는 'a_conf'처럼 점 대신 밑줄."""
    for n, t in EXPECTED.items():
        put(wd, n, texts.get(n.replace(".", "_"), t))


def grade(env, **texts):
    fx, wd = env
    apply(wd, **texts)
    r = grade_multi_edit_file(wd, PARAMS, fx, list(FIXTURE))
    assert set(r) == {"passed", "failure_type", "reason"} and r["passed"] == (r["failure_type"] == "pass")
    return r["failure_type"]


def test_registered():
    assert GRADERS["multi_edit_file"] is grade_multi_edit_file


def test_pass_and_cosmetic_variants(env):
    assert grade(env) == "pass"
    fx, wd = env
    for variant in (lambda t: t.replace("\n", "\r\n"), lambda t: t.rstrip("\n"), lambda t: t + "\n\n",
                    lambda t: t.replace("endpoint = ", "endpoint  =  "), lambda t: "\n" + t):
        for n, t in EXPECTED.items():
            put(wd, n, variant(t))
        r = grade_multi_edit_file(wd, PARAMS, fx, list(FIXTURE))
        assert r["failure_type"] == "pass", (variant, r)


def test_not_changed_at_all_is_wrong_value(env):
    fx, wd = env  # fixture 그대로
    assert grade_multi_edit_file(wd, PARAMS, fx, list(FIXTURE))["failure_type"] == "wrong_value"


def test_partial_edit_is_wrong_value(env):
    assert grade(env, d_conf=FIXTURE["d.conf"]) == "wrong_value"                  # d.conf를 못 바꿈
    assert grade(env, a_conf=FIXTURE["a.conf"], b_conf=FIXTURE["b.conf"]) == "wrong_value"


def test_wrong_value_variants(env):
    for bad in ("endpoint = http://new.internal:9091", "endpoint = http://new.internal:90900",       # 숫자 일부
                "endpoint = http://new.internal:9090/health", "endpoint = http://new.internal:9090.5",  # 접미가 값 일부
                "endpoint = http://old.internal:9090", "Endpoint = http://new.internal:9090",
                "endpoint = http://new.internal:9090,http://x"):
        assert grade(env, d_conf=f"level = info\n{bad}\n") == "wrong_value", bad


def test_format_error_variants(env):
    for fmt in ("endpoint=http://new.internal:9090",                       # 공백만 다름
                "endpoint = http://new.internal:9090 (변경)",               # 값 뒤에 설명
                "endpoint = http://new.internal:9090포트",                  # 한국어가 붙음
                "endpoint = http://new.internal:9090 # moved"):              # 줄 끝 주석
        assert grade(env, d_conf=f"level = info\n{fmt}\n") == "format_error", fmt


def test_decoy_lines_must_stay(env):
    a = EXPECTED["a.conf"]
    cases = {
        "주석 줄도 바꿈": a.replace(f"# {OLD}", f"# {NEW}"),
        "주석 줄 삭제": a.replace(f"# {OLD}\n", ""),
        "backup 키도 바꿈": EXPECTED["b.conf"].replace(f"backup_{OLD}", f"backup_{NEW}"),
    }
    assert grade(env, a_conf=cases["주석 줄도 바꿈"]) == "unexpected_change"
    assert grade(env, a_conf=cases["주석 줄 삭제"]) == "unexpected_change"
    assert grade(env, b_conf=cases["backup 키도 바꿈"]) == "unexpected_change"
    # 값이 조금 다른 endpoint 줄과 접미 줄도 건드리면 안 된다 (c.conf는 아무것도 바꾸지 않는 파일)
    assert grade(env, c_conf=FIXTURE["c.conf"].replace(OLD + "/health", NEW + "/health")) == "unexpected_change"
    assert grade(env, c_conf=FIXTURE["c.conf"].replace("8081", "9090")) == "unexpected_change"


def test_file_that_needs_no_change_must_not_change(env):
    assert grade(env, c_conf=FIXTURE["c.conf"] + "extra = 1\n") == "unexpected_change"
    assert grade(env, c_conf=FIXTURE["c.conf"].replace("# ", "## ")) == "unexpected_change"


def test_line_count_change_is_unexpected(env):
    assert grade(env, a_conf=EXPECTED["a.conf"] + "extra = 1\n") == "unexpected_change"
    assert grade(env, a_conf=EXPECTED["a.conf"].replace("mode = fast\n", "")) == "unexpected_change"
    assert grade(env, a_conf=EXPECTED["a.conf"].replace("name = alpha\n", "name = alpha\nname = beta\n")) == "unexpected_change"


def test_unexpected_change_outranks_wrong_value(env):
    # b.conf의 대상 줄은 안 바꾸고(wrong_value 조건), a.conf의 주석 줄은 바꿈(unexpected_change 조건)
    assert grade(env, b_conf=FIXTURE["b.conf"], a_conf=EXPECTED["a.conf"].replace(f"# {OLD}", "# changed")) == "unexpected_change"


def test_missing_and_empty_outputs_outrank_everything(env):
    fx, wd = env
    apply(wd, a_conf=EXPECTED["a.conf"].replace("mode = fast", "mode = slow"))     # unexpected_change 조건
    (wd / "d.conf").unlink()                                                       # + 파일 없음
    assert grade_multi_edit_file(wd, PARAMS, fx, list(FIXTURE))["failure_type"] == "missing_output"
    put(wd, "d.conf", "  \n\n")                                                     # 공백뿐인 파일도 없음으로 본다
    assert grade_multi_edit_file(wd, PARAMS, fx, list(FIXTURE))["failure_type"] == "missing_output"


def test_extra_files_are_ignored_and_unlisted_fixture_files_are_protected(env, tmp_path):
    fx, wd = env
    apply(wd)
    put(wd, "scratch.tmp", "x")
    assert grade_multi_edit_file(wd, PARAMS, fx, list(FIXTURE))["failure_type"] == "pass"
    # files에 없는 fixture 파일(보호 대상)을 고치면 unexpected_change
    (fx / "readme.txt").write_text("keep", encoding="utf-8")
    shutil.copy(fx / "readme.txt", wd / "readme.txt")
    (wd / "readme.txt").write_text("changed", encoding="utf-8")
    assert grade_multi_edit_file(wd, PARAMS, fx, list(FIXTURE))["failure_type"] == "unexpected_change"


def test_reason_names_the_problem_files(env):
    fx, wd = env
    apply(wd, d_conf=FIXTURE["d.conf"], a_conf=EXPECTED["a.conf"].replace("mode = fast", "mode = slow"))
    r = grade_multi_edit_file(wd, PARAMS, fx, list(FIXTURE))
    assert "a.conf" in r["reason"]
