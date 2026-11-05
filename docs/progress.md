# 진행 기록

## Day 1 (2026-11-03)
- 한 일: Python 3.12.10 설치, venv/SDK(0.2.176) 설치, 구조·README 틀·config 생성, docs/sdk_notes.md 정리, 비공개 GitHub 레포 생성.
- 숫자: Haiku 5.5 도구 왕복 성공(2턴, 2.3초, 추정 $0.0064). cache_creation 31,329 토큰/회로 고정 오버헤드가 큼.
- 다음 할 일: Day 2 커스텀 도구 3개 + 경로 탈출 차단 테스트. cwd 밖 접근 차단 방식(dontAsk/훅) 검증.

## Day 2 (2026-11-03)
- 한 일: 커스텀 도구 3개(search_text, file_stats, check_result), 샌드박스 경로 검사, 내장 도구 PreToolUse 훅, pytest 14개, Haiku 실검증.
- 숫자: pytest 14/14 통과. 실검증 3개 시나리오(Haiku 호출 3회, 총 약 $0.02) 모두 차단, 유출 0건.
- 다음 할 일: Day 3 호출 래퍼(config 전환), trajectory jsonl 로깅, max_turns 도달 동작 확인, 임의 과제 1개 완주.

## Day 3 (2026-11-05)
- 한 일: config 확장(프롬프트 버전, 허용 도구, 파일명용 약칭), runner_agent.py(임시 폴더, 샌드박스, trajectory jsonl, 예외 기록, grader 훅), pytest 6개 추가(총 20개), Haiku 3회 실행.
- 숫자: 시연 과제 5턴, 성공, 약 $0.011/회. max_turns=1은 error_max_turns 결과 + ResultError 예외가 둘 다 발생. 캐시는 실행 내에서만 재사용, 실행 간 미재사용.
- 다음 할 일: Day 4 과제 포맷(YAML/JSON), graders.py, 쉬운 과제 15개와 정답 풀이 스크립트.

## Day 3 후속 점검 (2026-11-05)
- 한 일: 로그 분석, 에이전트가 보는 도구 목록 확인, 캐시 원인 실험(4회), max_turns 실험(4회), 한도 사용률 스냅샷 기록 추가(ratelimit.py), report.py 설계 메모.
- 숫자: max_turns 한계 도달 시 num_turns = 설정값+1. 임시 폴더는 큰 캐시 비용의 원인이 아님(약 40k 블록은 고정 cwd에서도 재생성). utilization 해상도 0.01, 노이즈 ±0.01 → 과제 단위 델타 측정 불가.
- 결정 대기: ① claude.ai 커넥터 도구 약 60개가 에이전트에 노출됨(차단 여부) ② 선택 항목이 required로 노출되는 스키마 문제. Day 4 전에 정해야 베이스라인 동결 전 반영 가능.

## 설계 결정 (2026-11-05)
- 결정: ① 에이전트에서 claude.ai 커넥터를 차단(env ENABLE_CLAUDEAI_MCP_SERVERS=false). 개인 계정 연동 도구가 노출되어 평가 환경으로 부적절했고, 차단 후 비용이 약 10~20배 줄었다(2회 관찰, 가설: 커넥터 노출이 큰 캐시 블록의 원인). ② check_result 등 스키마의 선택 항목을 선택으로 수정 후 "베이스라인 도구 정의 v1"로 고정(베이스라인 이후 변경 금지). ③ 내장 도구는 유지하고, 실험 A의 주 지표를 커스텀 도구 선택률로 추가(성공률과 별도 보고, 표본 크기 자동 표기). ④ 과제 프롬프트에 도구 이름 금지, 과제에 분석 전용 overlap_with 필드.
- 한 일: build_options 환경변수, 스키마 수정, classify_tool, src/eval/report.py(선택률/성공률/5범주), pytest 32개 통과, plan.md와 CLAUDE.md 반영.
- 다음 할 일: Day 4(내일) 과제 포맷과 쉬운 과제 15개. 베이스라인 비용 상한은 차단 설정으로 재측정 필요.
