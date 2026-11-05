"""하네스 설정. 모델명 등은 코드에서 분리해 여기서만 관리한다.

실험은 한 번에 변수 하나만 바꾼다: model / prompt_version / max_turns / tool_desc_version.
"""
from dataclasses import asdict, dataclass

DEFAULT_MODEL = "claude-haiku-5-5"
COMPARE_MODEL = "claude-sonnet-5-5"  # 실험 D 부분 실행 전용

# 시스템 프롬프트 버전. 실험 B(검증 단계)는 여기에 버전을 추가한다.
PROMPTS: dict[str, str] = {
    "v1": (
        "You are a careful assistant that completes file-based tasks inside the working directory. "
        "Use the provided tools to inspect and modify files. When finished, reply with the final answer only."
    ),
}

BUILTIN_TOOLS_DEFAULT = ("Read", "Write", "Edit", "Glob", "Grep")


@dataclass(frozen=True)
class HarnessConfig:
    model: str = DEFAULT_MODEL
    max_turns: int = 20
    prompt_version: str = "v1"
    tool_desc_version: str = "default"
    builtin_tools: tuple[str, ...] = BUILTIN_TOOLS_DEFAULT  # Bash는 허용하지 않는다

    def __post_init__(self) -> None:
        if "Bash" in self.builtin_tools:
            raise ValueError("Bash is not allowed in this harness")
        if self.prompt_version not in PROMPTS:
            raise ValueError(f"unknown prompt_version: {self.prompt_version}")

    @property
    def system_prompt(self) -> str:
        return PROMPTS[self.prompt_version]

    @property
    def model_short(self) -> str:
        """파일명용 모델 약칭 (claude-haiku-5-5 -> haiku)."""
        for key in ("haiku", "sonnet", "opus", "fable"):
            if key in self.model:
                return key
        return self.model.replace("claude-", "").replace("/", "-")

    def to_dict(self) -> dict:
        d = asdict(self)
        d["builtin_tools"] = list(self.builtin_tools)
        return d
