"""실험 A: 도구 설명 변형(short, long, long_directive) 테스트 (구현보다 먼저 작성). 모델 호출 없음.

확인하는 것: default(동결된 도구 정의 v1)는 그대로, 변형은 설명 텍스트만 다르고 이름/스키마/동작은 같음,
long은 정보만(우선 사용 지시 없음), long_directive는 long + 지시 문장 하나, 설명이 과제나 정답을 암시하지 않음.
"""
import asyncio
import json
import re
from pathlib import Path

import pytest

from src.agent import tool_variants as tv
from src.agent import tools
from src.agent.config import HarnessConfig
from src.agent.runner_agent import build_options
from src.agent.tools import DESCRIPTIONS, SCHEMAS, TOOL_NAMES, build_server
from src.eval import freeze, loader

VARIANTS = ["short", "long", "long_directive"]
ROOT = Path(__file__).resolve().parents[1]
DIRECTIVE_WORDS = ["first", "prefer", "instead", "rather than", "better than", "recommend", "always", "should", "priority", "in preference"]


def handlers(server):
    return server["instance"]._request_handlers


def list_tools(server):
    r = asyncio.run(handlers(server)["tools/list"].handler(None, None))
    return {t.name: t for t in r.tools}


def call(server, name, args):
    h = handlers(server)["tools/call"]
    r = asyncio.run(h.handler(None, h.params_type(name=name, arguments=args)))
    return r.content[0].text


@pytest.fixture
def box(tmp_path):
    (tmp_path / "a.txt").write_text("hello world\nsecond line\nhello again\n", encoding="utf-8", newline="\n")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.txt").write_text("hello sub\n", encoding="utf-8", newline="\n")
    return tmp_path


# ---------------- default는 그대로 ----------------

def test_default_descriptions_untouched_and_variants_live_in_separate_module():
    assert set(DESCRIPTIONS) == {"default"}                      # 변형은 tools.DESCRIPTIONS에 넣지 않는다
    assert set(tv.VARIANT_DESCRIPTIONS) == set(VARIANTS)
    assert DESCRIPTIONS["default"]["search_text"] == "Search for a text string in files under a folder. Returns matching lines as path:line:text."
    manifest = json.loads((ROOT / "MANIFEST.json").read_text(encoding="utf-8"))
    assert freeze.tool_definitions_v1()["sha256"] == manifest["tool_definitions_v1"]["sha256"]
    assert freeze.config_defaults()["sha256"] == manifest["config_defaults"]["sha256"]
    assert HarnessConfig().tool_desc_version == "default"


def test_config_accepts_known_versions_and_rejects_unknown():
    for v in ["default", *VARIANTS]:
        assert HarnessConfig(tool_desc_version=v).tool_desc_version == v
    with pytest.raises(ValueError):
        HarnessConfig(tool_desc_version="medium")


# ---------------- 이름, 스키마, 동작은 default와 같다 ----------------

@pytest.mark.parametrize("variant", VARIANTS)
def test_variant_names_and_schemas_equal_default_only_description_differs(box, variant):
    default = list_tools(build_server(box))
    var = list_tools(build_server(box, variant))
    assert list(var) == list(default) == TOOL_NAMES              # 이름과 순서
    for name in TOOL_NAMES:
        assert var[name].input_schema == default[name].input_schema == SCHEMAS[name]
        assert var[name].description == tv.VARIANT_DESCRIPTIONS[variant][name]
        assert var[name].description != default[name].description
        assert var[name].description.strip() == var[name].description and var[name].description


def test_variant_descriptions_are_pairwise_different_for_every_tool():
    for name in TOOL_NAMES:
        texts = [DESCRIPTIONS["default"][name]] + [tv.VARIANT_DESCRIPTIONS[v][name] for v in VARIANTS]
        assert len(set(texts)) == len(texts)


@pytest.mark.parametrize("variant", VARIANTS)
def test_variant_tool_behavior_identical_to_default(box, variant):
    calls = [("search_text", {"query": "hello"}), ("search_text", {"query": "hello", "path": "sub"}), ("search_text", {"query": "zzz"}),
             ("file_stats", {"path": "a.txt"}), ("file_stats", {"path": "sub"}),
             ("check_result", {"path": "a.txt"}), ("check_result", {"path": "a.txt", "contains": "nope"}),
             ("check_result", {"path": "a.txt", "min_lines": 9}), ("check_result", {"path": "missing.txt"})]
    d, v = build_server(box), build_server(box, variant)
    for name, args in calls:
        assert call(v, name, args) == call(d, name, args), (name, args)


def test_options_use_the_configured_description_version(tmp_path):
    for v in VARIANTS:
        o = build_options(HarnessConfig(tool_desc_version=v), tmp_path)
        listed = list_tools(o.mcp_servers["t"])
        assert listed["file_stats"].description == tv.VARIANT_DESCRIPTIONS[v]["file_stats"]
    o = build_options(HarnessConfig(), tmp_path)
    assert list_tools(o.mcp_servers["t"])["file_stats"].description == DESCRIPTIONS["default"]["file_stats"]


# ---------------- 길이와 내용 규칙 ----------------

def test_length_order_short_default_long_directive():
    for name in TOOL_NAMES:
        default = DESCRIPTIONS["default"][name]
        short, long_, directive = (tv.VARIANT_DESCRIPTIONS[v][name] for v in VARIANTS)
        assert len(short) < len(default) < len(long_) < len(directive)
        assert "\n" not in short and short.count(". ") == 0          # short는 한 줄(한 문장)


def test_long_has_information_but_no_directive_and_long_directive_adds_exactly_one_sentence():
    for name in TOOL_NAMES:
        long_ = tv.VARIANT_DESCRIPTIONS["long"][name]
        directive = tv.VARIANT_DESCRIPTIONS["long_directive"][name]
        for text in (tv.VARIANT_DESCRIPTIONS["short"][name], long_):
            low = text.lower()
            assert not any(w in low for w in DIRECTIVE_WORDS), (name, text)
        assert directive.startswith(long_)
        extra = directive[len(long_):].strip()
        assert extra and extra.endswith(".") and extra.count(".") == 1      # 추가분은 문장 하나
        assert "use this tool first" in extra
        assert extra.lower().count("first") == 1


def test_long_describes_input_output_example_and_what_it_provides():
    s = tv.VARIANT_DESCRIPTIONS["long"]["search_text"]
    assert "query" in s and "path" in s
    assert "relative/path:line_number:line_text" in s and "Example" in s and "line numbers" in s
    f = tv.VARIANT_DESCRIPTIONS["long"]["file_stats"]
    assert "lines=<N> words=<N> bytes=<N>" in f and "Example" in f and "line, word and byte counts" in f
    c = tv.VARIANT_DESCRIPTIONS["long"]["check_result"]
    assert "PASS" in c and "FAIL" in c and "contains" in c and "min_lines" in c and "Example" in c


# ---------------- 과제나 정답을 암시하지 않는다 ----------------

def _strings(x):
    if isinstance(x, str):
        yield x
    elif isinstance(x, dict):
        for v in x.values():
            yield from _strings(v)
    elif isinstance(x, list):
        for v in x:
            yield from _strings(v)


def test_descriptions_do_not_contain_task_prompts_answers_files_or_ids():
    tasks = [t for t in loader.load_all() if not t.is_todo]
    fixture_names = {p.name for p in (ROOT / "fixtures").rglob("*") if p.is_file()}
    forbidden = {t.id for t in tasks} | {t.slug for t in tasks} | fixture_names
    forbidden |= {o for t in tasks for o in t.outputs}
    answers = set()
    for t in tasks:
        answers |= {s for s in _strings(t.grading.get("params", {})) if len(s) >= 3}
        answers |= {s for s in _strings(t.raw.get("answer", {})) if len(s) >= 3}
    all_texts = [(v, n, tv.VARIANT_DESCRIPTIONS[v][n]) for v in VARIANTS for n in TOOL_NAMES]
    for v, n, text in all_texts:
        for t in tasks:
            assert t.prompt not in text and t.id not in re.findall(r"[A-Z]\d{2}", text)
        for bad in forbidden:
            assert bad not in text, (v, n, bad)
        for ans in answers:
            assert ans not in text, (v, n, ans)


def test_example_values_in_descriptions_do_not_appear_in_any_task_prompt_or_fixture_text():
    tasks = [t for t in loader.load_all() if not t.is_todo]
    corpus = "\n".join(t.prompt for t in tasks)
    for p in (ROOT / "fixtures").rglob("*"):
        if p.is_file():
            corpus += "\n" + p.read_text(encoding="utf-8", errors="replace")
    for v in VARIANTS:
        for n in TOOL_NAMES:
            for lit in re.findall(r"'([^']+)'", tv.VARIANT_DESCRIPTIONS[v][n]):
                if lit.startswith("(") or "<" in lit or "FAIL" in lit or "PASS" in lit or lit.startswith("lines="):
                    continue                                      # 출력 형식 문구는 예시 값이 아니다
                if lit.startswith("relative/") or lit.startswith("missing text") or lit.startswith("fewer than"):
                    continue
                assert lit not in corpus, (v, n, lit)
