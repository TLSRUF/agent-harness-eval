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
- Easy and medium tasks mostly have min_steps of 2 or less while all hard tasks have 3 or more, so the effect of step count cannot be separated from the effect of task type.
- The reported num_turns equals tool calls + 1 (all 120 baseline runs), but the max_turns limit appears to be counted in model responses, not in num_turns (hypothesis: 3 successful runs had num_turns 21-24 under max_turns=20 without error_max_turns, with 5-7 model responses). Parallel calls within one response are counted per call in num_turns.
- In experiment C most error_max_turns runs were cut off at the wrap-up response after the result file had been written (all 108 passing runs had the file written first), so the grading pass rate and the normal-termination rate (1 - error_max_turns rate) should be read together.
- The limit rule appears to stop when the number of model responses would exceed max_turns (hypothesis: consistent at max_turns 3, 4 and 5; undecidable at 7 and 20); the definition is not confirmed.
- `file_stats` output does not contain the file name, so when several files are queried in parallel the pairing of calls and results can only be matched by order. In experiment A this pairing error was observed in 5 runs of H01 (the tool output itself was correct). Tool definitions v1 are frozen, so this was not fixed.
- Experiment A changes the descriptions of all three tools (search_text, file_stats, check_result) at once, so the effect cannot be separated per tool, nor can the influence of one tool's description on the choice of another tool.

## Contributions
This project is under active development and is not accepting external contributions (pull requests or issues) for now. We will update this notice once things settle.

## License
MIT. See [LICENSE](LICENSE).
