"""포트폴리오 공개 전 점검: README 구조, 30초 요약, 면접 노트, 링크, 개인정보 스캔.

개인정보 값(사용자 이름, 홈 경로, 이메일, 연결됐던 외부 서비스 이름)은 이 파일에 적지 않고 실행 시점에 환경에서 읽거나
문자열을 쪼개 만든다. 실패 메시지에는 값이 아니라 파일:줄만 넣는다.
"""
import getpass
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SELF = "tests/test_portfolio_ready.py"
READMES = {"README.md": ("## 30초 요약", "## 목차"), "README.en.md": ("## 30-second summary", "## Contents")}
FIGS = ["fig1_expA_selection.png", "fig2_expB_check_result.png", "fig3_expC_pass_vs_normal.png", "fig4_expD_cost_responses.png",
        "fig5_expEF_pass_by_task.png", "fig6_consistency.png"]
SAMPLE = re.compile(r"N=\d+|\d+/\d+|\d+건|\d+ runs|\d+ tasks|\d+ x \d+")      # 표본 크기 표시


def read(name):
    return (ROOT / name).read_text(encoding="utf-8")


def section(text, heading):
    a = text.index(heading)
    rest = text[a + len(heading):]
    m = re.search(r"\n## ", rest)
    return rest[:m.start()] if m else rest


# ---------------- 30초 요약 ----------------

@pytest.mark.parametrize("name", list(READMES))
def test_30sec_summary_is_at_the_top_and_at_most_10_lines(name):
    text = read(name)
    head, toc = READMES[name]
    assert head in text and toc in text
    assert text.index(head) < text.index(toc) < text.index("\n## ", text.index(toc) + 5)   # 요약 -> 목차 -> 나머지 순서
    first_h2 = text.index("\n## ")
    assert text.index(head) == first_h2 + 1                                            # 첫 번째 절이 요약
    lines = [ln for ln in section(text, head).split("\n") if ln.strip()]
    assert 6 <= len(lines) <= 10, len(lines)


@pytest.mark.parametrize("name", list(READMES))
def test_30sec_summary_has_three_findings_and_limits(name):
    lines = [ln for ln in section(read(name), READMES[name][0]).split("\n") if ln.strip()]
    key = ("- 발견", "- 한계") if name == "README.md" else ("- Finding", "- Limit")
    assert len([ln for ln in lines if ln.startswith(key[0])]) == 3
    assert len([ln for ln in lines if ln.startswith(key[1])]) >= 1


@pytest.mark.parametrize("name", list(READMES))
def test_30sec_summary_every_number_carries_a_sample_size(name):
    for ln in section(read(name), READMES[name][0]).split("\n"):
        if re.search(r"\d+%|\d+(\.\d+)?배|x\d|\$\d", ln):
            assert SAMPLE.search(ln), ln


@pytest.mark.parametrize("name", list(READMES))
def test_30sec_summary_only_uses_numbers_found_in_results_md(name):
    results = read("docs/results.md")
    for ln in section(read(name), READMES[name][0]).split("\n"):
        for pct, frac in re.findall(r"(\d+)% \((\d+/\d+)\)", ln):
            assert f"{pct}% ({frac})" in results, (pct, frac)                     # 새로 만든 수치 금지


@pytest.mark.parametrize("name", list(READMES))
def test_30sec_summary_avoids_stronger_words_than_measured(name):
    body = section(read(name), READMES[name][0])
    for bad in ["정확도", "개선됐", "향상", "좋아", "accuracy", "improved", "better"]:
        assert bad not in body, bad
    assert "채점 통과율" in body or "grading pass rate" in body


# ---------------- README 구조 ----------------

@pytest.mark.parametrize("name", list(READMES))
def test_readme_has_author_and_linkedin(name):
    text = read(name)
    assert "신민결" in text
    assert "LinkedIn" in text
    # 주소를 받지 못했으면 자리표시자("확인 불가")로 두고, 받았으면 linkedin.com 주소여야 한다
    assert "linkedin.com/" in text or "확인 불가" in text or "unknown" in text


@pytest.mark.parametrize("name,head", [("README.md", "## 핵심 발견"), ("README.en.md", "## Key findings")])
def test_readme_key_findings_at_most_5_each_with_sample_size(name, head):
    items = [ln for ln in section(read(name), head).split("\n") if ln.startswith("- ")]
    assert 3 <= len(items) <= 5
    for ln in items:
        assert SAMPLE.search(ln), ln


@pytest.mark.parametrize("name,head", [("README.md", "## 실험 A~F 한눈에"), ("README.en.md", "## Experiments A-F at a glance")])
def test_readme_experiment_table_lists_a_to_f_and_six_figures(name, head):
    sec = section(read(name), head)
    rows = [ln for ln in sec.split("\n") if ln.startswith("| ") and not ln.startswith("| ---") and not ln.startswith("|---")]
    for exp in "ABCDEF":
        assert any(re.match(rf"\| {exp} \|", r) for r in rows), exp
    for f in FIGS:
        assert f"results/figures/{f}" in sec, f


@pytest.mark.parametrize("name,heads", [("README.md", ["## 설계 원칙", "## 한계", "## 재현 방법"]),
                                        ("README.en.md", ["## Design principles", "## Limitations", "## Reproduce"])])
def test_readme_has_design_principles_limitations_and_reproduction(name, heads):
    text = read(name)
    for h in heads:
        assert h in text, h


def test_readme_reproduction_mentions_clone_install_test_and_login_only_auth():
    sec = section(read("README.md"), "## 재현 방법")
    for token in ["git clone", "pip install -r requirements.txt", "pytest", "claude login", "freeze --verify"]:
        assert token in sec, token
    assert "ANTHROPIC_API_KEY" in sec and "설정하지" in sec                          # 키는 설정하지 않는다는 안내


# ---------------- 면접 노트 ----------------

def test_interview_notes_has_15_questions_and_q14_is_a_placeholder():
    text = read("docs/interview_notes.md")
    qs = re.findall(r"^## (\d+)\. .*$", text, flags=re.M)
    assert qs == [str(i) for i in range(1, 16)]
    parts = re.split(r"^## \d+\. ", text, flags=re.M)[1:]
    for i, p in enumerate(parts, 1):
        if i == 14:
            assert "여기를 직접 작성" in p
        else:
            assert "여기를 직접 작성" not in p and len(p.strip()) > 60, i


def test_interview_notes_numbers_carry_sample_sizes_and_mark_unknowns():
    text = read("docs/interview_notes.md")
    for ln in text.split("\n"):
        if re.search(r"\d+% \(", ln):
            assert SAMPLE.search(ln), ln
    assert "확인 불가" in text or "가설" in text


# ---------------- 링크 ----------------

LINK = re.compile(r"\]\(([^)\s]+)\)")


def md_files():
    return [ROOT / "README.md", ROOT / "README.en.md", *sorted((ROOT / "docs").glob("*.md"))]


def test_all_relative_links_in_readme_and_docs_resolve():
    bad = []
    for f in md_files():
        for i, ln in enumerate(f.read_text(encoding="utf-8").split("\n"), 1):
            for target in LINK.findall(ln):
                if target.startswith(("http://", "https://", "mailto:", "#")):
                    continue
                path = target.split("#")[0]
                if path and not (f.parent / path).exists():
                    bad.append(f"{f.relative_to(ROOT)}:{i}")
    assert not bad, bad


def test_markdown_anchors_in_same_file_exist():
    def slug(h):
        s = re.sub(r"[^\w\- ]", "", h.strip().lower())                       # GitHub 방식: 기호 제거, 공백 하나마다 하이픈
        return s.replace(" ", "-")
    bad = []
    for f in [ROOT / "README.md", ROOT / "README.en.md"]:
        text = f.read_text(encoding="utf-8")
        slugs = {slug(m) for m in re.findall(r"^#{1,6} (.+)$", text, flags=re.M)}
        for i, ln in enumerate(text.split("\n"), 1):
            for a in re.findall(r"\]\(#([^)\s]+)\)", ln):
                if a not in slugs:
                    bad.append(f"{f.name}:{i}")
    assert not bad, bad


def test_readme_links_to_every_figure_and_results_md_from_both_languages():
    for name in READMES:
        text = read(name)
        assert "docs/results.md" in text
        for f in FIGS:
            assert f"results/figures/{f}" in text and (ROOT / "results" / "figures" / f).is_file(), f


# ---------------- 개인정보 스캔 ----------------

def _git(*args):
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def _tracked():
    out = _git("ls-files")
    if out is None:
        pytest.skip("git 저장소가 아님")
    return [f for f in out.split("\n") if f and f != SELF]


def _terms():
    home = Path.home()
    g = _git("config", "--global", "user.email") or ""
    local = g.strip().split("@")[0]
    return {
        "user": [getpass.getuser(), home.name],
        "homepath": [str(home), str(home).replace("\\", "/"), str(home).replace("\\", "\\\\")],
        "email": [local + "@"] if local else [],
        # 서비스 이름은 이 파일 자체가 스캔에 걸리지 않게 쪼개 쓴다
        "service": ["Coin" + "Gecko", "Crypto" + ".com", "Gm" + "ail", "Google " + "Drive", "Can" + "va", "Lunar" + "Crush", "Twelve " + "Data",
                    "Google " + "Calendar"],
    }


@pytest.mark.parametrize("kind", ["user", "homepath", "email", "service"])
def test_no_personal_value_in_tracked_text_files(kind):
    terms = [t.lower() for t in _terms()[kind] if t]
    hits = []
    for f in _tracked():
        p = ROOT / f
        if not p.is_file() or f.lower().endswith(".png"):
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for i, ln in enumerate(text.split("\n"), 1):
            if any(t in ln.lower() for t in terms):
                hits.append(f"{f}:{i}")
    assert not hits, hits


def test_png_files_have_no_text_metadata_chunks():
    bad = []
    for f in _tracked():
        if f.lower().endswith(".png"):
            data = (ROOT / f).read_bytes()
            if any(tag in data for tag in (b"tEXt", b"iTXt", b"zTXt", b"eXIf")):
                bad.append(f)
    assert not bad, bad


def test_png_files_do_not_contain_personal_values_in_raw_bytes():
    terms = [t.lower().encode() for k in ("user", "homepath", "email") for t in _terms()[k] if t]
    bad = [f for f in _tracked() if f.lower().endswith(".png") and any(t in (ROOT / f).read_bytes().lower() for t in terms)]
    assert not bad, bad


# Day 1, Day 2 커밋 2개는 noreply가 아닌 주소로 만들어졌다(이미 푸시된 히스토리라 다시 쓰지 않고 해시로 명시해 예외 처리).
# 이 PC의 git 설정이 아니라 히스토리를 검사하므로 새 클론에서도 같은 결과가 나온다.
LEGACY_NON_NOREPLY = {"16ba9bc9304dffd790af1c2c04079a6e27ecfed8", "46b3399627c7676bea60edad4170329c821c2180"}


def test_every_commit_author_is_noreply_except_the_two_known_legacy_commits():
    out = _git("log", "--format=%H %ae")
    if out is None:
        pytest.skip("git 저장소가 아님")
    bad = [ln.split()[0][:7] for ln in out.strip().split("\n")
           if ln and ln.split()[0] not in LEGACY_NON_NOREPLY and not ln.split()[1].endswith("@users.noreply.github.com")]
    assert not bad, bad                                                                # 값은 출력하지 않고 해시 앞 7자리만


def test_legacy_non_noreply_commits_are_exactly_the_known_two_if_history_is_unrewritten():
    out = _git("log", "--format=%H %ae")
    if out is None:
        pytest.skip("git 저장소가 아님")
    found = {ln.split()[0] for ln in out.strip().split("\n") if ln and not ln.split()[1].endswith("@users.noreply.github.com")}
    assert found <= LEGACY_NON_NOREPLY
