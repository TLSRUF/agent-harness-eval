"""실험 B: 프롬프트 변형(verify, verify_tool) 테스트 (구현보다 먼저 작성). 모델 호출 없음.

확인하는 것: 기본 프롬프트 v1(동결)은 그대로, 변형은 v1 뒤에 문장만 추가, verify_tool은 verify + 문장 하나,
추가 문장에 도구 이름이나 과제/정답을 암시하는 내용이 없음, 변형을 골라도 도구 설명은 default, 설정은 prompt_version만 다름.
"""
import asyncio
import json
import re
from pathlib import Path

import pytest

from src.agent import config
from src.agent import prompt_variants as pv
from src.agent.config import HarnessConfig
from src.agent.runner_agent import build_options
from src.agent.tools import BUILTIN_CANDIDATES, DESCRIPTIONS, TOOL_NAMES
from src.eval import freeze, loader

VARIANTS = ["verify", "verify_tool"]
V1 = config.PROMPTS["v1"]
ROOT = Path(__file__).resolve().parents[1]


def list_tools(server):
    r = asyncio.run(server["instance"]._request_handlers["tools/list"].handler(None, None))
    return {t.name: t for t in r.tools}


# ---------------- v1은 그대로 ----------------

def test_default_prompt_v1_untouched_and_variants_live_in_separate_module():
    assert set(config.PROMPTS) == {"v1"}                                  # 변형은 config.PROMPTS에 넣지 않는다
    assert set(config.VARIANT_PROMPTS) == set(VARIANTS)
    assert V1 == ("You are a careful assistant that completes file-based tasks inside the working directory. "
                  "Use the provided tools to inspect and modify files. When finished, reply with the final answer only.")
    manifest = json.loads((ROOT / "MANIFEST.json").read_text(encoding="utf-8"))
    assert freeze.config_defaults()["sha256"] == manifest["config_defaults"]["sha256"]
    assert freeze.tool_definitions_v1()["sha256"] == manifest["tool_definitions_v1"]["sha256"]
    assert HarnessConfig().prompt_version == "v1" and HarnessConfig().system_prompt == V1


def test_config_accepts_known_prompt_versions_and_rejects_unknown():
    for v in ["v1", *VARIANTS]:
        assert HarnessConfig(prompt_version=v).prompt_version == v
    with pytest.raises(ValueError):
        HarnessConfig(prompt_version="v2")
    assert HarnessConfig(prompt_version="verify").system_prompt == config.VARIANT_PROMPTS["verify"]


# ---------------- 변형은 v1 + 추가 문장 ----------------

def test_variants_are_v1_plus_added_sentences_only():
    verify, tool = config.VARIANT_PROMPTS["verify"], config.VARIANT_PROMPTS["verify_tool"]
    assert verify == f"{V1} {pv.VERIFY_ADDITION}"
    assert tool == f"{verify} {pv.VERIFY_TOOL_ADDITION}"
    assert verify.startswith(V1) and tool.startswith(V1) and tool.startswith(verify)
    assert pv.VERIFY_ADDITION.strip() == pv.VERIFY_ADDITION and pv.VERIFY_TOOL_ADDITION.strip() == pv.VERIFY_TOOL_ADDITION
    assert pv.VERIFY_ADDITION.count(".") == 2 and pv.VERIFY_ADDITION.endswith(".")         # 일반 지시 두 문장
    assert pv.VERIFY_TOOL_ADDITION.count(".") == 1 and pv.VERIFY_TOOL_ADDITION.endswith(".")  # 추가 문장은 하나
    assert len({V1, verify, tool}) == 3
    assert len(V1) < len(verify) < len(tool)


def test_variant_intent_words_are_present():
    low = pv.VERIFY_ADDITION.lower()
    assert "verify" in low and "correct" in low and "before" in low and "answer" in low
    low = pv.VERIFY_TOOL_ADDITION.lower()
    assert "tool" in low and "satisf" in low and "condition" in low and "use it" in low


def test_build_variants_is_pure_function_of_the_base_prompt():
    out = pv.build_variants("BASE.")
    assert out == {"verify": f"BASE. {pv.VERIFY_ADDITION}", "verify_tool": f"BASE. {pv.VERIFY_ADDITION} {pv.VERIFY_TOOL_ADDITION}"}


# ---------------- 추가 문장에 도구 이름이나 과제 암시가 없다 ----------------

def test_additions_name_no_tools():
    names = list(TOOL_NAMES) + list(BUILTIN_CANDIDATES) + ["Bash", "mcp", "search", "grep", "glob"]
    for text in (pv.VERIFY_ADDITION, pv.VERIFY_TOOL_ADDITION):
        for n in names:
            assert not re.search(rf"\b{re.escape(n)}\b", text, re.I), (n, text)
        assert "_" not in text                                           # 도구 이름 형식(snake_case) 자체가 없다


def _strings(x):
    if isinstance(x, str):
        yield x
    elif isinstance(x, dict):
        for v in x.values():
            yield from _strings(v)
    elif isinstance(x, list):
        for v in x:
            yield from _strings(v)


def test_additions_do_not_contain_task_prompts_answers_files_or_ids():
    tasks = [t for t in loader.load_all() if not t.is_todo]
    fixture_names = {p.name for p in (ROOT / "fixtures").rglob("*") if p.is_file()}
    forbidden = {t.id for t in tasks} | {t.slug for t in tasks} | fixture_names | {o for t in tasks for o in t.outputs}
    answers = set()
    for t in tasks:
        answers |= {s for s in _strings(t.grading.get("params", {})) if len(s) >= 3}
        answers |= {s for s in _strings(t.raw.get("answer", {})) if len(s) >= 3}
    for text in (pv.VERIFY_ADDITION, pv.VERIFY_TOOL_ADDITION):
        for t in tasks:
            assert t.prompt not in text
        for bad in forbidden | answers:
            assert bad not in text, bad
        assert not re.search(r"[A-Z]\d{2}", text) and not re.search(r"\d", text)


# ---------------- 변형을 골라도 바뀌는 건 시스템 프롬프트뿐 ----------------

@pytest.mark.parametrize("variant", VARIANTS)
def test_options_use_variant_prompt_and_default_tool_descriptions(tmp_path, variant):
    o, d = build_options(HarnessConfig(prompt_version=variant), tmp_path), build_options(HarnessConfig(), tmp_path)
    assert o.system_prompt == config.VARIANT_PROMPTS[variant] and d.system_prompt == V1
    listed = list_tools(o.mcp_servers["t"])
    for name in TOOL_NAMES:
        assert listed[name].description == DESCRIPTIONS["default"][name]      # 도구 설명은 default
        assert listed[name].description == list_tools(d.mcp_servers["t"])[name].description
    for attr in ("model", "max_turns", "tools", "allowed_tools", "permission_mode", "setting_sources", "env"):
        assert getattr(o, attr) == getattr(d, attr), attr


@pytest.mark.parametrize("variant", VARIANTS)
def test_config_differs_from_default_only_in_prompt_version(variant):
    a, b = HarnessConfig().to_dict(), HarnessConfig(prompt_version=variant).to_dict()
    assert {k for k in a if a[k] != b[k]} == {"prompt_version"}
    assert b["tool_desc_version"] == "default"
