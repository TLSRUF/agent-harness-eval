"""줄/단어 세기 정의 일치 테스트: 같은 파일을 세 경로로 세서 같아야 한다.

세 경로
1. fixture 생성기(fixtures/_gen/gen_fixtures.py)의 count_lines/count_words  (줄바꿈 개수, 정규식 분리)
2. 독립 검증 스크립트(src/eval/verify_counts.py)의 count_lines/count_words  (바이트 단위 줄 수, \\S+ 덩어리)
3. 에이전트가 쓰는 file_stats 도구 (str.splitlines, str.split)  -- 도구 정의 v1이라 이 테스트는 수정하지 않고 관찰만 한다.

기준 정의: 단어 = 공백으로 구분되는 덩어리, 줄 수 = 끝 줄바꿈 기준(LF/CRLF).
알려진 차이: file_stats는 str.splitlines()라서 낱개 CR, U+2028, U+0085, \\x0b, \\x0c, \\x1c 등 '특수 줄 구분 문자'도 줄바꿈으로 센다.
다른 두 경로는 \\n만 센다. 실제 fixture에는 이런 문자가 없으므로 과제 정답에는 영향이 없다(아래 테스트가 확인).
"""
import importlib.util
import re
from pathlib import Path

import pytest

from src.agent.tools import file_stats_impl
from src.eval import loader, verify_counts

GEN_PATH = loader.FIXTURES_DIR / "_gen" / "gen_fixtures.py"
spec = importlib.util.spec_from_file_location("gen_fixtures_for_test", GEN_PATH)
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)


def three_counts(tmp_path: Path, data: bytes):
    p = tmp_path / "t.txt"
    p.write_bytes(data)
    text = data.decode("utf-8")
    g = (gen.count_lines(text), gen.count_words(text))
    v = (verify_counts.count_lines(p), verify_counts.count_words(p))
    m = re.match(r"lines=(\d+) words=(\d+)", file_stats_impl(tmp_path, "t.txt")["content"][0]["text"])
    return g, v, (int(m.group(1)), int(m.group(2)))


AGREE = {
    "정상": b"a b\nc\n",
    "한 줄": b"x\n",
    "빈 파일": b"",
    "연속 공백/탭": b"a  b\t c\n",
    "한국어": "한 글 단어\n두 번째 줄\n".encode("utf-8"),
    "끝 줄바꿈 없음": b"a b\nc",
    "CRLF": b"a b\r\nc\r\n",
    "중간 빈 줄": b"a\n\nb\n",
    "끝 빈 줄 둘": b"a\nb\n\n",
    "NBSP 단어 구분": "a b c\n".encode("utf-8"),
    "전각 공백 단어 구분": "a b c\n".encode("utf-8"),
    "소수/숫자 덩어리": b"3.5 4,000 -7 a-b\n",
}

# file_stats만 줄 수가 다른 사례 (알려진 차이). 단어 수는 모든 사례에서 세 경로가 같다.
LINE_DIVERGENCE = {
    "낱개 CR": b"a\rb\r",
    "U+2028": "a b\n".encode("utf-8"),
    "U+0085": "a\u0085b\n".encode("utf-8"),
    "VT": b"a\x0bb\n",
    "FF": b"a\x0cb\n",
    "FS": b"a\x1cb\n",
}


@pytest.mark.parametrize("label", sorted(AGREE))
def test_three_paths_agree_on_normal_files(tmp_path, label):
    g, v, f = three_counts(tmp_path, AGREE[label])
    assert g == v == f, (label, g, v, f)


@pytest.mark.parametrize("label", sorted(LINE_DIVERGENCE))
def test_known_line_divergence_is_documented_not_silent(tmp_path, label):
    """file_stats만 줄 수가 다르다는 사실을 고정한다. file_stats가 바뀌면 이 테스트가 깨져 문서 갱신을 요구한다."""
    g, v, f = three_counts(tmp_path, LINE_DIVERGENCE[label])
    assert g == v, (label, g, v)            # 생성기와 verify_counts는 서로 같다
    assert g[1] == v[1] == f[1]             # 단어 수는 세 경로가 같다
    assert f[0] > g[0], (label, g, f)       # file_stats만 줄을 더 센다


def three_byte_counts(tmp_path: Path, data: bytes):
    """바이트 수를 세 경로로 센다: 생성기 쪽(len(text.encode)), verify_counts(len(read_bytes)), file_stats 도구(st_size)."""
    p = tmp_path / "t.txt"
    p.write_bytes(data)
    g = len(data.decode("utf-8").encode("utf-8"))
    v = verify_counts.count_bytes(p)
    m = re.search(r"bytes=(\d+)", file_stats_impl(tmp_path, "t.txt")["content"][0]["text"])
    return g, v, int(m.group(1))


@pytest.mark.parametrize("label,data", [
    ("ascii", b"abc\n"), ("빈 파일", b""), ("한글(3바이트 문자)", "한글 텍스트\n".encode("utf-8")), ("한글과 ASCII", "가a나b\n".encode("utf-8")),
    ("CRLF(줄바꿈 2바이트)", b"a\r\nb\r\n"), ("끝 줄바꿈 없음", "한글".encode("utf-8"))])
def test_byte_counts_agree_across_three_paths(tmp_path, label, data):
    g, v, f = three_byte_counts(tmp_path, data)
    assert g == v == f == len(data), (label, g, v, f)


def test_byte_counts_agree_on_every_fixture_file(tmp_path):
    """H08이 바이트 수를 비교하므로 모든 fixture 파일에서 세 경로의 바이트 수가 같아야 한다."""
    for path in M_FILES:
        g, v, f = three_byte_counts(tmp_path, path.read_bytes())
        assert g == v == f == path.stat().st_size, path


def test_words_agree_even_with_exotic_whitespace(tmp_path):
    for data in (b"a\x1cb c\n", "a b c\n".encode("utf-8"), "a\u0085b\n".encode("utf-8"), b"a\x0bb\x0cc\n"):
        g, v, f = three_counts(tmp_path, data)
        assert g[1] == v[1] == f[1], (data, g, v, f)


M_FILES = sorted(p for d in loader.FIXTURES_DIR.glob("[EMH][0-9][0-9]") for p in d.iterdir() if p.is_file() and p.name != ".gitkeep")  # 쉬움/보통/어려움 전체


@pytest.mark.parametrize("path", M_FILES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_three_paths_agree_on_every_fixture_file(tmp_path, path):
    data = path.read_bytes()
    g, v, f = three_counts(tmp_path, data)
    assert g == v == f, (path, g, v, f)


def test_fixtures_have_no_exotic_line_separators():
    """알려진 차이가 실제 fixture에서는 발동하지 않는다는 확인."""
    exotic = re.compile("[\r  \u0085\x0b\x0c\x1c\x1d\x1e]")
    bad = [str(p) for p in M_FILES if exotic.search(p.read_bytes().decode("utf-8"))]
    assert bad == []


def test_scan_covers_every_task_fixture_folder():
    """fixtures 아래 폴더는 과제 ID(E/M/H + 두 자리) 또는 _gen뿐이고, 모든 과제 fixture가 위 검사(세 경로 일치, 특수 줄 구분 문자 없음)에 들어간다."""
    names = [d.name for d in loader.FIXTURES_DIR.iterdir() if d.is_dir()]
    assert all(n == "_gen" or re.fullmatch(r"[EMH]\d\d", n) for n in names), names
    scanned = {p.parent.name for p in M_FILES}
    for t in loader.load_all():
        if not t.is_todo:
            real = [p for p in t.fixture_dir.iterdir() if p.is_file() and p.name != ".gitkeep"]
            assert not real or t.fixture in scanned, t.id


def test_stats_fixtures_follow_the_definition_rules():
    """M09, M10: 모든 파일이 끝 줄바꿈으로 끝나고 빈 줄이 없다 (줄 수 정의가 모호해지지 않게)."""
    for tid in ("M09", "M10"):
        for p in sorted((loader.FIXTURES_DIR / tid).iterdir()):
            data = p.read_bytes()
            assert data.endswith(b"\n") and not data.endswith(b"\n\n") and b"\n\n" not in data and b"\r" not in data, p
            assert verify_counts.count_lines(p) == data.count(b"\n")
