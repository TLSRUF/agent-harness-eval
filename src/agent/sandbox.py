"""샌드박스 경로 검사. 모든 경로는 root(과제 임시 폴더) 안이어야 한다."""
from pathlib import Path
from typing import Any


class SandboxError(Exception):
    pass


def resolve_in_sandbox(root: str | Path, user_path: str) -> Path:
    """user_path를 root 기준으로 해석하고, root 밖이면 SandboxError.

    절대경로, '..', 심볼릭 링크, 드라이브 문자 경로를 realpath 비교로 모두 차단한다.
    """
    if not isinstance(user_path, str) or not user_path.strip() or "\x00" in user_path:
        raise SandboxError("invalid path")
    root_real = Path(root).resolve()
    candidate = Path(user_path)
    full = candidate if candidate.is_absolute() else root_real / candidate
    real = full.resolve()  # 심볼릭 링크 해석 포함
    if real != root_real and root_real not in real.parents:
        raise SandboxError(f"path escapes sandbox: {user_path}")
    return real


_PATH_KEYS = ("file_path", "path", "notebook_path")


def check_builtin_tool_input(root: str | Path, tool_name: str, tool_input: dict[str, Any]) -> str | None:
    """내장 도구 입력의 경로가 샌드박스 밖이면 사유 문자열, 아니면 None."""
    try:
        for k in _PATH_KEYS:
            v = tool_input.get(k)
            if v:
                resolve_in_sandbox(root, v)
        pat = tool_input.get("pattern")
        if tool_name == "Glob" and isinstance(pat, str):
            # Grep의 pattern은 정규식이라 검사하지 않고, Glob 패턴만 탈출 여부를 본다.
            parts = pat.replace("\\", "/").split("/")
            if ".." in parts or Path(pat).is_absolute() or pat.startswith(("/", "\\")):
                raise SandboxError(f"glob pattern escapes sandbox: {pat}")
    except SandboxError as e:
        return str(e)
    return None
