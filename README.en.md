# agent-harness-eval

[한국어](README.md) | **English**

(To be written: problem -> approach -> headline numbers, in three lines.)

The primary experiment model is claude-haiku-5-5. claude-sonnet-5-5 is used only for a partial comparison run.

This harness blocks external connectors linked to the account from being loaded into the agent, and aborts the run if the tool list differs from the allow-list.

**Core question:** with the same model, how much do success rate and cost change depending on the harness configuration (tool descriptions, verification step, max turns, model)?

## Quick start
1. Python 3.12: `py -3.12 -m venv .venv`, then `pip install -r requirements.txt`
2. Authentication: `claude login` or `ANTHROPIC_API_KEY` (use only one of the two, never both)
3. `python -m src.agent.smoke`

## Limitations
- The `file_stats` tool counts lines with `str.splitlines()`, so lone CR, U+2028 and similar characters are also treated as line breaks; the evaluation fixtures contain no such characters.

## Contributions
This project is under active development and is not accepting external contributions (pull requests or issues) for now. We will update this notice once things settle.

## License
MIT. See [LICENSE](LICENSE).
