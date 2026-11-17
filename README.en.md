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
4. Comparison tables `python -m src.eval.exp_compare --exp A..F`, figures `python -m src.eval.plots` (writes results/figures, reads logs only)

## Key results

Full tables and interpretation are in [docs/results.md](docs/results.md) (generated from the results/raw logs by `python -m src.eval.results_summary`; the document is in Korean). Parentheses give the sample size (N tasks, M runs per task, total runs). "Observed" is a value read from the logs; "hypothesis" is interpretation. Main model haiku, 40-task evaluation set.

- Observed (A, tool descriptions): file_stats selection default 62% (15/24) -> long 100% (24/24) (N=8, 3 runs per task, 24 runs, under 30). search_text selection default 0% (0/36) -> long_directive 28% (10/36) (N=12, 3 runs per task, 36 runs). Success is 95-100% in all four settings (each N=40, 3 runs per task, 120 runs), so the ceiling effect hides any success-rate difference. Hypothesis: describing when to use a tool increases its selection. ([Figure 1](results/figures/fig1_expA_selection.png))
- Observed (B, verification prompts): check_result use default 50% (60/120) -> verify 90% (108/120), verify_tool 93% (112/120) (N=40, 3 runs per task, 120 runs). check_result does not verify values, so the increase shows more verification behaviour, not more accuracy. ([Figure 2](results/figures/fig2_expB_check_result.png))
- Observed (C, max turns): normal-termination rate at max_turns 3: 34% (41/120), 4: 72% (86/120), 5: 92% (111/120), 7: 100% (120/120) (each N=40, 3 runs per task, 120 runs). Success falls much less (93%, 96%, 98%, 99%). Hypothesis: most runs cut at the limit had already written the result file (error_max_turns yet graded pass: 71/79, 29/34, 8/9). ([Figure 3](results/figures/fig3_expC_pass_vs_normal.png))
- Observed (D, model): on the same 40 tasks x 1 run (40 runs) success is 100% (40/40) for both haiku and sonnet; mean cost $0.0015 vs $0.0139 (9.2x by total). Hypothesis: the ceiling effect means this set cannot separate the models' accuracy. ([Figure 4](results/figures/fig4_expD_cost_responses.png))
- Observed (E, file name in file_stats output): H01 passes 0/3 -> 3/3 (N=1, 3 runs), but the same-period control (expEctl) passes 1/3. Hypothesis level only; the effect is not established. All 5 failures (3 long, 2 expEctl) are the same name-value pairing error.
- Observed (F, total match count in search_text output): success expFctl 90% (18/20), expF 95% (19/20) (N=4, 5 runs per task, 20 runs, under 30). Effect not confirmed: the intervention reached (runs that used search_text) only 5/20 per condition, and all 3 failures had the correct count in a tool output but the agent miscounted. ([Figure 5](results/figures/fig5_expEF_pass_by_task.png))
- Observed (consistency): the share of repeated runs of the same task with the same tool order is default 49% (59/120 pairs), verify_tool 71% (85/120 pairs) (each N=40, 3 runs per task). Hypothesis: the verification prompt stabilises the order (comparison with the chance range: not verified). ([Figure 6](results/figures/fig6_consistency.png))

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
