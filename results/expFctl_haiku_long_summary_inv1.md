# 배치 요약: expFctl / haiku / long (호출 1번째)

- 선택: 과제 4개 x 반복 5 = 20회. 이번 호출에서 새로 끝낸 실행 20회
- 종료 사유: 정상 완료

## 결과
| 항목 | 값 |
|---|---|
| 통과 | 18 |
| 실패 | 2 |
| 채점 없음 | 0 |
| 중단된 실행 | 0 |
| 미실행 | 0 |
| failure_type: pass | 18 |
| failure_type: wrong_value | 2 |
| 평균 턴 수 | 4.7 |
| 입력 토큰 | 174 |
| 출력 토큰 | 17950 |
| 캐시 읽기 토큰 | 562376 |
| 캐시 생성 토큰 | 93376 |
| 정가 환산 비용 합계 | $0.0386 |

비용은 정가 환산 추정치이며 구독 한도 소모와는 별개다. 중단된 실행은 실패가 아니므로 통과/실패에 넣지 않았다.

## 배치 델타 (이번 호출, 구독 전체 사용량이라 다른 사용이 섞일 수 있음)
| 창 | 시작 | 끝 | 델타 |
|---|---|---|---|
| five_hour | 0.14 (probe) | 0.15 (probe) | +0.01 (측정 한계 이하일 수 있음) |
| seven_day | 0.53 (probe) | 0.53 (probe) | +0.00 (측정 한계 이하일 수 있음) |

- 단위 미확인: utilization이 0~1 비율로 보이나 확인되지 않았다. 관찰된 해상도는 0.01 단위, 값마다 ±0.01 노이즈가 관찰됐다. 관찰 범위: five_hour [0.14, 0.15], seven_day [0.53, 0.53]
- 시작값 출처: 탐침 호출(1턴, 도구 없음)로 읽음
- 과제 단위 델타는 쓰지 않는다(해상도와 잡음 때문). 배치 단위로만 본다.

## report.py 출력 (표본 크기 문구 포함)

# 리포트 (실행 20건)

## 설정 (모델 / 프롬프트 / 최대 턴 / 도구 설명)
- claude-haiku-5-5 / v1 / max_turns=20 / long: 20건

## 성공률
성공률 90% (N=4, 과제당 5회 / 총 20건)

## 반복 실행 지표 (반복 2회 이상인 과제만)
pass^k 50% | 단일 실행 평균 성공률 90% (N=4, 과제당 5회 / 총 20건) — 반복 2회 이상 과제만 ※ 표본이 작아 해석에 주의
일관성 (a) 도구 이름 순서 일치 30% | (b) 이름과 핵심 인자까지 일치 12% | (c) 참고: 전체 인자까지 일치 12% (N=4, 과제당 5회 / 총 20건; 비교한 쌍 40개) — 반복 2회 이상 과제만 ※ 표본이 작아 해석에 주의

## min_steps 구간별 성공률 (분석 전용 필드, 사람이 정한 추정값)
min_steps 1~2: 성공률 90% (N=4, 과제당 5회 / 총 20건) ※ 표본이 작아 해석에 주의
min_steps 3 이상: 성공률 n/a (N=0, 과제당 0회 / 총 0건) ※ 표본이 작아 해석에 주의
보조(3구간) min_steps 1~2: 성공률 90% (N=4, 과제당 5회 / 총 20건) ※ 표본이 작아 해석에 주의
보조(3구간) min_steps 3~7: 성공률 n/a (N=0, 과제당 0회 / 총 0건) ※ 표본이 작아 해석에 주의
보조(3구간) min_steps 8 이상: 성공률 n/a (N=0, 과제당 0회 / 총 0건) ※ 표본이 작아 해석에 주의

## 실패 유형 (failure_type, 채점기가 기록한 값 그대로)
failure_type pass 90% (N=4, 과제당 5회 / 총 20건) ※ 표본이 작아 해석에 주의
failure_type wrong_value 10% (N=4, 과제당 5회 / 총 20건) ※ 표본이 작아 해석에 주의
failure_type format_error 0% (N=4, 과제당 5회 / 총 20건) ※ 표본이 작아 해석에 주의
failure_type missing_output 0% (N=4, 과제당 5회 / 총 20건) ※ 표본이 작아 해석에 주의
failure_type unexpected_change 0% (N=4, 과제당 5회 / 총 20건) ※ 표본이 작아 해석에 주의

## 성패 분류 (subtype x 채점)
| 범주 | 건수 |
|---|---|
| success + 채점 통과 | 18 |
| success + 채점 실패(오답) | 2 |
| error_max_turns + 채점 통과 | 0 |
| error_max_turns + 채점 실패 | 0 |
| 기타 error_* / 예외 | 0 |
턴 제한 실패율(error_max_turns + 채점 실패): 0% (N=4, 과제당 5회 / 총 20건)
턴 제한에 걸렸지만 채점 통과: 0건 (별도 집계)

## 커스텀 도구 선택률 (overlap_with가 있는 과제만)
선택률 25% (N=4, 과제당 5회 / 총 20건)

search_text 대 Grep: 25% (N=4, 과제당 5회 / 총 20건) — 커스텀만 1, 내장만 15, 둘 다 4, 둘 다 아님 0

## 실행별 도구 호출 횟수
| 실행 | 과제 | 커스텀 | 내장 | 기타 |
|---|---|---|---|---|
| expFctl_haiku_long_E01_run1.jsonl | E01 | - | Grep 2, Write 1 | - |
| expFctl_haiku_long_E01_run2.jsonl | E01 | - | Grep 2, Write 1 | - |
| expFctl_haiku_long_E01_run3.jsonl | E01 | check_result 1 | Grep 2, Write 1 | - |
| expFctl_haiku_long_E01_run4.jsonl | E01 | check_result 1 | Grep 2, Write 1 | - |
| expFctl_haiku_long_E01_run5.jsonl | E01 | - | Grep 2, Write 1 | - |
| expFctl_haiku_long_M01_run1.jsonl | M01 | check_result 1, search_text 1 | Grep 1, Write 1 | - |
| expFctl_haiku_long_M01_run2.jsonl | M01 | check_result 1, search_text 1 | Grep 2, Write 1 | - |
| expFctl_haiku_long_M01_run3.jsonl | M01 | file_stats 1, search_text 1 | Write 1 | - |
| expFctl_haiku_long_M01_run4.jsonl | M01 | search_text 1 | Grep 2, Write 1 | - |
| expFctl_haiku_long_M01_run5.jsonl | M01 | check_result 1, search_text 1 | Grep 1, Write 1 | - |
| expFctl_haiku_long_M05_run1.jsonl | M05 | - | Grep 1, Read 1, Write 1 | - |
| expFctl_haiku_long_M05_run2.jsonl | M05 | - | Grep 1, Read 1, Write 1 | - |
| expFctl_haiku_long_M05_run3.jsonl | M05 | check_result 1 | Grep 2, Write 1 | - |
| expFctl_haiku_long_M05_run4.jsonl | M05 | - | Grep 1, Read 1, Write 1 | - |
| expFctl_haiku_long_M05_run5.jsonl | M05 | check_result 1 | Grep 2, Write 1 | - |
| expFctl_haiku_long_M07_run1.jsonl | M07 | check_result 1 | Glob 1, Grep 1, Write 1 | - |
| expFctl_haiku_long_M07_run2.jsonl | M07 | - | Glob 1, Grep 2, Write 1 | - |
| expFctl_haiku_long_M07_run3.jsonl | M07 | check_result 1 | Glob 1, Grep 1, Write 1 | - |
| expFctl_haiku_long_M07_run4.jsonl | M07 | - | Glob 1, Grep 1, Write 1 | - |
| expFctl_haiku_long_M07_run5.jsonl | M07 | check_result 1 | Glob 1, Grep 1, Write 1 | - |

## 기타 지표
- 도구 오류율: 0/73 = 0.0%
- 도구 오류율(구분): 커스텀 0/16 = 0.0% | 내장 0/57 = 0.0% | 기타 0/0 = n/a
- 평균 턴 수: 보고값 4.65, 보정값 4.65 (error_max_turns는 설정값+1로 보고되므로 min(num_turns, max_turns)로 보정)
- 비용 추정(정가 환산): 합계 $0.0386, 실행당 평균 $0.0019

※ 표본이 작아 해석에 주의 (선택률 계산에 포함된 실행 20건 < 30건)
