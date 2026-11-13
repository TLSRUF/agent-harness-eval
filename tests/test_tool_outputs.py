"""실험 E: 도구 출력 변형(filename) 테스트 (구현보다 먼저 작성). 모델 호출 없음.

확인하는 것: 기본 출력은 바이트까지 그대로, 변형은 file_stats 성공 출력 앞에 'path: <입력 경로>' 한 줄만 붙임,
이름/스키마/설명/다른 도구/오류 결과는 변하지 않음, HarnessConfig 기본값(동결)은 그대로이고 변형은 별도 설정 클래스로 선택.
"""
import asyncio
import json
from dataclasses import fields
from pathlib import Path

import pytest

from src.agent import config as hc
from src.agent import tool_outputs as to
from src.agent.config import ExperimentConfig, HarnessConfig
from src.agent.runner_agent import build_options
from src.agent.tools import SCHEMAS, TOOL_NAMES, build_server
from src.eval import freeze

ROOT = Path(__file__).resolve().parents[1]


def handlers(server):
    return server["instance"]._request_handlers


def list_tools(server):
    r = asyncio.run(handlers(server)["tools/list"].handler(None, None))
    return {t.name: t for t in r.tools}


def call_full(server, name, args):
    h = handlers(server)["tools/call"]
    r = asyncio.run(h.handler(None, h.params_type(name=name, arguments=args)))
    return r.content[0].text, bool(getattr(r, "isError", False))


def call(server, name, args):
    return call_full(server, name, args)[0]


@pytest.fixture
def box(tmp_path):
    (tmp_path / "a.txt").write_text("hello world\nsecond line\nhello again\n", encoding="utf-8", newline="\n")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.txt").write_text("hello sub\n", encoding="utf-8", newline="\n")
    return tmp_path


# ---------------- 기본 출력은 그대로 ----------------

def test_default_output_is_byte_identical_golden_and_default_args_unchanged(box):
    assert to.OUTPUT_VARIANTS == ("default", "filename")
    assert call(build_server(box), "file_stats", {"path": "a.txt"}) == "lines=3 words=6 bytes=36"          # 골든 값
    calls = [("search_text", {"query": "hello"}), ("search_text", {"query": "hello", "path": "sub"}), ("search_text", {"query": "zzz"}),
             ("file_stats", {"path": "a.txt"}), ("file_stats", {"path": "./sub/b.txt"}), ("file_stats", {"path": "sub"}), ("file_stats", {"path": "../x"}),
             ("check_result", {"path": "a.txt"}), ("check_result", {"path": "a.txt", "contains": "nope"}), ("check_result", {"path": "missing.txt"})]
    a, b = build_server(box), build_server(box, "default", "default")
    for name, args in calls:
        assert call_full(a, name, args) == call_full(b, name, args), (name, args)


# ---------------- filename 변형 ----------------

def test_filename_variant_prepends_one_path_line_using_the_input_path_as_given(box):
    v = build_server(box, "default", "filename")
    d = build_server(box)
    for p in ["a.txt", "./sub/b.txt", "sub/b.txt", str(box / "a.txt")]:
        out, err = call_full(v, "file_stats", {"path": p})
        base, _ = call_full(d, "file_stats", {"path": p})
        assert out == f"path: {p}\n{base}" and not err, p                     # 입력한 경로 그대로, 한 줄, 그 뒤에 기본 출력
        assert out.count("\n") == 1


def test_filename_variant_changes_nothing_else(box):
    d, v = build_server(box, "long"), build_server(box, "long", "filename")
    ld, lv = list_tools(d), list_tools(v)
    assert list(lv) == list(ld) == TOOL_NAMES
    for n in TOOL_NAMES:
        assert lv[n].description == ld[n].description and lv[n].input_schema == ld[n].input_schema == SCHEMAS[n]
    for name, args in [("search_text", {"query": "hello"}), ("search_text", {"query": "zzz"}), ("check_result", {"path": "a.txt", "contains": "hello"}),
                       ("check_result", {"path": "nope.txt"})]:
        assert call_full(v, name, args) == call_full(d, name, args), (name, args)
    for args in [{"path": "sub"}, {"path": "../x"}, {"path": "missing.txt"}]:    # 오류 결과(디렉터리, 샌드박스 밖, 없음)는 그대로
        out, err = call_full(v, "file_stats", args)
        assert (out, err) == call_full(d, "file_stats", args), args
        assert not out.startswith("path: ")


def test_unknown_output_variant_is_rejected(box):
    with pytest.raises(ValueError):
        build_server(box, "default", "upper")
    with pytest.raises(ValueError):
        ExperimentConfig(tool_output_variant="upper")
    with pytest.raises(ValueError):
        to.apply_file_stats_output("upper", "a.txt", {"content": [{"type": "text", "text": "x"}]})


def test_apply_function_does_not_touch_error_results_and_does_not_mutate_input():
    ok = {"content": [{"type": "text", "text": "lines=1 words=1 bytes=2"}]}
    err = {"content": [{"type": "text", "text": "not a file: d"}], "is_error": True}
    assert to.apply_file_stats_output("default", "a", ok) is ok
    out = to.apply_file_stats_output("filename", "a", ok)
    assert out["content"][0]["text"] == "path: a\nlines=1 words=1 bytes=2" and ok["content"][0]["text"] == "lines=1 words=1 bytes=2"
    assert to.apply_file_stats_output("filename", "a", err) == err


# ---------------- 동결: HarnessConfig 기본값은 그대로 ----------------

def test_harness_config_defaults_and_freeze_are_untouched():
    assert "tool_output_variant" not in HarnessConfig().to_dict()
    assert [f.name for f in fields(HarnessConfig)] == ["model", "max_turns", "prompt_version", "tool_desc_version", "builtin_tools"]
    manifest = json.loads((ROOT / "MANIFEST.json").read_text(encoding="utf-8"))
    assert freeze.config_defaults()["sha256"] == manifest["config_defaults"]["sha256"]
    assert freeze.tool_definitions_v1()["sha256"] == manifest["tool_definitions_v1"]["sha256"]
    assert hc.PROMPTS["v1"] and hc.DEFAULT_MODEL == "claude-haiku-5-5"


def test_experiment_config_extends_harness_config_with_default_equal_to_current_output():
    e = ExperimentConfig()
    assert isinstance(e, HarnessConfig) and e.tool_output_variant == "default"
    assert {k: v for k, v in e.to_dict().items() if k != "tool_output_variant"} == HarnessConfig().to_dict()
    f = ExperimentConfig(tool_desc_version="long", tool_output_variant="filename")
    assert f.to_dict()["tool_output_variant"] == "filename" and f.tool_desc_version == "long" and f.prompt_version == "v1" and f.max_turns == 20
    with pytest.raises(ValueError):
        ExperimentConfig(tool_desc_version="medium")                              # 기존 검증이 그대로 동작


def test_build_options_applies_output_variant_only_for_experiment_config(box):
    plain = build_options(HarnessConfig(tool_desc_version="long"), box)
    var = build_options(ExperimentConfig(tool_desc_version="long", tool_output_variant="filename"), box)
    assert call(plain.mcp_servers["t"], "file_stats", {"path": "a.txt"}) == "lines=3 words=6 bytes=36"
    assert call(var.mcp_servers["t"], "file_stats", {"path": "a.txt"}) == "path: a.txt\nlines=3 words=6 bytes=36"
    for attr in ("model", "max_turns", "system_prompt", "tools", "allowed_tools", "permission_mode", "setting_sources", "env"):
        assert getattr(plain, attr) == getattr(var, attr), attr
    assert list_tools(plain.mcp_servers["t"])["file_stats"].description == list_tools(var.mcp_servers["t"])["file_stats"].description
