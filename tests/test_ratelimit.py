from src.agent.ratelimit import delta, extract_windows


def test_extract_from_dict_and_missing():
    info = {"status": "allowed", "rate_limit_type": "five_hour", "resets_at": 1, "utilization": None,
            "raw": {"unifiedWindows": {"five_hour": {"utilization": 0.27}, "seven_day": {"utilization": 0.26}}}}
    w = extract_windows(info)
    assert w["five_hour"] == 0.27 and w["seven_day"] == 0.26 and w["utilization"] is None
    empty = extract_windows({"status": "allowed", "raw": {}})
    assert empty["five_hour"] is None and empty["seven_day"] is None


def test_delta():
    assert delta({"five_hour": 0.25, "seven_day": 0.26}, {"five_hour": 0.28, "seven_day": 0.26}) == {"five_hour": 0.03, "seven_day": 0.0}
    assert delta(None, {"five_hour": 0.1})["five_hour"] is None
