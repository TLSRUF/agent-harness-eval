"""평가셋 동결: MANIFEST.json이 현재 파일과 일치하는지, 그리고 검증 장치가 변경을 실제로 잡아내는지."""
import json
import shutil
from pathlib import Path

import pytest

from src.eval import freeze

ROOT = Path(__file__).resolve().parents[1]


# ---------------- 진짜 동결 검사: 이 테스트가 실패하면 동결된 파일이 바뀐 것이다 ----------------

def test_manifest_exists_and_has_all_sections():
    m = json.loads(freeze.MANIFEST_PATH.read_text(encoding="utf-8"))
    for key in ("schema", "frozen_on", "tasks", "fixtures", "graders", "solutions", "tool_definitions_v1", "harness_env", "config_defaults"):
        assert key in m, key
    assert len(m["tasks"]) == 40 and len(m["solutions"]) == 40
    assert {Path(p).stem[0] for p in m["tasks"]} == {"E", "M", "H"}
    assert sum(p.endswith(".json") is False for p in m["tasks"]) == 0
    for section in ("tasks", "fixtures", "graders", "solutions"):
        assert all(len(h) == 64 and set(h) <= set("0123456789abcdef") for h in m[section].values()), section


def test_frozen_files_match_manifest():
    problems = freeze.verify(ROOT)
    assert problems == [], "동결된 평가셋이 바뀌었다:\n" + "\n".join(problems)


def test_tool_definitions_v1_harness_env_and_config_defaults_match_manifest():
    m = json.loads(freeze.MANIFEST_PATH.read_text(encoding="utf-8"))
    assert freeze.tool_definitions_v1()["sha256"] == m["tool_definitions_v1"]["sha256"]
    assert freeze.harness_env()["sha256"] == m["harness_env"]["sha256"]
    assert freeze.config_defaults()["sha256"] == m["config_defaults"]["sha256"]
    assert m["harness_env"]["value"] == {"ENABLE_CLAUDEAI_MCP_SERVERS": "false"}
    assert m["config_defaults"]["value"]["model"] == "claude-haiku-5-5" and m["config_defaults"]["value"]["max_turns"] == 20


# ---------------- 검증 장치 자체 테스트 (임시 복사본에서 변조) ----------------

@pytest.fixture()
def tree(tmp_path):
    """동결 대상 파일만 임시 폴더에 복사하고 그 위에서 매니페스트를 만든다."""
    for rel in freeze.frozen_paths(ROOT)["all"]:
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, dst)
    m = freeze.build_manifest(tmp_path)
    return tmp_path, m


def test_clean_copy_verifies(tree):
    root, m = tree
    assert freeze.verify(root, m) == []


def test_modified_task_json_is_detected(tree):
    root, m = tree
    p = root / "src/eval/tasks/E01.json"
    p.write_text(p.read_text(encoding="utf-8").replace("ERROR", "WARN", 1), encoding="utf-8")
    probs = freeze.verify(root, m)
    assert any("E01.json" in x and "변경" in x for x in probs)


@pytest.mark.parametrize("rel", ["fixtures/E01/app.log", "fixtures/H08/note_06.txt", "src/eval/solutions/M05.py", "src/eval/graders.py",
                                 "src/eval/graders_user.py"])
def test_one_byte_change_is_detected(tree, rel):
    root, m = tree
    p = root / rel
    p.write_bytes(p.read_bytes() + b" ")
    assert any(rel in x for x in freeze.verify(root, m)), rel


def test_added_and_removed_files_are_detected(tree):
    root, m = tree
    (root / "fixtures/E01/extra.txt").write_text("x\n", encoding="utf-8")
    (root / "src/eval/tasks/H99.json").write_text("{}", encoding="utf-8")
    (root / "src/eval/solutions/E02.py").unlink()
    probs = "\n".join(freeze.verify(root, m))
    assert "fixtures/E01/extra.txt" in probs and "추가" in probs
    assert "tasks/H99.json" in probs
    assert "solutions/E02.py" in probs and "없음" in probs


def test_crlf_conversion_of_source_files_is_tolerated_but_not_for_fixtures(tree):
    """깃의 줄바꿈 변환으로 코드 파일이 CRLF가 되어도 통과, fixture는 바이트 그대로여야 한다."""
    root, m = tree
    p = root / "src/eval/graders.py"
    p.write_bytes(p.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    assert freeze.verify(root, m) == []
    f = root / "fixtures/E03/text.txt"
    f.write_bytes(f.read_bytes().replace(b"\n", b"\r\n"))
    assert any("fixtures/E03/text.txt" in x for x in freeze.verify(root, m))


def test_changed_tool_definitions_env_and_config_are_detected(tree, monkeypatch):
    root, m = tree
    from src.agent import config, tools, runner_agent
    monkeypatch.setitem(tools.DESCRIPTIONS["default"], "search_text", "changed")
    assert any("도구 정의" in x for x in freeze.verify(root, m))
    monkeypatch.undo()
    monkeypatch.setattr(runner_agent, "HARNESS_ENV", {"ENABLE_CLAUDEAI_MCP_SERVERS": "true"})
    assert any("HARNESS_ENV" in x for x in freeze.verify(root, m))
    monkeypatch.undo()
    monkeypatch.setattr(config, "DEFAULT_MODEL", "claude-sonnet-5-5")
    assert any("config" in x for x in freeze.verify(root, m))


def test_write_refuses_to_overwrite_an_existing_manifest(tmp_path):
    target = tmp_path / "MANIFEST.json"
    target.write_text("{}", encoding="utf-8")
    with pytest.raises(FileExistsError):
        freeze.write_manifest(ROOT, target)


def test_manifest_contains_no_absolute_paths_or_secrets():
    text = freeze.MANIFEST_PATH.read_text(encoding="utf-8")
    assert "C:\\" not in text and "C:/" not in text and "Users" not in text and "@" not in text
