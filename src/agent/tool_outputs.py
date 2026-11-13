"""실험 E: 도구 출력 변형. 도구 이름, 입력 스키마, 설명은 바꾸지 않고 file_stats의 성공 출력 문자열만 바꾼다.

- default: 지금 출력 그대로(바이트까지 같다).
- filename: 성공 출력 앞에 "path: <입력 경로>" 한 줄을 붙인다. 입력 경로는 모델이 넘긴 값 그대로다(해석된 절대 경로가 아니다).
  병렬 호출 결과를 파일에 짝짓기 쉽게 하려는 변형이다(가설: expA의 H01 짝 맞춤 오류의 원인 후보).
오류 결과(is_error)는 바꾸지 않는다. 동결 대상(도구 정의 v1의 이름, 기본 설명, 스키마)과 config 기본값은 건드리지 않는다.
"""
from typing import Any

OUTPUT_VARIANTS = ("default", "filename")


def validate_output_variant(variant: str) -> None:
    if variant not in OUTPUT_VARIANTS:
        raise ValueError(f"unknown tool_output_variant: {variant} (allowed: {list(OUTPUT_VARIANTS)})")


def apply_file_stats_output(variant: str, path: str, result: dict[str, Any]) -> dict[str, Any]:
    """file_stats 결과에 출력 변형을 적용한다. default와 오류 결과는 같은 객체를 그대로 돌려주고, 입력을 바꾸지 않는다."""
    validate_output_variant(variant)
    if variant == "default" or result.get("is_error") is True:
        return result
    first, *rest = result["content"]
    return {**result, "content": [{**first, "text": f"path: {path}\n{first['text']}"}, *rest]}
