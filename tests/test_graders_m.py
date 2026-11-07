"""Day 5 새 채점 부품 단위 테스트 (구현보다 먼저 작성): json_file, edit_file(target_keys), list_file.

한국어가 붙은 값, 소수, 줄바꿈 경계를 포함한다.
"""
import json
import shutil
from pathlib import Path

import pytest

from src.eval.graders import GRADERS, grade_edit_file, grade_json_file, grade_list_file


def make(tmp_path: Path, files: dict[str, str]) -> tuple[Path, Path]:
    """fixture 폴더와 그 복사본(작업 폴더)을 만든다."""
    fx = tmp_path / "fx"
    fx.mkdir(parents=True)
    for name, text in files.items():
        (fx / name).write_bytes(text.encode("utf-8"))
    wd = tmp_path / "wd"
    shutil.copytree(fx, wd)
    return fx, wd


def put(wd: Path, name: str, text: str):
    (wd / name).write_bytes(text.encode("utf-8"))


def test_registry_has_new_graders():
    assert GRADERS["json_file"] is grade_json_file
    assert GRADERS["list_file"] is grade_list_file


# =================== json_file ===================

EXPECTED_JSON = [{"name": "이서연", "score": "88"}, {"name": "박지호", "score": "92"}, {"name": "Lee", "score": "75.5"}]
JP = {"path": "scores.json", "expected": EXPECTED_JSON}


@pytest.fixture
def jenv(tmp_path):
    fx, wd = make(tmp_path, {"scores.csv": "name,score\n이서연,88\n박지호,92\nLee,75.5\n"})
    return fx, wd


def jg(env, text):
    fx, wd = env
    put(wd, "scores.json", text)
    r = grade_json_file(wd, JP, fx, ["scores.json"])
    assert set(r) == {"passed", "failure_type", "reason"} and r["passed"] == (r["failure_type"] == "pass")
    return r["failure_type"]


def test_json_pass_variants(jenv):
    pretty = json.dumps(EXPECTED_JSON, ensure_ascii=False, indent=2)
    compact = json.dumps(EXPECTED_JSON, ensure_ascii=False, separators=(",", ":"))
    ascii_escaped = json.dumps(EXPECTED_JSON)  # \uXXXX 이스케이프도 같은 값
    reordered_keys = json.dumps([{"score": o["score"], "name": o["name"]} for o in EXPECTED_JSON], ensure_ascii=False)
    for text in (pretty, pretty + "\n", pretty + "\n\n\n", compact, ascii_escaped, reordered_keys,
                 pretty.replace("\n", "\r\n"), "\n  " + compact + "  \n"):
        assert jg(jenv, text) == "pass", text[:30]


def test_json_type_difference_is_format_error(jenv):
    cases = [
        [{"name": "이서연", "score": 88}, {"name": "박지호", "score": "92"}, {"name": "Lee", "score": "75.5"}],   # "88" 대신 88
        [{"name": "이서연", "score": "88"}, {"name": "박지호", "score": 92}, {"name": "Lee", "score": 75.5}],
        [{"name": "이서연", "score": 88.0}, {"name": "박지호", "score": "92"}, {"name": "Lee", "score": "75.5"}],   # 88.0도 같은 값
        [{"name": "이서연", "score": "88.00"}, {"name": "박지호", "score": "92"}, {"name": "Lee", "score": "75.50"}],  # 소수 표기 차이
        [{"name": "이서연", "score": "088"}, {"name": "박지호", "score": "92"}, {"name": "Lee", "score": "75.5"}],   # 앞의 0
    ]
    for obj in cases:
        assert jg(jenv, json.dumps(obj, ensure_ascii=False)) == "format_error", obj


def test_json_unparseable_with_values_present_is_format_error(jenv):
    good = json.dumps(EXPECTED_JSON, ensure_ascii=False)
    for text in ("```json\n" + good + "\n```",          # 마크다운 코드 울타리
                 good[:-1] + ",]",                        # 끝 쉼표
                 good.replace('"', "'"),                  # 작은따옴표
                 "﻿" + good,                         # BOM
                 "결과: " + good):                         # 앞에 설명 문구
        assert jg(jenv, text) == "format_error", text[:25]


def test_json_wrong_value_cases(jenv):
    def objs(**over):
        o = [dict(x) for x in EXPECTED_JSON]
        for k, v in over.items():
            idx, key = k.split("_")
            o[int(idx)][key] = v
        return o

    cases = {
        "값 다름": objs(**{"0_score": "89"}),
        "소수 다름": objs(**{"2_score": "75.6"}),
        "한국어 붙음": objs(**{"0_score": "88점"}),
        "이름 다름": objs(**{"1_name": "박지후"}),
        "키 이름 대소문자": [{"Name": o["name"], "score": o["score"]} for o in EXPECTED_JSON],
        "키 누락": [{"name": o["name"]} for o in EXPECTED_JSON],
        "키 추가": [dict(o, grade="A") for o in EXPECTED_JSON],
        "항목 누락": EXPECTED_JSON[:2],
        "항목 추가": EXPECTED_JSON + [{"name": "Kim", "score": "60"}],
        "순서 바뀜": [EXPECTED_JSON[1], EXPECTED_JSON[0], EXPECTED_JSON[2]],
        "빈 배열": [],
        "감싼 객체": {"data": EXPECTED_JSON},
        "중복": EXPECTED_JSON + [EXPECTED_JSON[0]],
    }
    for label, obj in cases.items():
        assert jg(jenv, json.dumps(obj, ensure_ascii=False)) == "wrong_value", label
    for text in ("[]", "{}", "null", "hello", "88"):
        assert jg(jenv, text) == "wrong_value", text


def test_json_bool_and_none_are_not_numbers():
    fx_files = {"in.txt": "x\n"}
    for expected, actual, want in (
        ({"ok": True}, {"ok": "true"}, "format_error"),   # 값은 같고 타입만 다름
        ({"ok": True}, {"ok": 1}, "wrong_value"),         # True와 1은 다른 값
        ({"n": None}, {"n": "null"}, "format_error"),
        ({"n": "1"}, {"n": True}, "wrong_value"),
    ):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            fx, wd = make(Path(td), fx_files)
            put(wd, "o.json", json.dumps(actual))
            r = grade_json_file(wd, {"path": "o.json", "expected": expected}, fx, ["o.json"])
            assert r["failure_type"] == want, (expected, actual, r)


def test_json_missing_and_input_changed(jenv):
    fx, wd = jenv
    assert grade_json_file(wd, JP, fx, ["scores.json"])["failure_type"] == "missing_output"
    for text in ("", "  \n\n"):
        assert jg(jenv, text) == "missing_output"
    put(wd, "scores.json", json.dumps(EXPECTED_JSON, ensure_ascii=False))
    put(wd, "scores.csv", "changed")
    assert grade_json_file(wd, JP, fx, ["scores.json"])["failure_type"] == "unexpected_change"
    (wd / "scores.csv").unlink()
    assert grade_json_file(wd, JP, fx, ["scores.json"])["failure_type"] == "unexpected_change"


# =================== edit_file: target_keys ===================

INI = ("[server]\nhost = 10.0.0.5\nport = 8443\ntimeout = 30\n[network]\nretries = 3\nbackoff = 3\nidle = 30\n"
       "[logging]\nlevel = info\nmax_size = 100\n")
INI_OK = INI.replace("timeout = 30", "timeout = 60").replace("retries = 3", "retries = 5")
EP = {"path": "service.ini", "target_keys": ["timeout", "retries"], "value_tokens": ["60", "5"], "expected_text": INI_OK}


@pytest.fixture
def eenv(tmp_path):
    return make(tmp_path, {"service.ini": INI, "other.txt": "keep\n"})


def eg(env, text, params=EP, outputs=("service.ini",)):
    fx, wd = env
    put(wd, "service.ini", text)
    return grade_edit_file(wd, params, fx, list(outputs))["failure_type"]


def test_edit_multi_pass_variants(eenv):
    for text in (INI_OK, INI_OK.rstrip("\n"), INI_OK.replace("\n", "\r\n"), INI_OK + "\n\n",
                 INI_OK.replace("timeout = 60", "timeout   =   60"), "\n" + INI_OK):
        assert eg(eenv, text) == "pass", repr(text[:20])


def test_edit_multi_format_error(eenv):
    for text in (INI_OK.replace("timeout = 60", "timeout=60"),
                 INI_OK.replace("retries = 5", "retries=5"),
                 INI_OK.replace("timeout = 60", "timeout = 60초"),        # 한국어가 붙은 값
                 INI_OK.replace("retries = 5", "retries = 5회"),
                 INI_OK.replace("timeout = 60", "timeout = 60 # sec")):
        assert eg(eenv, text) == "format_error", repr(text)


def test_edit_multi_wrong_value(eenv):
    for text in (INI,                                                         # 아무것도 안 바꿈
                 INI.replace("timeout = 30", "timeout = 60"),                 # 하나만 바꿈
                 INI.replace("retries = 3", "retries = 5"),
                 INI_OK.replace("retries = 5", "retries = 5.0"),              # 소수 표기
                 INI_OK.replace("retries = 5", "retries = 15"),               # 숫자 일부
                 INI_OK.replace("timeout = 60", "timeout = 600"),
                 INI_OK.replace("timeout = 60", "timeout = 6"),
                 INI_OK.replace("retries = 5", "retries = 5.5")):
        assert eg(eenv, text) == "wrong_value", repr(text)


def test_edit_multi_unexpected_change(eenv):
    for text in (INI_OK.replace("backoff = 3", "backoff = 5"),               # 같은 값을 가진 다른 키
                 INI_OK.replace("idle = 30", "idle = 60"),
                 INI_OK.replace("port = 8443", "port = 8444"),
                 INI_OK.replace("[network]\n", ""),                             # 줄 삭제
                 INI_OK.replace("timeout = 60\n", ""),                         # 대상 줄 삭제
                 INI_OK + "extra = 1\n"):                                      # 줄 추가
        assert eg(eenv, text) == "unexpected_change", repr(text)


def test_edit_single_key_backward_compatible(tmp_path):
    env = make(tmp_path, {"settings.ini": "[g]\ndebug = false\nverbose = false\n"})
    p = {"path": "settings.ini", "target_key": "debug", "value_tokens": ["true"],
         "expected_text": "[g]\ndebug = true\nverbose = false\n"}
    fx, wd = env
    for text, want in (("[g]\ndebug = true\nverbose = false\n", "pass"), ("[g]\ndebug=true\nverbose = false\n", "format_error"),
                       ("[g]\ndebug = maybe\nverbose = false\n", "wrong_value"), ("[g]\ndebug = true\nverbose = true\n", "unexpected_change")):
        put(wd, "settings.ini", text)
        assert grade_edit_file(wd, p, fx, ["settings.ini"])["failure_type"] == want, text


CONF = "# header comment\nhost = a1\n# old setting\nport = 80\nmode = fast\n# end\n"
CONF_OK = "host = a1\nport = 80\nmode = fast\n"
CP = {"path": "legacy.conf", "target_key": "#", "expected_text": CONF_OK}


def test_edit_delete_lines_with_target_key(tmp_path):
    fx, wd = make(tmp_path, {"legacy.conf": CONF})
    def g(text):
        put(wd, "legacy.conf", text)
        return grade_edit_file(wd, CP, fx, ["legacy.conf"])["failure_type"]
    assert g(CONF_OK) == "pass"
    assert g(CONF_OK.replace("\n", "\r\n")) == "pass"
    assert g(CONF_OK.rstrip("\n")) == "pass"
    assert g(CONF) == "wrong_value"                                               # 하나도 안 지움
    assert g("# header comment\n" + CONF_OK) == "wrong_value"                     # 일부만 지움
    assert g(CONF_OK.replace("port = 80\n", "")) == "unexpected_change"          # 주석 아닌 줄까지 지움
    assert g(CONF_OK.replace("port = 80", "port = 81")) == "unexpected_change"
    assert g("mode = fast\nhost = a1\nport = 80\n") == "unexpected_change"        # 순서 바뀜
    assert g("old setting\n" + CONF_OK) == "unexpected_change"                    # '#'만 떼고 내용을 남김


def test_edit_missing_and_empty(eenv):
    fx, wd = eenv
    (wd / "service.ini").unlink()
    assert grade_edit_file(wd, EP, fx, ["service.ini"])["failure_type"] == "missing_output"
    assert eg(eenv, "") == "missing_output"


# =================== list_file ===================

def lenv(tmp_path):
    return make(tmp_path, {"ci.log": "x\n", "keep.txt": "keep\n"})


NUM = {"path": "failed_lines.out", "expected_items": ["12", "57", "190"], "item_pattern": r"\d+"}
NAMES = {"path": "files.out", "expected_items": ["alpha.conf", "billing.conf", "gateway.conf"], "item_pattern": r"[a-z]+\.conf"}
RANK = {"path": "top3.out", "expected_items": ["drill", "router", "plane"], "item_pattern": r"[a-z]+", "order_is_content": True}
PAIRS = {"path": "team.out", "expected_items": ["design: 4", "ops: 3", "qa: 5"], "item_pattern": r"[a-z]+: \d+"}


def lg(tmp_path, params, text):
    fx, wd = lenv(tmp_path)
    put(wd, params["path"], text)
    r = grade_list_file(wd, params, fx, [params["path"]])
    assert set(r) == {"passed", "failure_type", "reason"} and r["passed"] == (r["failure_type"] == "pass")
    return r["failure_type"]


def test_list_pass_variants(tmp_path):
    for i, text in enumerate(("12\n57\n190\n", "12\n57\n190", "12\r\n57\r\n190\r\n", "  12 \n57\n190\n\n", "12\n57\n190\n\n\n")):
        assert lg(tmp_path / f"a{i}", NUM, text) == "pass", repr(text)
    assert lg(tmp_path / "b", NAMES, "alpha.conf\nbilling.conf\ngateway.conf\n") == "pass"
    assert lg(tmp_path / "c", PAIRS, "design: 4\nops: 3\nqa: 5\n") == "pass"
    assert lg(tmp_path / "d", PAIRS, "design:  4\nops: 3\nqa: 5\n") == "pass"      # 연속 공백은 겉모양
    assert lg(tmp_path / "e", RANK, "drill\nrouter\nplane\n") == "pass"


def test_list_order_difference_is_format_error_when_order_is_instruction(tmp_path):
    cases = [(NUM, "190\n57\n12\n"), (NUM, "57\n12\n190\n"), (NAMES, "gateway.conf\nalpha.conf\nbilling.conf\n"),
             (PAIRS, "qa: 5\ndesign: 4\nops: 3\n")]
    for i, (p, text) in enumerate(cases):
        assert lg(tmp_path / f"o{i}", p, text) == "format_error", (p["path"], text)


def test_list_layout_difference_is_format_error(tmp_path):
    cases = [(NUM, "12\n57\n\n190\n"),  # 중간 빈 줄은 내용(겉모양이 아님)이라 format_error
             (NUM, "12, 57, 190\n"), (NUM, "줄 번호: 12, 57, 190\n"), (NUM, "12번째\n57번째\n190번째\n"),   # 한국어가 붙음
             (NUM, "12\n57\n190\n입니다\n"), (NAMES, "./alpha.conf\n./billing.conf\n./gateway.conf\n"),
             (NAMES, "- alpha.conf\n- billing.conf\n- gateway.conf\n"), (NAMES, "alpha.conf, billing.conf, gateway.conf"),
             (PAIRS, "항목: design: 4\nops: 3\nqa: 5\n"), (NUM, "1) 12\n2) 57\n3) 190\n")]
    for i, (p, text) in enumerate(cases):
        r = lg(tmp_path / f"l{i}", p, text)
        # '1) 12'처럼 번호가 섞이는 경우는 내용(숫자)이 달라지므로 wrong_value가 맞다
        assert r == ("wrong_value" if text.startswith("1) ") else "format_error"), (text, r)


def test_list_content_difference_is_wrong_value(tmp_path):
    cases = [(NUM, "12\n57\n"), (NUM, "12\n57\n190\n200\n"), (NUM, "12\n57\n191\n"), (NUM, "12\n57\n190\n190\n"),
             (NUM, "12\n57\n190.5\n"), (NUM, "12\n57\n1900\n"), (NUM, "12\n57\n19\n"), (NUM, ""), (NUM, "없음\n"),
             (NAMES, "alpha.conf\nbilling.conf\n"), (NAMES, "alpha.conf\nbilling.conf\ngateway.conf\nmailer.conf\n"),
             (NAMES, "alpha.conf\nbilling.conf\ngateway.conf.bak\n"), (NAMES, "alpha.conf\nBilling.conf\ngateway.conf\n"),
             (PAIRS, "design: 4\nops: 3\nqa: 6\n"), (PAIRS, "design: 4\nops: 3\n"), (PAIRS, "design: 4\nops: 3\nqa: 5\nsales: 1\n")]
    for i, (p, text) in enumerate(cases):
        r = lg(tmp_path / f"w{i}", p, text)
        if text.strip() == "":
            assert r == "missing_output"
        else:
            assert r == "wrong_value", (p["path"], text, r)


def test_list_order_is_content_is_wrong_value(tmp_path):
    for i, text in enumerate(("router\ndrill\nplane\n", "plane\nrouter\ndrill\n", "drill, plane, router")):
        assert lg(tmp_path / f"r{i}", RANK, text) == "wrong_value", text
    assert lg(tmp_path / "ok", RANK, "drill, router, plane\n") == "format_error"   # 내용과 순서는 맞고 구분자만 다름


def test_list_missing_and_input_changed(tmp_path):
    fx, wd = lenv(tmp_path)
    assert grade_list_file(wd, NUM, fx, ["failed_lines.out"])["failure_type"] == "missing_output"
    put(wd, "failed_lines.out", "12\n57\n190\n")
    put(wd, "ci.log", "changed")
    assert grade_list_file(wd, NUM, fx, ["failed_lines.out"])["failure_type"] == "unexpected_change"
