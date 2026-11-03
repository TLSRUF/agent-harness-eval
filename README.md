# agent-harness-eval

(작성 예정: 문제 -> 접근 -> 결과 수치 3줄)

주 실험 모델은 claude-haiku-5-5이며, claude-sonnet-5-5는 비교용 부분 실행이다.

## 실행 방법
1. Python 3.12, `py -3.12 -m venv .venv`, `pip install -r requirements.txt`
2. 인증: `claude login` 또는 `ANTHROPIC_API_KEY` (둘 중 하나만)
3. `python -m src.agent.smoke`

## 기여 안내 / Contributions

현재 개발 중이라 외부 기여(PR, 이슈)는 받지 않습니다. 정리가 끝나면 다시 안내합니다.

This project is under active development and is not accepting external contributions (pull requests or issues) for now. We will update this notice once things settle.

## 라이선스 / License

MIT. See [LICENSE](LICENSE).
