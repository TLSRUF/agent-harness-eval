"""실험 A: 도구 설명 변형. 입력 스키마, 도구 이름, 동작은 default(동결된 도구 정의 v1)와 같고 설명 텍스트만 다르다.

- short: default보다 짧은 한 문장(핵심 기능만).
- long: 입력 항목의 의미, 출력 형식, 예시 1개, 이 도구가 제공하는 정보를 정보 위주로 자세히 설명. 다른 도구보다 우선 쓰라는 지시는 넣지 않는다.
- long_directive: long + 우선 사용 지시 문장 하나(정보 효과와 지시 효과를 분리하기 위한 변형).

default는 src/agent/tools.py의 DESCRIPTIONS["default"]에 있고 동결 대상이다. 여기서 바꾸지 않는다.
예시 값은 어떤 과제 프롬프트나 fixture에도 나오지 않는 값만 쓴다(tests/test_tool_variants.py가 확인).
"""

SHORT: dict[str, str] = {
    "search_text": "Search files for text.",
    "file_stats": "Count a file's lines, words and bytes.",
    "check_result": "Check a file's existence and content.",
}

LONG: dict[str, str] = {
    "search_text": (
        "Search for a text string in the files under a folder (or in a single file) and return every matching line. "
        "The match is a case-sensitive substring test applied to each line, and files are searched recursively in sorted path order. "
        "Input: query (required) is the text to look for; path (optional, default is the working directory) is a folder or a file, "
        "relative to the working directory. "
        "Output: one line per match in the form relative/path:line_number:line_text, where line_number starts at 1 and line_text is the "
        "matching line trimmed of surrounding whitespace; at most 50 matches are returned, followed by '(truncated at 50)' if there were more, "
        "and 'no matches' is returned if nothing was found. Files larger than 1,000,000 bytes are skipped. "
        "Example: query='basalt', path='vault' might return vault/q7.txt:3:the basalt sample. "
        "This tool provides line numbers together with the matching text."
    ),
    "file_stats": (
        "Return the line count, word count and byte size of one text file. "
        "Input: path (required) is the file, relative to the working directory; it must be a file, not a folder. "
        "Output: a single line 'lines=<N> words=<N> bytes=<N>'. Lines are counted by splitting the text into lines "
        "(a final line without a trailing newline still counts, and an empty file has 0 lines), words are runs of non-whitespace characters, "
        "and bytes is the size of the file on disk. Files larger than 1,000,000 bytes return an error. "
        "Example: path='vault/q7.txt' might return 'lines=12 words=87 bytes=530'. "
        "This tool provides the line, word and byte counts of a file without returning its content."
    ),
    "check_result": (
        "Check whether a file exists and, optionally, whether it contains a given string and has at least a minimum number of lines. "
        "Input: path (required) is the file to check, relative to the working directory; contains (optional) is a text that has to appear "
        "somewhere in the file (case-sensitive substring); min_lines (optional) is the minimum number of lines the file has to have. "
        "Output: the single word PASS if every given condition holds, otherwise 'FAIL: ' followed by the reasons separated by '; ' "
        "(for example a missing text, fewer lines than min_lines, or a file that does not exist). "
        "Example: path='vault/q7.txt', contains='basalt', min_lines=3 returns PASS or a FAIL reason. "
        "This tool provides a pass/fail verdict with the reasons and does not modify any file."
    ),
}

# long에 붙이는 지시 문장(도구마다 하나). 이 문장 외에는 long과 글자 하나까지 같다.
DIRECTIVE: dict[str, str] = {
    "search_text": "For searching text in files, use this tool first.",
    "file_stats": "For counting a file's lines, words or bytes, use this tool first.",
    "check_result": "For checking a file's existence or content, use this tool first.",
}

VARIANT_DESCRIPTIONS: dict[str, dict[str, str]] = {
    "short": SHORT,
    "long": LONG,
    "long_directive": {name: f"{LONG[name]} {DIRECTIVE[name]}" for name in LONG},
}
