"""구독 한도(RateLimitEvent) 사용률 추출/기록 보조.

주의: utilization은 이 실험만의 사용량이 아니라 구독 전체 사용량이다.
다른 작업(채팅, 개발)이 섞이면 값이 오염되므로, 과제 단위 델타는 참고값일 뿐이다.
RateLimitEvent는 '한도 상태가 바뀔 때' 발행되어 실행당 1개일 수 있다(관찰값, 문서상 보장 아님).
"""
from __future__ import annotations

from typing import Any


def extract_windows(info: Any) -> dict[str, Any]:
    """RateLimitInfo(dataclass 또는 dict)에서 기록할 값만 뽑는다. 없는 값은 None."""
    get = (lambda k: info.get(k)) if isinstance(info, dict) else (lambda k: getattr(info, k, None))
    raw = get("raw") or {}
    windows = raw.get("unifiedWindows") or {}
    return {
        "status": get("status"),
        "rate_limit_type": get("rate_limit_type"),
        "resets_at": get("resets_at"),
        "utilization": get("utilization"),  # 이벤트가 대표하는 창의 값 (없으면 None)
        "five_hour": (windows.get("five_hour") or {}).get("utilization"),
        "seven_day": (windows.get("seven_day") or {}).get("utilization"),
    }


def delta(a: dict[str, Any] | None, b: dict[str, Any] | None) -> dict[str, float | None]:
    """b - a. 어느 한쪽이 없으면 None."""
    out: dict[str, float | None] = {}
    for k in ("five_hour", "seven_day"):
        x, y = (a or {}).get(k), (b or {}).get(k)
        out[k] = None if x is None or y is None else round(y - x, 6)
    return out
