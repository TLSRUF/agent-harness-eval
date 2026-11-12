# 배치 요약: expA / haiku / long (호출 1번째)

- 선택: 과제 40개 x 반복 3 = 120회. 이번 호출에서 새로 끝낸 실행 120회
- 종료 사유: 정상 완료

## 결과
| 항목 | 값 |
|---|---|
| 통과 | 114 |
| 실패 | 6 |
| 채점 없음 | 0 |
| 중단된 실행 | 0 |
| 미실행 | 0 |
| failure_type: pass | 114 |
| failure_type: wrong_value | 6 |
| 평균 턴 수 | 6.0 |
| 입력 토큰 | 936 |
| 출력 토큰 | 102496 |
| 캐시 읽기 토큰 | 2597274 |
| 캐시 생성 토큰 | 260380 |
| 정가 환산 비용 합계 | $0.1559 |

비용은 정가 환산 추정치이며 구독 한도 소모와는 별개다. 중단된 실행은 실패가 아니므로 통과/실패에 넣지 않았다.

## 배치 델타 (이번 호출, 구독 전체 사용량이라 다른 사용이 섞일 수 있음)
| 창 | 시작 | 끝 | 델타 |
|---|---|---|---|
| five_hour | 0.34 (probe) | 0.35 (probe) | +0.01 (측정 한계 이하일 수 있음) |
| seven_day | 0.2 (probe) | 0.2 (probe) | +0.00 (측정 한계 이하일 수 있음) |

- 단위 미확인: utilization이 0~1 비율로 보이나 확인되지 않았다. 관찰된 해상도는 0.01 단위, 값마다 ±0.01 노이즈가 관찰됐다. 관찰 범위: five_hour [0.34, 0.35], seven_day [0.2, 0.2]
- 시작값 출처: 탐침 호출(1턴, 도구 없음)로 읽음
- 과제 단위 델타는 쓰지 않는다(해상도와 잡음 때문). 배치 단위로만 본다.

## report.py 출력 (표본 크기 문구 포함)

# 리포트 (실행 120건)

## 설정 (모델 / 프롬프트 / 최대 턴 / 도구 설명)
- claude-haiku-5-5 / v1 / max_turns=20 / long: 120건

## 성공률
성공률 95% (N=40, 과제당 3회 / 총 120건)

## 반복 실행 지표 (반복 2회 이상인 과제만)
pass^k 92% | 단일 실행 평균 성공률 95% (N=40, 과제당 3회 / 총 120건) — 반복 2회 이상 과제만
일관성 (a) 도구 이름 순서 일치 44% | (b) 이름과 핵심 인자까지 일치 36% | (c) 참고: 전체 인자까지 일치 36% (N=40, 과제당 3회 / 총 120건; 비교한 쌍 120개) — 반복 2회 이상 과제만

## min_steps 구간별 성공률 (분석 전용 필드, 사람이 정한 추정값)
min_steps 1~2: 성공률 96% (N=28, 과제당 3회 / 총 84건)
min_steps 3 이상: 성공률 92% (N=12, 과제당 3회 / 총 36건)
보조(3구간) min_steps 1~2: 성공률 96% (N=28, 과제당 3회 / 총 84건)
보조(3구간) min_steps 3~7: 성공률 100% (N=5, 과제당 3회 / 총 15건) ※ 표본이 작아 해석에 주의
보조(3구간) min_steps 8 이상: 성공률 86% (N=7, 과제당 3회 / 총 21건) ※ 표본이 작아 해석에 주의

## 실패 유형 (failure_type, 채점기가 기록한 값 그대로)
failure_type pass 95% (N=40, 과제당 3회 / 총 120건)
failure_type wrong_value 5% (N=40, 과제당 3회 / 총 120건)
failure_type format_error 0% (N=40, 과제당 3회 / 총 120건)
failure_type missing_output 0% (N=40, 과제당 3회 / 총 120건)
failure_type unexpected_change 0% (N=40, 과제당 3회 / 총 120건)

## 성패 분류 (subtype x 채점)
| 범주 | 건수 |
|---|---|
| success + 채점 통과 | 114 |
| success + 채점 실패(오답) | 6 |
| error_max_turns + 채점 통과 | 0 |
| error_max_turns + 채점 실패 | 0 |
| 기타 error_* / 예외 | 0 |
턴 제한 실패율(error_max_turns + 채점 실패): 0% (N=40, 과제당 3회 / 총 120건)
턴 제한에 걸렸지만 채점 통과: 0건 (별도 집계)

## 커스텀 도구 선택률 (overlap_with가 있는 과제만)
선택률 48% (N=20, 과제당 3회 / 총 60건)
(overlap_with가 없는 과제의 실행 60건은 제외)

file_stats 대 Read: 100% (N=8, 과제당 3회 / 총 24건) — 커스텀만 17, 내장만 0, 둘 다 7, 둘 다 아님 0
search_text 대 Grep: 14% (N=12, 과제당 3회 / 총 36건) — 커스텀만 4, 내장만 28, 둘 다 1, 둘 다 아님 3

## 실행별 도구 호출 횟수
| 실행 | 과제 | 커스텀 | 내장 | 기타 |
|---|---|---|---|---|
| expA_haiku_long_E01_run1.jsonl | E01 | - | Grep 1, Write 1 | - |
| expA_haiku_long_E01_run2.jsonl | E01 | - | Grep 2, Write 1 | - |
| expA_haiku_long_E01_run3.jsonl | E01 | - | Grep 2, Write 1 | - |
| expA_haiku_long_E02_run1.jsonl | E02 | search_text 1 | Write 1 | - |
| expA_haiku_long_E02_run2.jsonl | E02 | - | Grep 1, Read 1, Write 1 | - |
| expA_haiku_long_E02_run3.jsonl | E02 | search_text 1 | Write 1 | - |
| expA_haiku_long_E03_run1.jsonl | E03 | check_result 1, file_stats 1 | Read 1, Write 1 | - |
| expA_haiku_long_E03_run2.jsonl | E03 | check_result 1, file_stats 1 | Read 1, Write 1 | - |
| expA_haiku_long_E03_run3.jsonl | E03 | file_stats 1 | Read 1, Write 1 | - |
| expA_haiku_long_E04_run1.jsonl | E04 | - | Read 1, Write 1 | - |
| expA_haiku_long_E04_run2.jsonl | E04 | - | Read 1, Write 1 | - |
| expA_haiku_long_E04_run3.jsonl | E04 | - | Glob 1, Read 1, Write 1 | - |
| expA_haiku_long_E05_run1.jsonl | E05 | - | Edit 1, Grep 1 | - |
| expA_haiku_long_E05_run2.jsonl | E05 | - | Edit 1, Glob 1, Grep 1, Read 1 | - |
| expA_haiku_long_E05_run3.jsonl | E05 | - | Edit 1, Grep 1 | - |
| expA_haiku_long_E06_run1.jsonl | E06 | - | Read 1, Write 1 | - |
| expA_haiku_long_E06_run2.jsonl | E06 | - | Read 1, Write 1 | - |
| expA_haiku_long_E06_run3.jsonl | E06 | - | Read 1, Write 1 | - |
| expA_haiku_long_E07_run1.jsonl | E07 | - | Glob 1, Write 1 | - |
| expA_haiku_long_E07_run2.jsonl | E07 | - | Glob 1, Write 1 | - |
| expA_haiku_long_E07_run3.jsonl | E07 | check_result 1 | Glob 1, Write 1 | - |
| expA_haiku_long_E08_run1.jsonl | E08 | - | Grep 1, Write 1 | - |
| expA_haiku_long_E08_run2.jsonl | E08 | - | Read 1, Write 1 | - |
| expA_haiku_long_E08_run3.jsonl | E08 | - | Grep 1, Write 1 | - |
| expA_haiku_long_E09_run1.jsonl | E09 | - | Read 1, Write 1 | - |
| expA_haiku_long_E09_run2.jsonl | E09 | - | Read 1, Write 1 | - |
| expA_haiku_long_E09_run3.jsonl | E09 | - | Read 1, Write 1 | - |
| expA_haiku_long_E10_run1.jsonl | E10 | file_stats 2 | Write 1 | - |
| expA_haiku_long_E10_run2.jsonl | E10 | file_stats 2 | Write 1 | - |
| expA_haiku_long_E10_run3.jsonl | E10 | file_stats 2 | Write 1 | - |
| expA_haiku_long_E11_run1.jsonl | E11 | - | Write 1 | - |
| expA_haiku_long_E11_run2.jsonl | E11 | - | Write 1 | - |
| expA_haiku_long_E11_run3.jsonl | E11 | - | Write 1 | - |
| expA_haiku_long_E12_run1.jsonl | E12 | check_result 1, file_stats 1 | Read 1, Write 1 | - |
| expA_haiku_long_E12_run2.jsonl | E12 | - | Read 1, Write 1 | - |
| expA_haiku_long_E12_run3.jsonl | E12 | - | Read 1, Write 1 | - |
| expA_haiku_long_E13_run1.jsonl | E13 | check_result 1 | Read 1, Write 1 | - |
| expA_haiku_long_E13_run2.jsonl | E13 | - | Read 1, Write 1 | - |
| expA_haiku_long_E13_run3.jsonl | E13 | check_result 1 | Grep 1, Write 1 | - |
| expA_haiku_long_E14_run1.jsonl | E14 | - | Read 1, Write 1 | - |
| expA_haiku_long_E14_run2.jsonl | E14 | - | Read 1, Write 1 | - |
| expA_haiku_long_E14_run3.jsonl | E14 | - | Read 1, Write 1 | - |
| expA_haiku_long_E15_run1.jsonl | E15 | - | Edit 2, Read 2 | - |
| expA_haiku_long_E15_run2.jsonl | E15 | - | Edit 2, Read 2 | - |
| expA_haiku_long_E15_run3.jsonl | E15 | - | Edit 2, Read 2 | - |
| expA_haiku_long_H01_run1.jsonl | H01 | check_result 1, file_stats 10 | Glob 1, Write 1 | - |
| expA_haiku_long_H01_run2.jsonl | H01 | check_result 1, file_stats 10 | Glob 1, Write 1 | - |
| expA_haiku_long_H01_run3.jsonl | H01 | file_stats 10 | Glob 1, Write 1 | - |
| expA_haiku_long_H02_run1.jsonl | H02 | check_result 1, file_stats 12 | Glob 1, Write 1 | - |
| expA_haiku_long_H02_run2.jsonl | H02 | check_result 1, file_stats 12 | Glob 1, Grep 2, Write 1 | - |
| expA_haiku_long_H02_run3.jsonl | H02 | file_stats 12 | Glob 1, Grep 2, Write 1 | - |
| expA_haiku_long_H03_run1.jsonl | H03 | check_result 1 | Glob 1, Grep 1, Write 1 | - |
| expA_haiku_long_H03_run2.jsonl | H03 | check_result 1 | Glob 1, Grep 1, Write 1 | - |
| expA_haiku_long_H03_run3.jsonl | H03 | - | Glob 1, Grep 1, Write 1 | - |
| expA_haiku_long_H04_run1.jsonl | H04 | check_result 1, file_stats 10, search_text 1 | Glob 1, Grep 1, Read 3, Write 1 | - |
| expA_haiku_long_H04_run2.jsonl | H04 | check_result 1, file_stats 10 | Glob 1, Grep 4, Read 1, Write 1 | - |
| expA_haiku_long_H04_run3.jsonl | H04 | check_result 1, file_stats 10 | Glob 1, Read 10, Write 1 | - |
| expA_haiku_long_H05_run1.jsonl | H05 | - | Edit 6, Glob 1, Grep 2, Read 6 | - |
| expA_haiku_long_H05_run2.jsonl | H05 | search_text 1 | Edit 6, Glob 1, Grep 3, Read 10 | - |
| expA_haiku_long_H05_run3.jsonl | H05 | - | Edit 6, Glob 1, Grep 3, Read 6 | - |
| expA_haiku_long_H06_run1.jsonl | H06 | - | Read 2, Write 1 | - |
| expA_haiku_long_H06_run2.jsonl | H06 | check_result 1 | Read 2, Write 1 | - |
| expA_haiku_long_H06_run3.jsonl | H06 | check_result 1 | Read 2, Write 1 | - |
| expA_haiku_long_H07_run1.jsonl | H07 | check_result 1 | Glob 1, Read 6, Write 1 | - |
| expA_haiku_long_H07_run2.jsonl | H07 | - | Glob 1, Read 6, Write 1 | - |
| expA_haiku_long_H07_run3.jsonl | H07 | - | Glob 1, Read 6, Write 1 | - |
| expA_haiku_long_H08_run1.jsonl | H08 | file_stats 10 | Glob 1, Write 1 | - |
| expA_haiku_long_H08_run2.jsonl | H08 | file_stats 10 | Glob 1, Write 1 | - |
| expA_haiku_long_H08_run3.jsonl | H08 | check_result 1, file_stats 10 | Glob 1, Write 1 | - |
| expA_haiku_long_M01_run1.jsonl | M01 | search_text 1 | Write 1 | - |
| expA_haiku_long_M01_run2.jsonl | M01 | check_result 1, search_text 1 | Write 1 | - |
| expA_haiku_long_M01_run3.jsonl | M01 | search_text 1 | Grep 1, Write 1 | - |
| expA_haiku_long_M02_run1.jsonl | M02 | check_result 1 | Grep 1, Write 1 | - |
| expA_haiku_long_M02_run2.jsonl | M02 | check_result 1 | Grep 1, Write 1 | - |
| expA_haiku_long_M02_run3.jsonl | M02 | check_result 1 | Grep 1, Write 1 | - |
| expA_haiku_long_M03_run1.jsonl | M03 | check_result 1 | Grep 1, Write 1 | - |
| expA_haiku_long_M03_run2.jsonl | M03 | check_result 1 | Grep 1, Write 1 | - |
| expA_haiku_long_M03_run3.jsonl | M03 | - | Grep 1, Write 1 | - |
| expA_haiku_long_M04_run1.jsonl | M04 | - | Grep 1, Write 1 | - |
| expA_haiku_long_M04_run2.jsonl | M04 | check_result 1 | Grep 2, Write 1 | - |
| expA_haiku_long_M04_run3.jsonl | M04 | check_result 1 | Grep 1, Write 1 | - |
| expA_haiku_long_M05_run1.jsonl | M05 | - | Grep 2, Write 1 | - |
| expA_haiku_long_M05_run2.jsonl | M05 | check_result 1 | Grep 2, Write 1 | - |
| expA_haiku_long_M05_run3.jsonl | M05 | check_result 1 | Grep 1, Read 1, Write 1 | - |
| expA_haiku_long_M06_run1.jsonl | M06 | - | Glob 1, Grep 1, Write 1 | - |
| expA_haiku_long_M06_run2.jsonl | M06 | check_result 1 | Glob 1, Grep 1, Write 1 | - |
| expA_haiku_long_M06_run3.jsonl | M06 | - | Glob 1, Grep 2, Write 1 | - |
| expA_haiku_long_M07_run1.jsonl | M07 | check_result 1 | Glob 1, Grep 1, Write 1 | - |
| expA_haiku_long_M07_run2.jsonl | M07 | check_result 1 | Glob 1, Grep 1, Write 1 | - |
| expA_haiku_long_M07_run3.jsonl | M07 | check_result 1 | Glob 1, Grep 1, Write 1 | - |
| expA_haiku_long_M08_run1.jsonl | M08 | - | Glob 1, Grep 1, Write 1 | - |
| expA_haiku_long_M08_run2.jsonl | M08 | - | Grep 1, Write 1 | - |
| expA_haiku_long_M08_run3.jsonl | M08 | check_result 1 | Glob 1, Grep 1, Write 1 | - |
| expA_haiku_long_M09_run1.jsonl | M09 | check_result 1, file_stats 10 | Glob 1, Write 1 | - |
| expA_haiku_long_M09_run2.jsonl | M09 | check_result 1, file_stats 10 | Glob 1, Grep 2, Write 1 | - |
| expA_haiku_long_M09_run3.jsonl | M09 | check_result 1, file_stats 10 | Glob 1, Write 1 | - |
| expA_haiku_long_M10_run1.jsonl | M10 | check_result 1, file_stats 8 | Glob 1, Write 1 | - |
| expA_haiku_long_M10_run2.jsonl | M10 | check_result 1, file_stats 8 | Glob 1, Write 1 | - |
| expA_haiku_long_M10_run3.jsonl | M10 | check_result 1, file_stats 3 | Glob 1, Read 8, Write 1 | - |
| expA_haiku_long_M11_run1.jsonl | M11 | - | Read 1, Write 1 | - |
| expA_haiku_long_M11_run2.jsonl | M11 | - | Read 1, Write 1 | - |
| expA_haiku_long_M11_run3.jsonl | M11 | check_result 1 | Read 1, Write 1 | - |
| expA_haiku_long_M12_run1.jsonl | M12 | - | Read 1, Write 1 | - |
| expA_haiku_long_M12_run2.jsonl | M12 | - | Read 1, Write 1 | - |
| expA_haiku_long_M12_run3.jsonl | M12 | - | Read 1, Write 1 | - |
| expA_haiku_long_M13_run1.jsonl | M13 | check_result 1 | Read 1, Write 1 | - |
| expA_haiku_long_M13_run2.jsonl | M13 | check_result 1 | Read 1, Write 1 | - |
| expA_haiku_long_M13_run3.jsonl | M13 | check_result 1 | Read 1, Write 1 | - |
| expA_haiku_long_M14_run1.jsonl | M14 | - | Edit 2, Read 1 | - |
| expA_haiku_long_M14_run2.jsonl | M14 | - | Edit 2, Glob 1, Read 1 | - |
| expA_haiku_long_M14_run3.jsonl | M14 | - | Edit 2, Glob 1, Read 1 | - |
| expA_haiku_long_M15_run1.jsonl | M15 | file_stats 2 | Read 1, Write 1 | - |
| expA_haiku_long_M15_run2.jsonl | M15 | search_text 1 | Read 1, Write 1 | - |
| expA_haiku_long_M15_run3.jsonl | M15 | check_result 1, file_stats 1 | Read 1, Write 1 | - |
| expA_haiku_long_M16_run1.jsonl | M16 | - | Read 1, Write 1 | - |
| expA_haiku_long_M16_run2.jsonl | M16 | - | Read 1, Write 1 | - |
| expA_haiku_long_M16_run3.jsonl | M16 | - | Read 1, Write 1 | - |
| expA_haiku_long_M17_run1.jsonl | M17 | - | Read 1, Write 1 | - |
| expA_haiku_long_M17_run2.jsonl | M17 | - | Read 1, Write 1 | - |
| expA_haiku_long_M17_run3.jsonl | M17 | - | Read 1, Write 1 | - |

## 기타 지표
- 도구 오류율: 0/603 = 0.0%
- 도구 오류율(구분): 커스텀 0/241 = 0.0% | 내장 0/362 = 0.0% | 기타 0/0 = n/a
- 평균 턴 수: 보고값 6.03, 보정값 6.03 (error_max_turns는 설정값+1로 보고되므로 min(num_turns, max_turns)로 보정)
- 비용 추정(정가 환산): 합계 $0.1559, 실행당 평균 $0.0013
