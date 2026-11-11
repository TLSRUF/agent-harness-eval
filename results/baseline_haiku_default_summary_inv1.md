# 배치 요약: baseline / haiku / default (호출 1번째)

- 선택: 과제 40개 x 반복 1 = 40회. 이번 호출에서 새로 끝낸 실행 40회
- 종료 사유: 정상 완료

## 결과
| 항목 | 값 |
|---|---|
| 통과 | 40 |
| 실패 | 0 |
| 채점 없음 | 0 |
| 중단된 실행 | 0 |
| 미실행 | 0 |
| failure_type: pass | 40 |
| 평균 턴 수 | 5.9 |
| 입력 토큰 | 316 |
| 출력 토큰 | 35439 |
| 캐시 읽기 토큰 | 796342 |
| 캐시 생성 토큰 | 126748 |
| 정가 환산 비용 합계 | $0.0604 |

비용은 정가 환산 추정치이며 구독 한도 소모와는 별개다. 중단된 실행은 실패가 아니므로 통과/실패에 넣지 않았다.

## 배치 델타 (이번 호출, 구독 전체 사용량이라 다른 사용이 섞일 수 있음)
| 창 | 시작 | 끝 | 델타 |
|---|---|---|---|
| five_hour | 0.28 (probe) | 0.29 (probe) | +0.01 (측정 한계 이하일 수 있음) |
| seven_day | 0.11 (probe) | 0.11 (probe) | +0.00 (측정 한계 이하일 수 있음) |

- 단위 미확인: utilization이 0~1 비율로 보이나 확인되지 않았다. 관찰된 해상도는 0.01 단위, 값마다 ±0.01 노이즈가 관찰됐다. 관찰 범위: five_hour [0.28, 0.29], seven_day [0.11, 0.11]
- 시작값 출처: 탐침 호출(1턴, 도구 없음)로 읽음
- 과제 단위 델타는 쓰지 않는다(해상도와 잡음 때문). 배치 단위로만 본다.

## report.py 출력 (표본 크기 문구 포함)

# 리포트 (실행 40건)

## 설정 (모델 / 프롬프트 / 최대 턴 / 도구 설명)
- claude-haiku-5-5 / v1 / max_turns=20 / default: 40건

## 성공률
성공률 100% (N=40, 과제당 1회 / 총 40건)

## 반복 실행 지표 (반복 2회 이상인 과제만)
pass^k n/a | 단일 실행 평균 성공률 n/a (N=0, 과제당 0회 / 총 0건) — 반복 2회 이상 과제만 ※ 표본이 작아 해석에 주의
일관성 (a) 도구 이름 순서 일치 n/a | (b) 이름과 핵심 인자까지 일치 n/a | (c) 참고: 전체 인자까지 일치 n/a (N=0, 과제당 0회 / 총 0건; 비교한 쌍 0개) — 반복 2회 이상 과제만 ※ 표본이 작아 해석에 주의

## min_steps 구간별 성공률 (분석 전용 필드, 사람이 정한 추정값)
min_steps 1~2: 성공률 100% (N=28, 과제당 1회 / 총 28건) ※ 표본이 작아 해석에 주의
min_steps 3 이상: 성공률 100% (N=12, 과제당 1회 / 총 12건) ※ 표본이 작아 해석에 주의
보조(3구간) min_steps 1~2: 성공률 100% (N=28, 과제당 1회 / 총 28건) ※ 표본이 작아 해석에 주의
보조(3구간) min_steps 3~7: 성공률 100% (N=5, 과제당 1회 / 총 5건) ※ 표본이 작아 해석에 주의
보조(3구간) min_steps 8 이상: 성공률 100% (N=7, 과제당 1회 / 총 7건) ※ 표본이 작아 해석에 주의

## 실패 유형 (failure_type, 채점기가 기록한 값 그대로)
failure_type pass 100% (N=40, 과제당 1회 / 총 40건)
failure_type wrong_value 0% (N=40, 과제당 1회 / 총 40건)
failure_type format_error 0% (N=40, 과제당 1회 / 총 40건)
failure_type missing_output 0% (N=40, 과제당 1회 / 총 40건)
failure_type unexpected_change 0% (N=40, 과제당 1회 / 총 40건)

## 성패 분류 (subtype x 채점)
| 범주 | 건수 |
|---|---|
| success + 채점 통과 | 40 |
| success + 채점 실패(오답) | 0 |
| error_max_turns + 채점 통과 | 0 |
| error_max_turns + 채점 실패 | 0 |
| 기타 error_* / 예외 | 0 |
턴 제한 실패율(error_max_turns + 채점 실패): 0% (N=40, 과제당 1회 / 총 40건)
턴 제한에 걸렸지만 채점 통과: 0건 (별도 집계)

## 커스텀 도구 선택률 (overlap_with가 있는 과제만)
선택률 25% (N=20, 과제당 1회 / 총 20건)
(overlap_with가 없는 과제의 실행 20건은 제외)

file_stats 대 Read: 62% (N=8, 과제당 1회 / 총 8건) — 커스텀만 4, 내장만 3, 둘 다 1, 둘 다 아님 0
search_text 대 Grep: 0% (N=12, 과제당 1회 / 총 12건) — 커스텀만 0, 내장만 10, 둘 다 0, 둘 다 아님 2

## 실행별 도구 호출 횟수
| 실행 | 과제 | 커스텀 | 내장 | 기타 |
|---|---|---|---|---|
| baseline_haiku_default_E01_run1.jsonl | E01 | check_result 1 | Grep 2, Write 1 | - |
| baseline_haiku_default_E02_run1.jsonl | E02 | - | Grep 1, Write 1 | - |
| baseline_haiku_default_E03_run1.jsonl | E03 | check_result 1, file_stats 1 | Read 1, Write 1 | - |
| baseline_haiku_default_E04_run1.jsonl | E04 | - | Glob 1, Read 1, Write 1 | - |
| baseline_haiku_default_E05_run1.jsonl | E05 | - | Edit 1, Glob 1, Read 1 | - |
| baseline_haiku_default_E06_run1.jsonl | E06 | - | Read 1, Write 1 | - |
| baseline_haiku_default_E07_run1.jsonl | E07 | check_result 1 | Glob 1, Write 1 | - |
| baseline_haiku_default_E08_run1.jsonl | E08 | - | Grep 1, Write 1 | - |
| baseline_haiku_default_E09_run1.jsonl | E09 | - | Read 1, Write 1 | - |
| baseline_haiku_default_E10_run1.jsonl | E10 | check_result 1 | Read 2, Write 1 | - |
| baseline_haiku_default_E11_run1.jsonl | E11 | - | Write 1 | - |
| baseline_haiku_default_E12_run1.jsonl | E12 | check_result 1 | Read 1, Write 1 | - |
| baseline_haiku_default_E13_run1.jsonl | E13 | check_result 1 | Read 1, Write 1 | - |
| baseline_haiku_default_E14_run1.jsonl | E14 | check_result 1 | Read 1, Write 1 | - |
| baseline_haiku_default_E15_run1.jsonl | E15 | - | Edit 2, Read 2 | - |
| baseline_haiku_default_H01_run1.jsonl | H01 | check_result 1, file_stats 10 | Glob 1, Write 1 | - |
| baseline_haiku_default_H02_run1.jsonl | H02 | check_result 1, file_stats 12 | Glob 1, Grep 1, Write 1 | - |
| baseline_haiku_default_H03_run1.jsonl | H03 | - | Glob 1, Grep 1, Write 1 | - |
| baseline_haiku_default_H04_run1.jsonl | H04 | check_result 1 | Glob 1, Grep 1, Read 10, Write 1 | - |
| baseline_haiku_default_H05_run1.jsonl | H05 | - | Edit 6, Glob 1, Grep 2, Read 6 | - |
| baseline_haiku_default_H06_run1.jsonl | H06 | - | Read 2, Write 1 | - |
| baseline_haiku_default_H07_run1.jsonl | H07 | check_result 1 | Glob 1, Read 6, Write 1 | - |
| baseline_haiku_default_H08_run1.jsonl | H08 | check_result 1, file_stats 10 | Glob 1, Write 1 | - |
| baseline_haiku_default_M01_run1.jsonl | M01 | - | Grep 2, Write 1 | - |
| baseline_haiku_default_M02_run1.jsonl | M02 | check_result 1 | Read 1, Write 1 | - |
| baseline_haiku_default_M03_run1.jsonl | M03 | - | Grep 1, Write 1 | - |
| baseline_haiku_default_M04_run1.jsonl | M04 | - | Grep 1, Read 1, Write 1 | - |
| baseline_haiku_default_M05_run1.jsonl | M05 | - | Grep 1, Read 1, Write 1 | - |
| baseline_haiku_default_M06_run1.jsonl | M06 | check_result 1 | Glob 1, Grep 2, Write 1 | - |
| baseline_haiku_default_M07_run1.jsonl | M07 | check_result 1 | Glob 1, Grep 1, Write 1 | - |
| baseline_haiku_default_M08_run1.jsonl | M08 | check_result 1 | Glob 1, Grep 1, Write 1 | - |
| baseline_haiku_default_M09_run1.jsonl | M09 | file_stats 10 | Glob 1, Write 1 | - |
| baseline_haiku_default_M10_run1.jsonl | M10 | check_result 1 | Glob 1, Read 8, Write 1 | - |
| baseline_haiku_default_M11_run1.jsonl | M11 | - | Read 1, Write 1 | - |
| baseline_haiku_default_M12_run1.jsonl | M12 | - | Read 1, Write 1 | - |
| baseline_haiku_default_M13_run1.jsonl | M13 | check_result 1 | Read 1, Write 1 | - |
| baseline_haiku_default_M14_run1.jsonl | M14 | - | Edit 2, Glob 1, Read 1 | - |
| baseline_haiku_default_M15_run1.jsonl | M15 | check_result 1 | Read 1, Write 1 | - |
| baseline_haiku_default_M16_run1.jsonl | M16 | - | Read 1, Write 1 | - |
| baseline_haiku_default_M17_run1.jsonl | M17 | - | Read 1, Write 1 | - |

## 기타 지표
- 도구 오류율: 0/197 = 0.0%
- 도구 오류율(구분): 커스텀 0/62 = 0.0% | 내장 0/135 = 0.0% | 기타 0/0 = n/a
- 평균 턴 수: 보고값 5.92, 보정값 5.92 (error_max_turns는 설정값+1로 보고되므로 min(num_turns, max_turns)로 보정)
- 비용 추정(정가 환산): 합계 $0.0604, 실행당 평균 $0.0015

※ 표본이 작아 해석에 주의 (선택률 계산에 포함된 실행 20건 < 30건)
