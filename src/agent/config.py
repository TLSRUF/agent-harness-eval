"""하네스 설정. 모델명 등은 코드에서 분리해 여기서만 관리한다."""
from dataclasses import dataclass

DEFAULT_MODEL = "claude-haiku-5-5"
COMPARE_MODEL = "claude-sonnet-5-5"  # 실험 D 부분 실행 전용


@dataclass(frozen=True)
class HarnessConfig:
    model: str = DEFAULT_MODEL
    max_turns: int = 20
    prompt_version: str = "v1"
    tool_desc_version: str = "default"
