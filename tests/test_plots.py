"""src/eval/plots.py 테스트 (구현보다 먼저 작성). 합성 로그로 그림 파일이 만들어지는지, 제목에 표본 문구가 들어가는지,
그림에 쓰인 숫자가 로그에서 센 값과 같은지, 개인 경로가 새지 않는지, 입력(results/raw)을 바꾸지 않는지 확인한다. 모델 호출 없음.
"""
import hashlib
import json
import os
import re
from pathlib import Path

import pytest

from src.eval import loader, plots, report

TASKS = {t.id: t for t in loader.load_all() if not t.is_todo}
SEARCH = sorted(t.id for t in TASKS.values() if "search_text|Grep" in t.overlap_with)
FILE = sorted(t.id for t in TASKS.values() if "file_stats|Read" in t.overlap_with)
S_CUSTOM, F_CUSTOM, CHECK, GREP = "mcp__t__search_text", "mcp__t__file_stats", "mcp__t__check_result", "Grep"
PNG = b"\x89PNG\r\n\x1a\n"

PREFIX = {
    "default": "baseline_haiku_default", "short": "expA_haiku_short", "long": "expA_haiku_long", "long_directive": "expA_haiku_longDirective",
    "verify": "expB_haiku_verify", "verify_tool": "expB_haiku_verifyTool",
    "mt3": "expC_haiku_maxTurns3", "mt4": "expC_haiku_maxTurns4", "mt5": "expC_haiku_maxTurns5", "mt7": "expC_haiku_maxTurns7",
    "sonnet": "expD_sonnet_default",
    "e": "expE_haiku_longFilename", "ectl": "expEctl_haiku_long", "fctl": "expFctl_haiku_long", "f": "expF_haiku_longCountline",
}


def make(d: Path, col, task, run, rounds=(), *, passed=True, subtype="success", cost=0.01, tag=None):
    """rounds: 응답 하나당 [도구 이름 또는 (이름, 입력)] 목록."""
    rows = [{"kind": "config", "task_id": task, "config": {"model": "claude-haiku-5-5", "max_turns": 20}},
            {"kind": "message", "message": {"_type": "SystemMessage", "subtype": "init", "data": {"cwd": "C:/x", "tools": []}}}]
    n = 0
    for i, names in enumerate(rounds):
        for item in names:
            name, inp = item if isinstance(item, tuple) else (item, {})
            rows.append({"kind": "message", "message": {"_type": "AssistantMessage", "message_id": f"msg_{i}",
                                                        "content": [{"_type": "ToolUseBlock", "id": f"tu{n}", "name": name, "input": inp}]}})
            n += 1
    rows.append({"kind": "message", "message": {"_type": "AssistantMessage", "message_id": "msg_final", "content": [{"_type": "TextBlock", "text": "done"}]}})
    rows.append({"kind": "summary", "subtype": subtype, "is_error": subtype != "success", "num_turns": n + 1, "total_cost_usd": cost,
                 "usage": {"input_tokens": 10, "cache_creation_input_tokens": 100, "cache_read_input_tokens": 1000}, "exception": None,
                 "graded": {"passed": passed, "failure_type": "pass" if passed else "wrong_value"}})
    (d / f"{PREFIX[col]}_{task}_run{run}.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")


def fill(d, col, tasks=None, runs=3, **kw):
    for t in (tasks or sorted(TASKS)):
        for r in range(1, runs + 1):
            make(d, col, t, r, **kw)


E_TASKS = ["E03", "E10", "M09", "M10", "H01", "H02", "H04", "H08"]
F_TASKS = ["E01", "M01", "M05", "M07"]


@pytest.fixture
def raw(tmp_path):
    d = tmp_path / "raw"
    d.mkdir()
    for c in ("default", "short", "long", "long_directive"):
        for t in sorted(TASKS):
            for r in (1, 2, 3):
                st = [[S_CUSTOM]] if (t in SEARCH and c in ("long", "long_directive")) else [[GREP]] if t in SEARCH else [[F_CUSTOM]] if (t in FILE and c != "default") else [["Read"]]
                make(d, c, t, r, st)
    for c in ("verify", "verify_tool"):
        for t in sorted(TASKS):
            for r in (1, 2, 3):
                make(d, c, t, r, [[CHECK]] if c == "verify_tool" or r == 1 else [[GREP]])
    for c, mt in (("mt3", 3), ("mt4", 4), ("mt5", 5), ("mt7", 7)):
        for t in sorted(TASKS):
            for r in (1, 2, 3):
                bad = (mt == 3 and r == 1)
                make(d, c, t, r, [["Grep"]], subtype="error_max_turns" if bad else "success", passed=not bad or r == 2)
    for t in sorted(TASKS):
        make(d, "sonnet", t, 1, [["Grep"]], cost=0.1)
    for t in E_TASKS:
        for r in (1, 2, 3):
            make(d, "e", t, r, [[F_CUSTOM]], passed=(t != "H01" or r < 3))
    for r in (1, 2, 3):
        make(d, "ectl", "H01", r, [[F_CUSTOM]], passed=(r == 1))              # 같은 날 대조(expEctl)는 H01만: 1/3
    for t in F_TASKS:
        for r in range(1, 6):
            make(d, "fctl", t, r, [[S_CUSTOM]], passed=(r != 5))
            make(d, "f", t, r, [[S_CUSTOM, (GREP, {"output_mode": "count"})]])
    return d


@pytest.fixture
def out(tmp_path):
    return tmp_path / "figures"


def by_name(figs):
    return {f.name: f for f in figs}


# ---------------- 파일 생성과 제목 ----------------

def test_generate_all_creates_six_png_files_and_each_title_has_sample_text(raw, out):
    figs, skipped = plots.generate_all(raw, out, lang="en")
    assert [f.name for f in figs] == plots.FIGURE_NAMES and skipped == []
    assert plots.FIGURE_NAMES == ["fig1_expA_selection.png", "fig2_expB_check_result.png", "fig3_expC_pass_vs_normal.png",
                                  "fig4_expD_cost_responses.png", "fig5_expEF_pass_by_task.png", "fig6_consistency.png"]
    for f in figs:
        p = out / f.name
        assert p.is_file() and p.read_bytes().startswith(PNG) and f.path == p and p.stat().st_size > 2000
        assert re.search(r"N=\d+ tasks, .*total \d+ runs", f.title), f.title                    # 표본 크기: 과제 수, 과제당 횟수, 총 건수


def test_korean_titles_use_the_same_sample_label_rule_as_reports(raw, out):
    figs, _ = plots.generate_all(raw, out, lang="ko")
    t = by_name(figs)
    s_label = report.sample_label({x: 3 for x in SEARCH})
    f_label = report.sample_label({x: 3 for x in FILE})
    assert s_label in t["fig1_expA_selection.png"].title and f_label in t["fig1_expA_selection.png"].title
    assert report.sample_label({x: 3 for x in sorted(TASKS)}) in t["fig2_expB_check_result.png"].title
    for f in figs:
        assert re.search(r"N=\d+, 과제당 [\d~]+회.*총 \d+건", f.title), f.title


def test_sample_text_english_mirrors_the_korean_rule():
    assert plots.sample_text({"a": 3, "b": 3}, "en") == "N=2 tasks, 3 runs per task / total 6 runs"
    assert plots.sample_text({"a": 3, "b": 5}, "en") == "N=2 tasks, 3~5 runs per task (min 3) / total 8 runs"
    assert plots.sample_text({}, "en") == "N=0 tasks, 0 runs per task / total 0 runs"
    assert plots.sample_text({"a": 3, "b": 3}, "ko") == report.sample_label({"a": 3, "b": 3})


def test_small_sample_titles_get_a_warning_below_30_runs(raw, out):
    figs, _ = plots.generate_all(raw, out, lang="en")
    t = by_name(figs)
    assert "small sample" in t["fig5_expEF_pass_by_task.png"].title
    assert "small sample" not in t["fig2_expB_check_result.png"].title                                # 120건이면 경고 없음


# ---------------- 그림에 쓰인 숫자 ----------------

def test_fig1_selection_rates_come_from_logs(raw, out):
    figs, _ = plots.generate_all(raw, out, lang="en")
    d = by_name(figs)["fig1_expA_selection.png"].data
    assert list(d["search_text"]) == ["default", "short", "long", "long_directive"]
    assert d["search_text"]["default"] == (0, 3 * len(SEARCH)) and d["search_text"]["long"] == (3 * len(SEARCH), 3 * len(SEARCH))
    assert d["file_stats"]["default"] == (0, 3 * len(FILE)) and d["file_stats"]["short"] == (3 * len(FILE), 3 * len(FILE))


def test_fig2_check_result_use_rate_per_config(raw, out):
    d = by_name(plots.generate_all(raw, out, lang="en")[0])["fig2_expB_check_result.png"].data["check_result"]
    assert list(d) == ["default", "verify", "verify_tool"]
    assert d["default"] == (0, 120) and d["verify_tool"] == (120, 120) and d["verify"] == (40, 120)


def test_fig3_pass_rate_and_normal_termination_rate_lines(raw, out):
    d = by_name(plots.generate_all(raw, out, lang="en")[0])["fig3_expC_pass_vs_normal.png"].data
    assert d["x"] == [3, 4, 5, 7, 20]
    assert d["pass"][20] == (120, 120) and d["normal"][20] == (120, 120)                               # 20 = baseline default
    assert d["normal"][3] == (80, 120) and d["normal"][7] == (120, 120)                                # max_turns 3: run1 40건이 error_max_turns
    assert d["pass"][3] == (80, 120)                                                                   # 그 40건은 채점도 실패


def test_fig4_uses_only_common_pairs_and_means(raw, out):
    d = by_name(plots.generate_all(raw, out, lang="en")[0])["fig4_expD_cost_responses.png"].data
    assert d["pairs"] == 40 and d["scale"] == "log"
    assert d["cost"]["haiku"] == pytest.approx(0.01) and d["cost"]["sonnet"] == pytest.approx(0.1)
    assert d["responses"]["haiku"] == pytest.approx(2.0) and d["responses"]["sonnet"] == pytest.approx(2.0)


def test_fig5_pass_counts_per_task_for_e_and_f(raw, out):
    d = by_name(plots.generate_all(raw, out, lang="en")[0])["fig5_expEF_pass_by_task.png"].data
    # E 패널의 주 비교 = 같은 날 대조 expEctl 대 expE (H01만)
    assert set(d["E"]) == {"expEctl", "long_filename"} and set(d["E"]["expEctl"]) == {"H01"}
    assert d["E"]["expEctl"]["H01"] == (1, 3) and d["E"]["long_filename"]["H01"] == (2, 3)
    # 보조 = 3일 전 expA long 대 expE (8과제)
    assert set(d["E_aux"]) == {"long", "long_filename"} and set(d["E_aux"]["long"]) == set(E_TASKS)
    assert d["E_aux"]["long"]["E03"] == (3, 3) and d["E_aux"]["long_filename"]["H01"] == (2, 3)
    assert d["F"]["long"]["M01"] == (4, 5) and d["F"]["long_countline"]["M01"] == (5, 5) and set(d["F"]["long"]) == set(F_TASKS)


def test_fig5_e_main_panel_is_titled_with_the_main_comparison_and_keeps_sample_sizes(raw, out):
    f = by_name(plots.generate_all(raw, out, lang="en")[0])["fig5_expEF_pass_by_task.png"]
    assert "expEctl vs expE" in f.title and "auxiliary" in f.title
    assert f.panel_titles["E"].startswith("Experiment E main") and "N=1 tasks, 3 runs per task / total 3 runs" in f.panel_titles["E"]
    assert "auxiliary" in f.panel_titles["E_aux"] and "N=8 tasks, 3 runs per task / total 24 runs" in f.panel_titles["E_aux"]
    assert "N=4 tasks, 5 runs per task / total 20 runs" in f.panel_titles["F"]


def test_fig5_without_expEctl_logs_still_draws_the_auxiliary_e_panel(raw, out):
    for p in raw.glob("expEctl_*"):
        p.unlink()
    d = by_name(plots.generate_all(raw, out, lang="en")[0])["fig5_expEF_pass_by_task.png"].data
    assert "E" not in d and "E_aux" in d and "F" in d


def test_fig6_consistency_rates_per_config(raw, out):
    d = by_name(plots.generate_all(raw, out, lang="en")[0])["fig6_consistency.png"].data
    assert list(d["order"]) == ["default", "short", "long", "long_directive", "verify", "verify_tool"]
    pairs = 3 * len(TASKS)                                                                             # 과제당 3회 -> 쌍 3개
    assert d["order"]["default"] == (pairs, pairs) and d["args"]["default"] == (pairs, pairs)         # 합성 로그는 매번 같은 도구 순서와 인자


# ---------------- 누락, 폰트, 개인정보, 읽기 전용 ----------------

def test_missing_experiments_are_skipped_with_a_reason_not_a_crash(tmp_path, out):
    d = tmp_path / "raw"
    d.mkdir()
    for c in ("default", "short"):
        fill(d, c, None, 3, rounds=[[S_CUSTOM]])
    figs, skipped = plots.generate_all(d, out, lang="en")
    names = [f.name for f in figs]
    assert "fig1_expA_selection.png" in names and "fig6_consistency.png" in names and "fig2_expB_check_result.png" not in names
    assert len(skipped) == 4
    assert any("fig2_expB_check_result.png" in s for s in skipped) and any("fig4_expD_cost_responses.png" in s for s in skipped)
    assert not (out / "fig2_expB_check_result.png").exists()


def test_empty_input_returns_nothing_and_main_exits_1(tmp_path):
    d = tmp_path / "raw"
    d.mkdir()
    figs, skipped = plots.generate_all(d, tmp_path / "o", lang="en")
    assert figs == [] and len(skipped) == 6
    assert plots.main(["--raw-dir", str(d), "--out-dir", str(tmp_path / "o")]) == 1


def test_font_detection_falls_back_to_english_labels():
    assert plots.detect_lang(["DejaVu Sans", "Arial"]) == ("en", None)
    assert plots.detect_lang(["DejaVu Sans", "Malgun Gothic"]) == ("ko", "Malgun Gothic")
    assert plots.detect_lang(["NanumGothic"]) == ("ko", "NanumGothic")
    assert plots.detect_lang([]) == ("en", None)


def test_png_and_sources_contain_no_personal_paths_or_user_names(raw, out, tmp_path):
    plots.generate_all(raw, out, lang="en")
    user = os.path.basename(os.path.expanduser("~")).lower()
    needles = [str(tmp_path).lower().encode(), str(tmp_path).replace("\\", "/").lower().encode(), b"c:\\users", b"c:/users"]
    if len(user) >= 4:
        needles.append(user.encode())
    for p in out.glob("*.png"):
        data = p.read_bytes().lower()
        for n in needles:
            assert n not in data, (p.name, n)
    src = Path(plots.__file__).read_text(encoding="utf-8").lower()
    assert "c:\\users" not in src and "c:/users" not in src and (len(user) < 4 or user not in src)
    for f in plots.generate_all(raw, out, lang="en")[0]:
        assert str(tmp_path).lower() not in f.title.lower()


def test_generation_is_read_only_for_input_and_writes_only_to_out_dir(raw, out):
    def snap():
        return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in raw.rglob("*") if p.is_file()}
    before = snap()
    plots.generate_all(raw, out, lang="en")
    assert snap() == before
    assert sorted(p.name for p in out.iterdir()) == sorted(plots.FIGURE_NAMES)


def test_main_writes_into_the_requested_folder_and_lists_files(raw, out, capsys):
    assert plots.main(["--raw-dir", str(raw), "--out-dir", str(out), "--lang", "en"]) == 0
    printed = capsys.readouterr().out
    for name in plots.FIGURE_NAMES:
        assert name in printed and (out / name).is_file()
    assert plots.DEFAULT_OUT_DIR == "results/figures" and plots.DEFAULT_RAW_DIR == "results/raw"


def test_single_config_is_not_enough_for_a_comparison_figure(tmp_path, out):
    d = tmp_path / "raw"
    d.mkdir()
    fill(d, "default", None, 3, rounds=[[GREP]])                                  # 설정 하나뿐이면 비교 그림(fig1)을 만들지 않는다
    figs, skipped = plots.generate_all(d, out, lang="en")
    assert "fig1_expA_selection.png" not in [f.name for f in figs] and any("fig1_expA_selection.png" in s for s in skipped)
