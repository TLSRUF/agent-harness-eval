"""Day 17: README 보완과 강한 표현 수정을 고정하는 테스트 (수정보다 먼저 작성).

- 작성자 줄과 LinkedIn 주소
- 30초 요약 발견 1 = search_text 선택률(숫자는 results_summary.py가 만든 docs/results.md와 같아야 한다)
- "성공률"(채점 통과율을 가리키는 곳), "정확도", accuracy, 올랐다/떨어졌다/훨씬/much, 안정화, 우연 범위 안 표현 금지
모델 호출 없음. results/raw가 없으면 로그 대조 테스트는 건너뛴다.
"""
import re
from pathlib import Path

import pytest

from src.eval import loader, results_summary as rs

ROOT = Path(__file__).resolve().parent.parent
LINKEDIN = "https://www.linkedin.com/in/%EB%AF%BC%EA%B2%B0-%EC%8B%A0-8878ba406/"
TASKS = {t.id: t for t in loader.load_all() if not t.is_todo}


def read(name):
    return (ROOT / name).read_text(encoding="utf-8")


def summary_line(name, key):
    head = "## 30초 요약" if name == "README.md" else "## 30-second summary"
    text = read(name)
    sec = text[text.index(head):]
    sec = sec[:sec.index("\n## ", 5)]
    return next(ln for ln in sec.split("\n") if ln.startswith(key))


def section(text, heading):
    a = text.index(heading)
    rest = text[a + len(heading):]
    m = re.search(r"\n## ", rest)
    return rest[:m.start()] if m else rest


# ---------------- 1. 작성자 줄, LinkedIn ----------------

def test_author_line_ko_and_en_with_linkedin_url():
    ko, en = read("README.md").split("\n"), read("README.en.md").split("\n")
    ko_line = next(ln for ln in ko if ln.startswith("작성자"))
    en_line = next(ln for ln in en if ln.startswith("Author"))
    assert ko_line.startswith("작성자: 신민결") and "Shin" not in ko_line.split("LinkedIn")[0]
    assert en_line.startswith("Author: Shin Min-gyeol (신민결)")
    for ln in (ko_line, en_line):
        assert LINKEDIN in ln
        assert "확인 불가" not in ln and "unknown" not in ln and "입력 필요" not in ln


# ---------------- 1. 발견 1 = search_text 선택률 ----------------

def _row(results, label):
    for ln in results.split("\n"):
        if ln.startswith(f"| {label} |"):
            return [c.strip() for c in ln.strip().strip("|").split("|")]
    raise AssertionError(label)


def _ab_rows(text):
    """docs/results.md 실험 A 표의 search_text 선택률, Grep 사용률 행 (default, short, long, long_directive 순)."""
    a = text[text.index("## 실험 A"):text.index("## 실험 B")]
    return _row(a, "search_text 선택률")[1:5], _row(a, "Grep 사용률")[1:5]


@pytest.mark.parametrize("name", ["README.md", "README.en.md"])
def test_finding_1_is_search_text_selection_with_grep_use_and_sample(name):
    ln = summary_line(name, "- 발견 1" if name == "README.md" else "- Finding 1")
    for s in ("0% (0/36)", "14% (5/36)", "28% (10/36)", "86% (31/36)", "75% (27/36)", "N=12"):
        assert s in ln, s
    assert "search_text" in ln and "Grep" in ln
    assert ln.index("search_text") < ln.index("file_stats")                    # file_stats는 보조 문장으로 내려간다
    assert "62% (15/24)" in ln and "100% (24/24)" in ln and "30" in ln          # 보조 문장도 표본 크기와 경고를 유지
    assert "N=8" in ln


@pytest.mark.parametrize("name", ["README.md", "README.en.md"])
def test_finding_1_numbers_equal_the_numbers_in_generated_results_md(name):
    sel, grep = _ab_rows(read("docs/results.md"))
    ln = summary_line(name, "- 발견 1" if name == "README.md" else "- Finding 1")
    for cell in (sel[0], sel[1], sel[2], sel[3], grep[0], grep[3]):             # default, short, long, long_directive / Grep default, long_directive
        assert cell in ln, (cell, ln)


def test_finding_1_numbers_equal_the_numbers_results_summary_computes_from_real_logs():
    raw = ROOT / "results" / "raw"
    if not any(raw.glob("baseline_haiku_default_H01_run1.jsonl")):
        pytest.skip("results/raw 로그가 없다(gitignore 대상)")
    sel, grep = _ab_rows(rs.build(raw, TASKS))
    assert sel == ["0% (0/36)", "0% (0/36)", "14% (5/36)", "28% (10/36)"]
    assert grep[0] == "86% (31/36)" and grep[3] == "75% (27/36)"
    assert (sel, grep) == _ab_rows(read("docs/results.md"))                      # 커밋된 문서가 생성기 출력과 같다


def test_limits_say_repeats_of_the_same_task_are_not_independent():
    ko = section(read("README.md"), "## 한계")
    en = section(read("README.en.md"), "## Limitations")
    assert "같은 과제의 3회 반복은 서로 독립이 아니다" in ko
    assert "not independent" in en and "3 runs" in en


# ---------------- 2. 강한 표현 ----------------

STRONG_KO = ["올랐", "올리", "오른", "떨어", "훨씬", "정확도", "안정화"]
DOCS = ["README.md", "README.en.md", "docs/results.md", "docs/interview_notes.md"]


@pytest.mark.parametrize("name", DOCS)
def test_no_stronger_words_than_measured(name):
    text = read(name)
    for w in STRONG_KO:
        assert w not in text, (name, w)
    assert not re.search(r"\bmuch\b", text, flags=re.I), name
    assert not re.search(r"accuracy|accurate", text, flags=re.I), name
    assert not re.search(r"stabili[sz]es", text, flags=re.I), name


@pytest.mark.parametrize("name", ["README.md", "docs/results.md", "docs/interview_notes.md"])
def test_korean_docs_call_the_pass_rate_a_grading_pass_rate(name):
    text = read(name)
    assert "성공률" not in text, name


def test_english_readme_does_not_call_the_pass_rate_success():
    text = read("README.en.md")
    assert not re.search(r"\bsuccess\b", text, flags=re.I), "success"             # successful/succeeded(쓰기 성공)는 해당 없음
    assert "grading pass rate" in text


def test_correctness_is_stated_as_not_measured():
    assert "정확성은 측정하지 않았다" in read("README.md")
    assert "정확성은 측정하지 않았다" in read("docs/results.md")
    assert "Correctness was not measured" in read("README.en.md")


def test_consistency_claim_is_an_observation_with_the_cause_marked_as_hypothesis():
    ko = next(ln for ln in read("README.md").split("\n") if ln.startswith("- 관찰(일관성)"))
    assert "순서 일치 비율이 49% (59/120쌍)에서 71% (85/120쌍)으로 높게 관찰됨(원인은 가설)" in ko
    en = next(ln for ln in read("README.en.md").split("\n") if ln.startswith("- Observed (consistency)"))
    assert "49% (59/120 pairs)" in en and "71% (85/120 pairs)" in en
    assert "observed higher" in en and "cause is a hypothesis" in en
    for ln in (ko, en):
        assert "우연 범위와의 비교" not in ln or "하지 않았다(확인 불가)" in ln


def test_results_md_does_not_claim_the_difference_is_within_chance():
    text = read("docs/results.md")
    assert "우연 범위 안이다" not in text
    assert "우연 범위와의 비교는 하지 않았다(확인 불가)" in text


# ---------------- 생성기 (results_summary.py) ----------------

def test_generator_uses_grading_pass_rate_and_never_the_old_words(tmp_path):
    from test_results_summary import fill_all_experiments, fill_f
    fill_all_experiments(tmp_path)
    fill_f(tmp_path)
    text = rs.build(tmp_path, TASKS)
    assert "채점 통과율" in text
    assert "정확성은 측정하지 않았다" in text
    for w in ["성공률", "정확도", "올랐", "올리", "오른", "떨어", "훨씬", "우연 범위 안이다"]:
        assert w not in text, w
    assert "| 채점 통과율 |" in text


def test_generator_keeps_identifiers_such_as_failure_type_and_error_max_turns(tmp_path):
    from test_results_summary import fill_all_experiments, fill_f
    fill_all_experiments(tmp_path)
    fill_f(tmp_path)
    text = rs.build(tmp_path, TASKS)
    assert "error_max_turns" in text and "search_text 선택률" in text and "check_result 사용률" in text
