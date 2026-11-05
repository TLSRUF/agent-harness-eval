"""커스텀 도구 3개 + 샌드박스 훅. 도구는 root(과제 임시 폴더)에 묶여 생성된다."""
from pathlib import Path
from typing import Any

from claude_agent_sdk import HookMatcher, create_sdk_mcp_server, tool

from .sandbox import SandboxError, check_builtin_tool_input, resolve_in_sandbox

SERVER_NAME = "t"
TOOL_NAMES = ["search_text", "file_stats", "check_result"]
ALLOWED_CUSTOM = [f"mcp__{SERVER_NAME}__{n}" for n in TOOL_NAMES]
# 허용 후보 내장 도구. Bash는 항상 끈다.
BUILTIN_CANDIDATES = ["Read", "Write", "Edit", "Glob", "Grep"]
MAX_RESULTS = 50
MAX_FILE_BYTES = 1_000_000

# 도구 설명 버전 (실험 A에서 short/long을 추가한다)
DESCRIPTIONS: dict[str, dict[str, str]] = {
    "default": {
        "search_text": "Search for a text string in files under a folder. Returns matching lines as path:line:text.",
        "file_stats": "Return line count, word count and byte size of a text file.",
        "check_result": "Check that a file exists and optionally contains a string or has a minimum line count. Returns PASS or FAIL with reasons.",
    },
}


# 입력 스키마 (베이스라인 도구 정의 v1). 선택 항목은 required에서 제외한다.
SCHEMAS: dict[str, dict[str, Any]] = {
    "search_text": {
        "type": "object",
        "properties": {"query": {"type": "string"}, "path": {"type": "string"}},
        "required": ["query"],
    },
    "file_stats": {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    },
    "check_result": {
        "type": "object",
        "properties": {"path": {"type": "string"}, "contains": {"type": "string"}, "min_lines": {"type": "integer"}},
        "required": ["path"],
    },
}


def classify_tool(name: str) -> str:
    """SDK가 부여한 도구 이름으로 종류를 판정한다: 'custom' | 'builtin' | 'other'.

    커스텀 도구 이름 형식은 mcp__<서버키>__<도구명> (서버키 SERVER_NAME='t').
    판정은 접두사 mcp__t__ 와 내장 이름 목록으로만 한다 (이 함수가 유일한 판정 지점).
    """
    if name.startswith(f"mcp__{SERVER_NAME}__"):
        return "custom"
    if name in BUILTIN_CANDIDATES:
        return "builtin"
    return "other"


def _ok(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


def _err(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "is_error": True}


def _read_text(p: Path) -> str:
    if p.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f"file too large (> {MAX_FILE_BYTES} bytes)")
    return p.read_text(encoding="utf-8", errors="replace")


def search_text_impl(root: Path, query: str, path: str = ".") -> dict[str, Any]:
    try:
        base = resolve_in_sandbox(root, path)
        if not query:
            return _err("query must not be empty")
        files = [base] if base.is_file() else sorted(f for f in base.rglob("*") if f.is_file())
        hits: list[str] = []
        root_real = Path(root).resolve()
        for f in files:
            try:
                f_real = resolve_in_sandbox(root, str(f))  # 링크로 밖을 가리키는 파일 제외
                text = _read_text(f_real)
            except (SandboxError, ValueError, OSError):
                continue
            for n, line in enumerate(text.splitlines(), 1):
                if query in line:
                    hits.append(f"{f_real.relative_to(root_real).as_posix()}:{n}:{line.strip()}")
                    if len(hits) >= MAX_RESULTS:
                        return _ok("\n".join(hits) + f"\n(truncated at {MAX_RESULTS})")
        return _ok("\n".join(hits) if hits else "no matches")
    except SandboxError as e:
        return _err(f"access denied: {e}")
    except OSError as e:
        return _err(f"error: {e}")


def file_stats_impl(root: Path, path: str) -> dict[str, Any]:
    try:
        p = resolve_in_sandbox(root, path)
        if not p.is_file():
            return _err(f"not a file: {path}")
        text = _read_text(p)
        return _ok(f"lines={len(text.splitlines())} words={len(text.split())} bytes={p.stat().st_size}")
    except SandboxError as e:
        return _err(f"access denied: {e}")
    except (OSError, ValueError) as e:
        return _err(f"error: {e}")


def check_result_impl(root: Path, path: str, contains: str = "", min_lines: int = 0) -> dict[str, Any]:
    try:
        p = resolve_in_sandbox(root, path)
        if not p.is_file():
            return _ok(f"FAIL: file does not exist: {path}")
        text = _read_text(p)
        problems = []
        if contains and contains not in text:
            problems.append(f"missing text: {contains!r}")
        if min_lines and len(text.splitlines()) < int(min_lines):
            problems.append(f"fewer than {min_lines} lines")
        return _ok("PASS" if not problems else "FAIL: " + "; ".join(problems))
    except SandboxError as e:
        return _err(f"access denied: {e}")
    except (OSError, ValueError) as e:
        return _err(f"error: {e}")


def build_server(root: str | Path, desc_version: str = "default"):
    """root에 묶인 SDK MCP 서버를 만든다."""
    root = Path(root).resolve()
    d = DESCRIPTIONS[desc_version]

    @tool("search_text", d["search_text"], SCHEMAS["search_text"])
    async def search_text(args: dict[str, Any]) -> dict[str, Any]:
        return search_text_impl(root, args.get("query", ""), args.get("path") or ".")

    @tool("file_stats", d["file_stats"], SCHEMAS["file_stats"])
    async def file_stats(args: dict[str, Any]) -> dict[str, Any]:
        return file_stats_impl(root, args.get("path", ""))

    @tool("check_result", d["check_result"], SCHEMAS["check_result"])
    async def check_result(args: dict[str, Any]) -> dict[str, Any]:
        return check_result_impl(root, args.get("path", ""), args.get("contains", ""), args.get("min_lines", 0))

    return create_sdk_mcp_server(name=SERVER_NAME, version="1.0.0", tools=[search_text, file_stats, check_result])


def make_sandbox_hook(root: str | Path):
    async def hook(input_data, tool_use_id, context):
        reason = check_builtin_tool_input(root, input_data.get("tool_name", ""), input_data.get("tool_input", {}))
        if reason:
            return {"hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": f"sandbox: {reason}",
            }}
        return {}
    return hook


def sandbox_hooks(root: str | Path) -> dict[str, list[HookMatcher]]:
    return {"PreToolUse": [HookMatcher(matcher="|".join(BUILTIN_CANDIDATES), hooks=[make_sandbox_hook(root)])]}
