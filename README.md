# agent-harness-eval

**한국어** | [English](README.en.md)

(작성 예정: 문제 -> 접근 -> 결과 수치 3줄)

주 실험 모델은 claude-haiku-5-5이며, claude-sonnet-5-5는 비교용 부분 실행이다.

이 하네스는 계정에 연결된 외부 커넥터가 에이전트에 로드되지 않도록 차단하며, 도구 목록이 허용 목록과 다르면 실행을 중단한다.

## 실행 방법
1. Python 3.12, `py -3.12 -m venv .venv`, `pip install -r requirements.txt`
2. 인증: `claude login` 또는 `ANTHROPIC_API_KEY` (둘 중 하나만)
3. `python -m src.agent.smoke`
4. 실험 비교표 `python -m src.eval.exp_compare --exp A~F`, 그래프 `python -m src.eval.plots`(results/figures, 로그만 읽는다)

## 주요 결과

전체 표와 해석은 [docs/results.md](docs/results.md)에 있다(`python -m src.eval.results_summary`가 results/raw 로그에서 만든다). 아래는 요약이며, 괄호는 표본 크기(과제 수 N, 과제당 반복 M회, 총 실행 건수)다. "관찰"은 로그에서 읽은 값, "가설"은 해석이다. 주 모델 haiku, 평가셋 40개.

- 관찰(실험 A, 도구 설명): file_stats 선택률 default 62% (15/24) -> long 100% (24/24) (N=8, 과제당 3회, 총 24건, 30건 미만). search_text 선택률 default 0% (0/36) -> long_directive 28% (10/36) (N=12, 과제당 3회, 총 36건). 성공률은 네 설정 모두 95~100%(각 N=40, 과제당 3회, 총 120건)라 천장 효과로 성공률 차이는 가릴 수 없다. 가설: 도구 설명에 쓰임새를 적으면 도구 선택이 늘어난다. ([그림 1](results/figures/fig1_expA_selection.png))
- 관찰(실험 B, 검증 지시): check_result 사용률 default 50% (60/120) -> verify 90% (108/120), verify_tool 93% (112/120) (N=40, 과제당 3회, 총 120건). check_result는 값의 정확성을 확인하지 않으므로 사용률 증가는 검증 행동의 증가일 뿐 정확성 증가의 근거가 아니다. ([그림 2](results/figures/fig2_expB_check_result.png))
- 관찰(실험 C, 최대 턴 수): 정상 종료율 max_turns 3 34% (41/120), 4 72% (86/120), 5 92% (111/120), 7 100% (120/120) (각 N=40, 과제당 3회, 총 120건). 성공률은 93%, 96%, 98%, 99%로 훨씬 덜 떨어진다. 가설: 한계에서 잘린 실행의 대부분은 결과 파일을 이미 쓴 뒤였다(error_max_turns인데 채점 통과 3: 71/79, 4: 29/34, 5: 8/9). ([그림 3](results/figures/fig3_expC_pass_vs_normal.png))
- 관찰(실험 D, 모델): 같은 40개 과제 x 1회(총 40건)에서 성공률은 haiku 100% (40/40), sonnet 100% (40/40)로 같고 평균 비용은 $0.0015 대 $0.0139(비용 합 비율 9.2배). 가설: 이 평가셋은 천장 효과로 모델 간 정확도 차이를 가리지 못한다. ([그림 4](results/figures/fig4_expD_cost_responses.png))
- 관찰(실험 E, file_stats 출력에 파일 이름): H01 통과 0/3 -> 3/3이지만(N=1, 3회) 같은 시기 대조(expEctl)는 1/3이다. 가설 수준이며 효과는 확정하지 못했다. 실패 5건(long 3, expEctl 2)은 모두 같은 이름-값 짝 오류다.
- 관찰(실험 F, search_text 출력에 전체 일치 줄 수): 성공률 expFctl 90% (18/20), expF 95% (19/20)(N=4, 과제당 5회, 총 20건, 30건 미만). 효과를 확인하지 못함: 변형이 닿은 실행(search_text 사용)이 조건당 5/20이고, 실패 3건은 모두 도구 출력에 정답이 있었는데 에이전트가 틀리게 센 것이다. ([그림 5](results/figures/fig5_expEF_pass_by_task.png))
- 관찰(일관성): 같은 과제를 3번 반복했을 때 도구 호출 순서가 같은 비율은 default 49% (59/120쌍), verify_tool 71% (85/120쌍)(각 N=40, 과제당 3회). 가설: 검증 지시가 순서를 안정화한다(우연 범위와의 비교는 확인 불가). ([그림 6](results/figures/fig6_consistency.png))

## 한계

- `file_stats` 도구는 `str.splitlines()`를 써서 낱개 CR, U+2028 등도 줄바꿈으로 세며, 평가 fixture에는 이런 문자가 없다.
- 쉬움·보통은 min_steps가 대부분 2 이하이고 어려움은 모두 3 이상이라, 단계 수의 효과와 과제 유형의 효과를 분리할 수 없다.
- 보고되는 num_turns는 도구 호출 수 + 1이지만(베이스라인 120건 모두), max_turns 한도는 이 값이 아니라 모델 응답 수 기준으로 보인다(가설: num_turns 21~24인 성공 실행 3건이 max_turns=20에서 error_max_turns 없이 끝났고 응답 수는 5~7이었다). 한 응답 안의 병렬 호출은 num_turns에서 호출마다 센다.
- 실험 C에서 error_max_turns의 대부분은 결과 파일 작성 뒤 마무리 응답에서 잘린 것이어서(통과한 108건 모두 파일이 먼저 만들어짐) 채점 통과율과 정상 종료율(1 - error_max_turns 비율)을 함께 본다.
- 한계 규칙은 응답 수가 max_turns를 넘으려 할 때 중단하는 것으로 보이며(가설, max_turns 3, 4, 5에서 일치, 7과 20은 확인 불가) 정의는 확정이 아니다.
- `file_stats`는 출력에 파일 이름이 없어, 파일 여러 개를 병렬로 호출할 때 호출과 결과의 짝을 순서로만 맞춰야 한다. expA에서 H01의 이 짝 맞춤 오류가 5건 관찰됐다(도구 출력은 정확했음). 도구 정의 v1은 동결이라 고치지 않았다.
- 실험 A는 도구 3개(search_text, file_stats, check_result)의 설명을 동시에 바꾼다. 그래서 효과를 도구별로 분리할 수 없고, 설명 하나가 다른 도구 선택에 준 영향도 구분하지 못한다.

## 기여 안내 / Contributions

현재 개발 중이라 외부 기여(PR, 이슈)는 받지 않습니다. 정리가 끝나면 다시 안내합니다.

This project is under active development and is not accepting external contributions (pull requests or issues) for now. We will update this notice once things settle.

## 라이선스 / License

MIT. See [LICENSE](LICENSE).
