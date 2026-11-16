"""도구 출력 변형(실험 E, F). 도구 이름, 입력 스키마, 설명은 바꾸지 않고 성공 출력 문자열만 바꾼다.

- default: 지금 출력 그대로(바이트까지 같다).
- filename(실험 E): file_stats 성공 출력 앞에 "path: <입력 경로>" 한 줄을 붙인다. 입력 경로는 모델이 넘긴 값 그대로다(해석된 절대 경로가 아니다).
  병렬 호출 결과를 파일에 짝짓기 쉽게 하려는 변형이다(가설: expA의 H01 짝 맞춤 오류의 원인 후보).
- countline(실험 F): search_text 성공 출력 맨 앞에 "total matches: <전체 일치 줄 수>" 한 줄을 붙인다. 개수는 MAX_RESULTS로 잘리기 전의 실제 개수다.
- filename+countline: 둘 다 적용한다.
오류 결과(is_error)는 바꾸지 않는다. 동결 대상(도구 정의 v1의 이름, 기본 설명, 스키마)과 config 기본값은 건드리지 않는다.
"""
from typing import Any

OUTPUT_VARIANTS = ("default", "filename", "countline", "filename+countline")


def validate_output_variant(variant: str) -> None:
    if variant not in OUTPUT_VARIANTS:
        raise ValueError(f"unknown tool_output_variant: {variant} (allowed: {list(OUTPUT_VARIANTS)})")


def variant_parts(variant: str) -> set[str]:
    """변형 이름을 적용할 부분 변형의 집합으로 푼다(default는 빈 집합)."""
    validate_output_variant(variant)
    return set() if variant == "default" else set(variant.split("+"))


def _prepend(result: dict[str, Any], line: str) -> dict[str, Any]:
    first, *rest = result["content"]
    return {**result, "content": [{**first, "text": f"{line}\n{first['text']}"}, *rest]}


def apply_file_stats_output(variant: str, path: str, result: dict[str, Any]) -> dict[str, Any]:
    """file_stats 결과에 출력 변형을 적용한다. filename이 아니거나 오류 결과면 같은 객체를 그대로 돌려주고, 입력을 바꾸지 않는다."""
    if "filename" not in variant_parts(variant) or result.get("is_error") is True:
        return result
    return _prepend(result, f"path: {path}")


def apply_search_text_output(variant: str, total: int, result: dict[str, Any]) -> dict[str, Any]:
    """search_text 결과에 출력 변형을 적용한다. countline이 아니거나 오류 결과면 같은 객체를 그대로 돌려준다. total은 잘리기 전 전체 일치 줄 수."""
    if "countline" not in variant_parts(variant) or result.get("is_error") is True:
        return result
    return _prepend(result, f"total matches: {total}")
