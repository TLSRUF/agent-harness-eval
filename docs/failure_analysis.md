# 실패 분석

## 실험 A 실패 12건 (short 3, long 6, long_directive 3) — 읽기 전용 분석, 모델 호출 없음

대상: results/raw의 expA 실행 360건 중 채점 실패 12건. 모두 failure_type = wrong_value. error_max_turns는 0건, 다른 failure_type은 없다.
기준은 CLAUDE.md의 분류 (a) 에이전트 실수 (b) 프롬프트 모호 (c) 채점 기준 문제, 그리고 이번 요청의 (d) 도구 자체의 동작 한계.
에이전트가 만든 출력은 results/raw/*_final/ 스냅샷에서, 기대 정답은 과제 JSON에서 읽었다.

| 설정 | 과제 | run | failure_type | 에이전트 출력 | 기대 정답 | 도구 순서(이름만) | 커스텀 결과 잘림 | 분류 |
|---|---|---|---|---|---|---|---|---|
| short | M05 | 2 | wrong_value | 줄 수: 18 | 줄 수: 17 | Read, Grep, Write | 아니오 | (a) 세기 실수. Grep 출력은 정확히 17줄 |
| short | M07 | 1 | wrong_value | 줄 수: 13 | 줄 수: 14 | Glob, Grep, Write, check_result | 아니오 | (a) 세기 실수. Grep 출력은 정확히 14줄 |
| short | M07 | 2 | wrong_value | 줄 수: 13 | 줄 수: 14 | Glob, Grep, Write, check_result | 아니오 | (a) 세기 실수. Grep 출력은 정확히 14줄 |
| long | H01 | 1 | wrong_value | app_08.log: 2675 / app_03.log: 2493 / app_05.log: 2306 | app_07.log: 2675 / app_03.log: 2493 / app_05.log: 2306 | Glob, file_stats x10, Write, check_result | 아니오 | (a) 파일 이름과 값의 짝을 잘못 씀. 도구 결과 10개는 모두 맞음 |
| long | H01 | 2 | wrong_value | (위와 같음) | (위와 같음) | Glob, file_stats x10, Write, check_result | 아니오 | (a) 위와 같음 |
| long | H01 | 3 | wrong_value | (위와 같음) | (위와 같음) | Glob, file_stats x10, Write | 아니오 | (a) 위와 같음 |
| long | M01 | 1 | wrong_value | 줄 수: 25 | 줄 수: 23 | search_text, Write | 아니오 | (a) 세기 실수. search_text 출력은 정확히 23줄 |
| long | M01 | 3 | wrong_value | 줄 수: 24 | 줄 수: 23 | search_text, Grep, Write | 아니오 | (a) 세기 실수. search_text와 Grep 출력 모두 정확히 23줄 |
| long | M07 | 3 | wrong_value | 줄 수: 13 | 줄 수: 14 | Glob, Grep, Write, check_result | 아니오 | (a) 세기 실수. Grep 출력은 정확히 14줄 |
| long_directive | H01 | 2 | wrong_value | app_08.log: 2675 / app_03.log: 2493 / app_05.log: 2306 | app_07.log: 2675 / app_03.log: 2493 / app_05.log: 2306 | Glob, file_stats x10, Write, check_result | 아니오 | (a) H01 long과 같은 오류 |
| long_directive | H01 | 3 | wrong_value | (위와 같음) | (위와 같음) | Glob, file_stats x10, Write | 아니오 | (a) 위와 같음 |
| long_directive | M07 | 1 | wrong_value | 줄 수: 13 | 줄 수: 14 | Glob, search_text, Grep, Write, check_result | 아니오 | (a) 세기 실수. search_text와 Grep 출력 모두 정확히 14줄 |

### 분류 요약
- (a) 에이전트의 절차/계산 실수: 12건 모두. 근거: 12건 모두 도구 출력은 정확했다(줄 수 출력은 기대한 줄 수와 같고, H01은 file_stats 10개 결과가 모두 맞았다). 에이전트가 센 값이나 짝지은 이름이 틀렸다.
- (b) 프롬프트가 모호했음: 0건. 근거: 12건 중 모호한 문장에서 비롯한 오류는 없었다(세기 과제는 "몇 줄인지", H01은 파일명과 단어 수 형식을 명시). 단 에이전트 생각(thinking)이 로그에 비어 있어(signature만 있음) 에이전트 내부 해석은 확인 불가.
- (c) 채점 기준 문제: 0건. 근거: 채점은 기대 정답과 문자열을 비교하고, 기대 정답은 사람이 손으로 대조해 동결한 값이며(hand_check와 도구 결과가 일치: H01 단어 수 2675/2493/2306, M07 14줄 등), 오답 출력은 실제로 값이 다르다.
- (d) 도구 자체의 동작 한계: 확인된 것은 0건. 단 가설 2개를 남긴다.
  - H01: file_stats 출력은 `lines=N words=N bytes=N` 형식이라 파일 이름이 들어 있지 않다. 한 응답에서 10개를 병렬 호출하면 결과를 호출 순서로 짝지어야 한다. 실패 5건이 모두 같은 오류(7번째 파일 app_07의 2675를 app_08에 붙임)를 냈으므로 우연한 세기 실수보다 같은 원인이 있어 보인다. 그러나 같은 형식, 같은 병렬 호출(10개)을 한 default 2건과 short 2건은 정답이었다. 도구 출력은 모든 설정에서 같으므로 출력 형식만으로는 설명되지 않고, long 계열 설명이 에이전트 행동을 바꿨을 가능성이 있다(가설, 확인 불가).
  - M01, M05, M07(세기 과제 7건): search_text 출력에는 일치 줄 수 요약이 없다. 내장 Grep은 `output_mode: count`로 "Found 23 total occurrences"처럼 개수를 직접 준다. 확인한 사실: M01 default는 3회 모두 Grep count 모드를 먼저 호출해 23을 받은 뒤 내용을 확인했다. 세기 과제 3개 x 설정 4개 x 3회 = 36건 중 count 모드를 쓴 16건은 실패 0건, 쓰지 않은 20건(내용 줄을 직접 센 경우)은 실패 7건(7건 모두 여기). 우연히 이 정도로 몰릴 확률은 단측 약 0.009(사후 분석, 다중 비교 보정 없음, 탐색용). count 모드 사용 비율은 default 6/9, short 5/9, long 1/9, long_directive 4/9로, long에서 가장 적다. 해석(가설): long 설명이 search_text 쪽으로 선택을 옮기면서 개수 요약을 받지 못하고 직접 세다가 틀렸을 수 있다. 확인 불가(생각 내용 비공개, 인과 미검증).

### 잘림, 길이 제한 확인 (H01, M01 요청 사항)
- `src/agent/tools.py`: search_text는 결과를 최대 `MAX_RESULTS = 50`개로 자르고 `(truncated at 50)`을 붙인다. 읽는 파일 크기는 `MAX_FILE_BYTES = 1_000_000` 이하만 읽는다(초과 파일은 search_text에서 건너뛰고 file_stats에서는 오류). file_stats에는 결과 개수 제한이 없다.
- 실제 로그: 커스텀 도구 결과 866건(baseline 포함 expA 4개 설정) 중 `truncated` 표시가 있는 것 0건, 한 결과의 최대 줄 수 23줄(M01). 가장 큰 fixture 파일은 27,077바이트(M03 orders.log)라 1,000,000바이트 한계와 거리가 멀다. M01 search_text 결과 23건 < 50, H01 file_stats 결과는 파일당 한 줄. 따라서 H01, M01 모두 도구가 결과를 잘라서 생긴 오류는 아니다.

### default가 3/3 통과였던 점 검토
- (b)나 (c)였다면 default도 같은 결함으로 실패해야 하는데 default는 이 4개 과제(H01, M01, M05, M07) x 3회 = 12건 모두 통과했고, 위에서 (b), (c)는 근거가 없다. 다음 이유로 베이스라인 통과는 결함을 가리는 우연이 아니다.
  - 정답 풀이 40개가 채점을 통과한다(동결 검증).
  - H01 default는 file_stats x10(2건)이나 Read x10 + Grep(1건)으로 정답을 만들었고 같은 채점기를 통과했다. 같은 프롬프트에서 expA long 3/3, long_directive 2/3이 틀린 것은 에이전트 행동 차이다.
  - M01 default는 Grep 2번(count 모드로 23을 받고 내용 모드로 확인)으로 3/3 통과, M05 default는 Grep count 3/3, M07 default는 Grep content 3/3 통과(M07 default는 count 없이 직접 세어 14를 맞춤). expA 실패는 M07 4건, M01 2건, M05 1건으로 세기 과제에 모여 있고 도구 출력은 모두 정확했다.
- 따라서 베이스라인 무효화나 재동결이 필요한 사유는 없다. 필요했다면 MANIFEST 대상 파일 변경이므로 멈추고 알렸을 것이다.

### 해석 시 주의 (가설, 사후 분석)
- long 계열에서 H01 5/6 실패(default, short는 file_stats 호출 4건 중 0건 실패)는 사후에 본 패턴이다. 단순 계산(실패 5건이 long 계열 6건에 몰릴 확률, 단측 6/252 ≈ 0.024)은 탐색용이고 다중 비교 보정을 하지 않았다. 원인(설명 문구, 호출 순서, 확률적 변동)은 확인 불가.
- M07의 설정별 실패는 default 0/3, short 2/3, long 1/3, long_directive 1/3이다. 모두 내장 Grep(또는 search_text와 Grep) 출력의 14줄을 13으로 센 오류이며, 설정이 실패율을 올렸는지 우연인지는 확인 불가(표본이 과제 1개 x 3회).

## 실험 B verify_tool 3건, 실험 C 16건 — 읽기 전용 분석, 모델 호출 없음

대상: results/raw의 expB 240건 중 채점 실패 3건(모두 verify_tool), expC 480건 중 채점 실패 16건. 모든 실패 판정은 채점기가 기록한 failure_type 그대로.
요청서의 expC 실패 수는 15건(max_turns 3: 8, 4: 5, 5: 1, 7: 1)이었으나 실제 로그는 **16건**이다(3: 8, 4: 5, **5: 2**, 7: 1). max_turns 5의 실패는 error_max_turns 1건(H07 run1)과 success + wrong_value 1건(H01 run3)이다.
"출력 파일 생성"은 로그의 snapshot 이벤트(missing_outputs) 기준, "Write 있음"은 로그에서 출력 파일에 대한 성공한 Write/Edit 호출이 있었는지(스냅샷 기준과 별개로 호출 기록 확인).

| 설정 | 과제 | run | failure_type | subtype | 모델 응답 수 | 출력 파일 생성(스냅샷), Write 호출 | 기대 정답과의 차이(채점 사유) | 도구 호출 순서 | default 통과 |
|---|---|---|---|---|---|---|---|---|---|
| expB verify_tool | H07 | 3 | wrong_value | success | 4 | 있음, Write 있음 | got 'timeout: 20', expected 'timeout: 35' | Glob, Read x8, Write, check_result | 3/3 |
| expB verify_tool | M07 | 1 | wrong_value | success | 5 | 있음, Write 있음 | got '줄 수: 15', expected '줄 수: 14' | Glob, Grep, Write, check_result | 3/3 |
| expB verify_tool | M07 | 2 | wrong_value | success | 4 | 있음, Write 있음 | got '줄 수: 13', expected '줄 수: 14' | Glob, Grep, Write, check_result | 3/3 |
| expC 3 | H02 | 1 | missing_output | error_max_turns | 3 | 없음, Write 없음 | output file not found: total_lines.out | Glob, file_stats x12, Grep | 3/3 |
| expC 3 | H02 | 2 | missing_output | error_max_turns | 3 | 없음, Write 없음 | output file not found: total_lines.out | Glob, file_stats x12, Grep | 3/3 |
| expC 3 | H02 | 3 | missing_output | error_max_turns | 3 | 없음, Write 없음 | output file not found: total_lines.out | Glob, file_stats x12, Grep | 3/3 |
| expC 3 | H04 | 1 | missing_output | error_max_turns | 3 | 없음, Write 없음 | output file not found: wrong_docs.out | Glob, Read x10, file_stats x4 | 3/3 |
| expC 3 | H04 | 2 | missing_output | error_max_turns | 3 | 없음, Write 없음 | output file not found: wrong_docs.out | Glob, file_stats x10, Grep | 3/3 |
| expC 3 | H04 | 3 | missing_output | error_max_turns | 3 | 없음, Write 없음 | output file not found: wrong_docs.out | Glob, Grep, Read, Grep, file_stats | 3/3 |
| expC 3 | H05 | 1 | wrong_value | error_max_turns | 3 | 있음(제자리 수정 과제의 입력 파일), Write/Edit 없음 | svc_04.conf:6, svc_05.conf:1 등이 old.internal:8080 그대로(기대 new.internal:9090) | Glob, Grep, Read x6 | 3/3 |
| expC 3 | H05 | 3 | wrong_value | error_max_turns | 3 | 있음(제자리 수정), Edit 있음 | svc_08.conf:8이 old.internal:8080 그대로 | Glob, Grep, Read x6, Edit x6 | 3/3 |
| expC 4 | H02 | 2 | missing_output | error_max_turns | 4 | 없음, Write 없음 | output file not found: total_lines.out | Glob, file_stats x12, Grep x2 | 3/3 |
| expC 4 | H04 | 1 | missing_output | error_max_turns | 4 | 없음, Write 없음 | output file not found: wrong_docs.out | Glob, Grep x2, file_stats x10, Grep | 3/3 |
| expC 4 | H04 | 2 | missing_output | error_max_turns | 4 | 없음, Write 없음 | output file not found: wrong_docs.out | Glob, Read x10, file_stats x10 | 3/3 |
| expC 4 | H04 | 3 | missing_output | error_max_turns | 4 | 없음, Write 없음 | output file not found: wrong_docs.out | Glob, Grep, file_stats x10, Grep x4 | 3/3 |
| expC 4 | H05 | 3 | wrong_value | error_max_turns | 4 | 있음(제자리 수정), Edit 있음 | svc_08.conf:8이 old.internal:8080 그대로 | Glob, Grep, Read x6, Edit x6 | 3/3 |
| expC 5 | H01 | 3 | wrong_value | success | 5 | 있음, Write 있음 | missing 'app_07.log: 2675', unexpected 'app_08.log: 2675' | Glob, file_stats x10, Write, check_result | 3/3 |
| expC 5 | H07 | 1 | missing_output | error_max_turns | 5 | 없음, Write 없음 | output file not found: timeout.out | Glob, Read x6 | 3/3 |
| expC 7 | M07 | 3 | wrong_value | success | 5 | 있음, Write 있음 | got '줄 수: 13', expected '줄 수: 14' | Glob, Grep, Write, check_result | 3/3 |

### expC 실패의 구성 (요청 확인 사항)
- "실패가 모두 error_max_turns이고 결과 파일이 아직 없는 상태였나?" -> **아니오.** 16건 중 14건이 error_max_turns, 2건은 success + wrong_value(max_turns 5의 H01 run3, 7의 M07 run3)다.
- error_max_turns 실패 14건: 결과 파일이 아직 없는 것(missing_output) 11건(H02 4건, H04 6건, H07 1건)과 제자리 수정 과제 H05의 불완전 수정 3건이다. H05는 출력이 새 파일이 아니라 입력 설정 파일 수정이라 "파일 없음"이 아니라 일부만 고쳐진 상태(run1 max_turns 3은 수정 호출 0번, 나머지 2건은 Edit 6번 뒤 한 파일(svc_08.conf)이 남음)다.
- error_max_turns인데 채점 통과인 108건(max_turns 3: 71, 4: 29, 5: 8) -> **예외 없이 모두 결과 파일이 잘리기 전에 이미 만들어져 있었다**(로그에서 출력 파일에 대한 성공한 Write/Edit 호출이 있음 108/108, 호출 없는 통과 0건). 이 중 50건(3에서 46, 4에서 3, 5에서 1건)은 그 Write가 마지막 응답(설정값번째 응답)에서 일어났고, 58건은 그보다 앞선 응답이었다. 어느 쪽이든 잘린 것은 파일 작성 뒤의 후속 응답(마무리 응답이나 확인 호출)이다.
- error_max_turns 중 통과 비율은 3: 71/79, 4: 29/34, 5: 8/9이고, 한계에 걸린 122건 중 108건(약 89%)이 이미 통과 상태였다. 그래서 채점 통과율(93~98%)과 정상 종료율(3: 34%, 4: 72%, 5: 약 92%)이 크게 다르다.

### 분류 (max_turns 7의 1건과 verify_tool 3건)
- 대상: expC 7 M07 run3, expB verify_tool H07 run3, M07 run1, run2. 4건 모두 같은 과제가 default에서 3/3 통과했다.
- (a) 에이전트의 절차/계산 실수: 4건 모두.
  - M07 3건(verify_tool run1: 15, run2: 13, expC 7 run3: 13): Grep(content 모드) 출력은 정확히 14줄이었고 에이전트가 세는 값이 틀렸다. 3건 모두 Grep `count` 모드는 쓰지 않았다(expA에서 본 패턴과 같다. B, C의 세기 과제 M01, M05, M07에서 출력 파일을 만든 실행 54건 중 count 모드를 쓴 21건은 실패 0건, 쓰지 않은 33건은 실패 3건(이 3건 모두). expA의 16건 중 0건, 20건 중 7건과 합치면 쓴 37건 실패 0, 안 쓴 53건 실패 10건. 사후 분석이고 인과는 가설).
  - H07 run3: 설정 파일 8개를 모두 병렬로 읽었고 내용이 모두 맞았는데(net.conf: `timeout = 30`, `include = tuning.conf`, `timeout = 35`) include 처리 순서에서 덮어쓰기 규칙을 잘못 적용해 20(base.conf의 값)을 답했다. 처리 순서 추적 실수로 보이나(8개 파일 내용은 모두 맞게 읽음) 에이전트 내부 추론은 확인 불가.
- (b) 프롬프트가 모호했음: 0건. H07 프롬프트는 처리 순서와 덮어쓰기 규칙을 명시하고, M07은 "deadline이 들어 있는 줄이 모두 몇 줄"로 명시적이다. 에이전트 내부 해석은 생각(thinking) 비공개라 확인 불가.
- (c) 채점 기준 문제: 0건. 기대 정답은 사람이 대조해 동결한 값(H07 35, M07 14)이고 hand_check와 도구 출력이 일치한다.
- (d) 도구 한계: 확인된 원인은 없다. 단 verify_tool 3건과 expC 7의 M07 run3에서 에이전트는 check_result를 **자신이 쓴 값 그대로**(`contains: "줄 수: 15"`, `"timeout: 20"` 등) 확인해 PASS를 받았다. check_result는 파일 존재, 포함 문자열, 최소 줄 수만 확인하므로 값이 틀려도 PASS가 나온다(설계 한계, 도구 정의 v1은 동결). 이 PASS가 오답을 막지 못한 것은 사실이고, 오답을 만든 원인은 아니다(원인은 (a)).
- 설정별 M07 실패: default 0/3, verify 0/3, verify_tool 2/3, max_turns 3/4/5는 각 0/3, 7은 1/3. 표본이 과제 1개 x 3회라 설정 효과인지 우연인지는 확인 불가.

### 이번에 새로 확인된 H01 짝 맞춤 오류
- expC max_turns 5의 H01 run3은 expA에서 본 것과 같은 오류(app_07의 2675를 app_08에 붙임)를 냈다. 이 실행은 **도구 설명 default**(expA의 long 계열이 아님)이다. expC의 H01 12건 중 실패는 이 1건뿐이고 expB의 H01 6건과 baseline의 H01 3건은 모두 통과했다. 따라서 expA에서 세웠던 "long 설명이 행동을 바꿨을 수 있다"는 설명만으로는 부족하고, 같은 짝 맞춤 오류가 설명과 무관하게 드물게 나타날 수 있다(가설). 파일 이름이 없는 출력 형식이 원인 후보라는 가설은 실험 E(expE)에서 검증한다.
