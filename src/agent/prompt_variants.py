"""실험 B: 시스템 프롬프트 변형(검증 지시). 기본 프롬프트 v1(config.PROMPTS["v1"])은 동결 대상이라 여기서 바꾸지 않는다.

- verify: v1 뒤에 일반 검증 지시 두 문장을 붙인다. 특정 도구 이름은 쓰지 않는다.
- verify_tool: verify 뒤에 "결과 파일이 요구한 조건을 만족하는지 확인할 도구가 있으면 쓰라"는 문장 하나를 더 붙인다. 이것도 도구 이름은 쓰지 않는다.

도구 설명은 두 변형 모두 default를 쓴다(변수 하나만 바꾼다). 추가 문장에는 과제, 정답, 파일 이름, 숫자가 없다(tests/test_prompt_variants.py가 확인).
"""

VERIFY_ADDITION = "Before giving your final answer, verify your result. If you find a mistake, correct it first."
VERIFY_TOOL_ADDITION = "If a tool is available that can check whether the result file satisfies the requested conditions, use it."

VARIANT_NAMES = ("verify", "verify_tool")


def build_variants(base: str) -> dict[str, str]:
    """기본 프롬프트(base) 뒤에 추가 문장만 붙인 변형들. base는 바꾸지 않는다."""
    verify = f"{base} {VERIFY_ADDITION}"
    return {"verify": verify, "verify_tool": f"{verify} {VERIFY_TOOL_ADDITION}"}
