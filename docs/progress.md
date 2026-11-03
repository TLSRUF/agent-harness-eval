# 진행 기록

## Day 1 (2026-11-03)
- 한 일: Python 3.12.10 설치, venv/SDK(0.2.176) 설치, 구조·README 틀·config 생성, docs/sdk_notes.md 정리, 비공개 GitHub 레포 생성.
- 숫자: Haiku 5.5 도구 왕복 성공(2턴, 2.3초, 추정 $0.0064). cache_creation 31,329 토큰/회로 고정 오버헤드가 큼.
- 다음 할 일: Day 2 커스텀 도구 3개 + 경로 탈출 차단 테스트. cwd 밖 접근 차단 방식(dontAsk/훅) 검증.

## Day 2 (2026-11-03)
- 한 일: 커스텀 도구 3개(search_text, file_stats, check_result), 샌드박스 경로 검사, 내장 도구 PreToolUse 훅, pytest 14개, Haiku 실검증.
- 숫자: pytest 14/14 통과. 실검증 3개 시나리오(Haiku 호출 3회, 총 약 $0.02) 모두 차단, 유출 0건.
- 다음 할 일: Day 3 호출 래퍼(config 전환), trajectory jsonl 로깅, max_turns 도달 동작 확인, 임의 과제 1개 완주.
