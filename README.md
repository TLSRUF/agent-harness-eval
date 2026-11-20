# agent-harness-eval

**한국어** | [English](README.en.md)

작성자: 신민결 · LinkedIn: (주소 확인 불가, 입력 필요)

## 30초 요약

- 하는 일: Claude Agent SDK로 만든 Haiku 5.5 도구 사용 에이전트를 동결한 40개 과제로 채점하고, 하네스 설정(도구 설명, 검증 지시, 최대 턴 수, 모델)을 하나씩만 바꿔 채점 통과율, 도구 선택률, 비용 변화를 잰다(실험 A~F, 설정별 40개 과제 x 3회 = 120건 기준).
- 발견 1(도구 설명, 실험 A): file_stats 선택률이 default 62% (15/24)에서 long 100% (24/24)로 올랐다(N=8, 24건, 30건 미만). 채점 통과율은 네 설정 모두 95~100%(각 N=40, 120건)라 차이를 가려 볼 수 없다.
- 발견 2(검증 지시, 실험 B): check_result 사용률이 default 50% (60/120)에서 verify 90% (108/120), verify_tool 93% (112/120)로 늘었다(N=40, 120건). 이 도구는 값의 정확성을 확인하지 않으므로 검증 행동이 늘었다는 뜻일 뿐 정확성의 근거는 아니다.
- 발견 3(최대 턴 수, 실험 C): max_turns 3에서 정상 종료율은 34% (41/120)인데 채점 통과율은 93% (112/120)로 덜 떨어졌다(N=40, 120건). error_max_turns인데 통과한 108건은 모두 결과 파일 쓰기가 성공한 뒤에 잘렸다.
- 한계 1: 베이스라인 채점 통과율이 이미 100% (120/120)라 천장 효과로 설정 간 통과율 차이를 가리기 어렵다(실험 D도 haiku 100% (40/40), sonnet 100% (40/40)).
- 한계 2: 실험 E는 H01 한 과제 x 3회, 실험 F는 변형이 닿은 실행이 조건당 5/20뿐이라 효과를 확정하지 못했다(가설 수준). 해석은 "관찰"과 "가설"로 나눠 적었다.
- 읽는 법: 모든 비율은 (맞은 수/표본 수)로 적었고 30건 미만은 경고를 붙였다. 상세 표는 [docs/results.md](docs/results.md).

## 목차

- [핵심 발견](#핵심-발견)
- [실험 A~F 한눈에](#실험-af-한눈에)
- [설계 원칙](#설계-원칙)
- [재현 방법](#재현-방법)
- [주요 결과](#주요-결과)
- [한계](#한계)
- [기여 안내 / Contributions](#기여-안내--contributions)
- [라이선스 / License](#라이선스--license)

## 핵심 발견

주 실험 모델은 claude-haiku-5-5이며, claude-sonnet-5-5는 비교용 부분 실행(실험 D)이다. 아래 괄호는 표본 크기다. "관찰"은 로그에서 읽은 값, "가설"은 해석이다.

- 도구 설명(A): file_stats 선택률 default 62% (15/24) -> long 100% (24/24)(N=8, 24건, 30건 미만), search_text 선택률 default 0% (0/36) -> long_directive 28% (10/36)(N=12, 36건). 가설: 도구 설명에 쓰임새를 적으면 도구 선택이 늘어난다. 채점 통과율은 네 설정 모두 95~100%(각 120건)다.
- 검증 지시(B): check_result 사용률 50% (60/120) -> 90% (108/120), 93% (112/120)(N=40, 120건). 이는 검증 행동의 증가이며 정확성 증가의 근거가 아니다(check_result는 값을 검사하지 않는다).
- 최대 턴 수(C): 정상 종료율 max_turns 3 34% (41/120), 4 72% (86/120), 5 92% (111/120), 7 100% (120/120)(각 N=40, 120건)인데 채점 통과율은 93%, 96%, 98%, 99%(각 120건)다. 한도에 걸렸지만 통과한 108건은 모두 쓰기 성공 뒤에 잘렸고, 마무리 응답에서 잘렸다는 직접 증거는 없다(가설).
- 모델(D): 같은 40개 과제 x 1회(총 40건)에서 채점 통과율은 haiku 100% (40/40), sonnet 100% (40/40)로 같고 평균 비용은 $0.0015 대 $0.0139(비용 합 비율 9.2배)다. 가설: 천장 효과로 모델 간 차이를 가린다.
- 출력 변형(E, F): E는 H01 한 과제 3회씩 expEctl 1/3 대 expE 3/3(N=1, 총 6건), F는 expFctl 18/20 대 expF 19/20(N=4, 총 20건)이며 둘 다 30건 미만이라 효과를 확정하지 못했다.

## 실험 A~F 한눈에

설정은 한 번에 변수 하나만 바꿨다. 표본은 N(과제 수), 반복(과제당 횟수), 총 건수다. 상세는 [docs/results.md](docs/results.md).

| 실험 | 바꾼 변수 | 표본 | 핵심 관찰 | 그림 |
|---|---|---|---|---|
| A | 도구 설명(default, short, long, long_directive) | N=40, 3회, 총 120건 x 4설정 | file_stats 선택률 62% (15/24) -> 100% (24/24), 채점 통과율은 95~100% | [그림 1](results/figures/fig1_expA_selection.png) |
| B | 검증 지시(default, verify, verify_tool) | N=40, 3회, 총 120건 x 3설정 | check_result 사용률 50% (60/120) -> 90% (108/120), 93% (112/120) | [그림 2](results/figures/fig2_expB_check_result.png), [그림 6](results/figures/fig6_consistency.png) |
| C | max_turns(3, 4, 5, 7, 기준 20) | N=40, 3회, 총 120건 x 4설정 | 정상 종료율 34% (41/120) -> 100% (120/120), 채점 통과율 93% -> 99% | [그림 3](results/figures/fig3_expC_pass_vs_normal.png) |
| D | 모델(haiku, sonnet) | N=40, 1회, 총 40건 x 2모델 | 채점 통과율 100% (40/40) 대 100% (40/40), 비용 합 9.2배 | [그림 4](results/figures/fig4_expD_cost_responses.png) |
| E | file_stats 출력에 파일 이름 | H01 N=1, 3회, 총 6건(30건 미만) | expEctl 1/3 대 expE 3/3, 효과 미확정 | [그림 5](results/figures/fig5_expEF_pass_by_task.png) |
| F | search_text 출력에 전체 일치 줄 수 | N=4, 5회, 총 20건 x 2조건(30건 미만) | expFctl 18/20 대 expF 19/20, 효과 확인하지 못함 | [그림 5](results/figures/fig5_expEF_pass_by_task.png) |

## 설계 원칙

- 평가셋 동결: 과제 40개(쉬움 15, 보통 17, 어려움 8), 채점 함수, 정답 풀이, 도구 정의, 설정 기본값의 sha256을 MANIFEST.json에 고정하고(2026-11-09) 바뀌면 테스트가 실패한다. 같은 시험으로 비교해야 설정 변경의 효과를 분리할 수 있기 때문이다.
- 한 번에 변수 하나: 모델, 프롬프트 버전, 최대 턴, 도구 설명 버전은 결과 파일에 함께 저장한다.
- 표본 크기 자동 표기: 모든 리포트의 비율에 N, 반복, 총 건수가 붙고 30건 미만이면 경고가 붙는다.
- 관찰과 가설 분리: 로그에서 읽은 값은 "관찰", 해석은 "가설", 근거가 없으면 "확인 불가"로 적는다. 사후 분석은 사후라고 표시한다.
- 최소 권한 실행: 과제마다 임시 폴더를 cwd로 쓰고 허용 도구를 명시적으로 제한하며 임시 폴더 밖 접근을 막는다. 계정에 연결된 외부 커넥터가 에이전트에 로드되지 않도록 차단하고, 도구 목록이 허용 목록과 다르면 실행을 중단한다.
- 전부 기록하고 이어하기: 모든 실행을 trajectory jsonl로 저장하고(메시지, 도구 호출, 결과, 토큰, 비용 추정, 지연, 설정), 사용량 한도가 감지되면 안전하게 멈추고 이어서 돌릴 수 있다. 큰 실행 전에는 예상 호출 수를 보여주고 확인을 받는다.
- 인증과 비밀 정보: 인증은 코드에서 다루지 않고 SDK가 환경(claude login 또는 ANTHROPIC_API_KEY)으로 처리한다. 비밀 정보는 코드, 로그, 커밋에 넣지 않는다.

## 재현 방법

1. 저장소를 받고 설치한다: `git clone <저장소 주소>`, `cd agent-harness-eval`, `py -3.12 -m venv .venv`, `.venv\Scripts\activate`, `pip install -r requirements.txt` (Python 3.12).
2. 모델 호출 없이 확인한다: `python -m pytest -q`(채점기, 도구, 집계 코드 테스트), `python -m src.eval.freeze --verify`("동결 일치"가 나와야 한다). `results/raw`는 용량 때문에 저장소에 없어서, 로그가 있어야 하는 테스트는 건너뛴다.
3. 모델을 호출하려면 인증이 필요하다: `claude login` 또는 `ANTHROPIC_API_KEY` 중 하나만 쓰고 둘을 동시에 설정하지 않는다. 이 저장소의 측정은 claude login으로 실행했다.
4. 연결 확인(모델 호출 1회): `python -m src.agent.smoke`.
5. 실험 실행 예: `python -m src.eval.batch --experiment expA --tasks E01,H01 --runs 1 --config-name long`. 호출 수를 보여주고 확인을 받는다. 구독 한도가 작으면 나눠서 돌린다.
6. 표와 그림은 `results/raw` 로그에서 만든다: `python -m src.eval.exp_compare --exp A`(A~F), `python -m src.eval.plots`(results/figures), `python -m src.eval.results_summary`(docs/results.md). 로그가 없으면 이 표와 그림은 직접 실험을 실행한 뒤에만 다시 만들 수 있다.
7. 재현성: 같은 모델과 설정으로 다시 돌려도 수치가 같다는 것은 확인 불가다(반복 사이 우연 범위가 있다).

## 주요 결과

전체 표와 해석은 [docs/results.md](docs/results.md)에 있다(`python -m src.eval.results_summary`가 results/raw 로그에서 만든다). 아래는 요약이며, 괄호는 표본 크기(과제 수 N, 과제당 반복 M회, 총 실행 건수)다. "관찰"은 로그에서 읽은 값, "가설"은 해석이다. 주 모델 haiku, 평가셋 40개.

- 관찰(실험 A, 도구 설명): file_stats 선택률 default 62% (15/24) -> long 100% (24/24) (N=8, 과제당 3회, 총 24건, 30건 미만). search_text 선택률 default 0% (0/36) -> long_directive 28% (10/36) (N=12, 과제당 3회, 총 36건). 성공률은 네 설정 모두 95~100%(각 N=40, 과제당 3회, 총 120건)라 천장 효과로 성공률 차이는 가릴 수 없다. 가설: 도구 설명에 쓰임새를 적으면 도구 선택이 늘어난다. ([그림 1](results/figures/fig1_expA_selection.png))
- 관찰(실험 B, 검증 지시): check_result 사용률 default 50% (60/120) -> verify 90% (108/120), verify_tool 93% (112/120) (N=40, 과제당 3회, 총 120건). check_result는 값의 정확성을 확인하지 않으므로 사용률 증가는 검증 행동의 증가일 뿐 정확성 증가의 근거가 아니다. ([그림 2](results/figures/fig2_expB_check_result.png))
- 관찰(실험 C, 최대 턴 수): 정상 종료율 max_turns 3 34% (41/120), 4 72% (86/120), 5 92% (111/120), 7 100% (120/120) (각 N=40, 과제당 3회, 총 120건). 성공률은 93%, 96%, 98%, 99%로 훨씬 덜 떨어진다. 관찰: error_max_turns인데 채점 통과는 3: 71/79, 4: 29/34, 5: 8/9이고 이 108건은 모두 결과 파일 쓰기가 성공한 뒤에 잘렸다(쓰기 직후 48건, 쓰기 뒤 도구 호출이 이어진 것 60건). 마무리 응답에서 잘렸다는 직접 증거는 없다(가설). ([그림 3](results/figures/fig3_expC_pass_vs_normal.png))
- 관찰(실험 D, 모델): 같은 40개 과제 x 1회(총 40건)에서 성공률은 haiku 100% (40/40), sonnet 100% (40/40)로 같고 평균 비용은 $0.0015 대 $0.0139(비용 합 비율 9.2배). 가설: 이 평가셋은 천장 효과로 모델 간 정확도 차이를 가리지 못한다. ([그림 4](results/figures/fig4_expD_cost_responses.png))
- 관찰(실험 E, file_stats 출력에 파일 이름): 같은 날 연달아 돌린 H01 한 과제 3회씩에서 expEctl(long) 1/3 대 expE(long + 파일 이름) 3/3(N=1, 각 3회, 총 6건, 30건 미만). 3일 전에 돌린 expA long은 0/3이다. 가설 수준이며 효과는 확정하지 못했다(같은 날 대조도 3번 중 2번 실패). 실패 5건(long 3, expEctl 2)은 모두 같은 이름-값 짝 오류다.
- 관찰(실험 F, search_text 출력에 전체 일치 줄 수): 성공률 expFctl 90% (18/20), expF 95% (19/20)(N=4, 과제당 5회, 총 20건, 30건 미만). 효과를 확인하지 못함: 변형이 닿은 실행(search_text 사용)이 조건당 5/20이고, 실패 3건은 모두 도구 출력에 정답이 있었는데 에이전트가 틀리게 센 것이다. ([그림 5](results/figures/fig5_expEF_pass_by_task.png))
- 관찰(일관성): 같은 과제를 3번 반복했을 때 도구 호출 순서가 같은 비율은 default 49% (59/120쌍), verify_tool 71% (85/120쌍)(각 N=40, 과제당 3회). 가설: 검증 지시가 순서를 안정화한다(우연 범위와의 비교는 확인 불가). ([그림 6](results/figures/fig6_consistency.png))

## 한계

- `file_stats` 도구는 `str.splitlines()`를 써서 낱개 CR, U+2028 등도 줄바꿈으로 세며, 평가 fixture에는 이런 문자가 없다.
- 쉬움·보통은 min_steps가 대부분 2 이하이고 어려움은 모두 3 이상이라, 단계 수의 효과와 과제 유형의 효과를 분리할 수 없다.
- 보고되는 num_turns는 도구 호출 수 + 1이지만(베이스라인 120건 모두), max_turns 한도는 이 값이 아니라 모델 응답 수 기준으로 보인다(가설: num_turns 21~24인 성공 실행 3건이 max_turns=20에서 error_max_turns 없이 끝났고 응답 수는 5~7이었다). 한 응답 안의 병렬 호출은 num_turns에서 호출마다 센다.
- 실험 C의 error_max_turns 해석: error_max_turns인데 통과한 108건(max_turns 3: 71, 4: 29, 5: 8)은 모두 결과 파일 쓰기가 성공한 뒤에 잘렸다. 쓰기 직후에 잘린 것은 48건(44, 3, 1)이고, 60건(27, 26, 7)은 쓰기 뒤에 도구가 한 번 더 호출됐다(대부분 check_result, H05는 Edit 뒤 Grep). 마무리 응답에서 잘렸다는 직접 증거는 없다(가설). 그래서 채점 통과율과 정상 종료율(1 - error_max_turns 비율)을 함께 본다.
- 한계 규칙은 응답 수가 max_turns를 넘으려 할 때 중단하는 것으로 보이며(가설, max_turns 3, 4, 5에서 일치, 7과 20은 확인 불가) 정의는 확정이 아니다.
- `file_stats`는 출력에 파일 이름이 없어, 파일 여러 개를 병렬로 호출할 때 호출과 결과의 짝을 순서로만 맞춰야 한다. expA에서 H01의 이 짝 맞춤 오류가 5건 관찰됐다(도구 출력은 정확했음). 도구 정의 v1은 동결이라 고치지 않았다.
- 실험 A는 도구 3개(search_text, file_stats, check_result)의 설명을 동시에 바꾼다. 그래서 효과를 도구별로 분리할 수 없고, 설명 하나가 다른 도구 선택에 준 영향도 구분하지 못한다.

## 기여 안내 / Contributions

현재 개발 중이라 외부 기여(PR, 이슈)는 받지 않습니다. 정리가 끝나면 다시 안내합니다.

This project is under active development and is not accepting external contributions (pull requests or issues) for now. We will update this notice once things settle.

## 라이선스 / License

MIT. See [LICENSE](LICENSE).
