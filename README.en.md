# agent-harness-eval

[한국어](README.md) | **English**

Author: 신민결 · LinkedIn: (URL unknown, to be added)

## 30-second summary

- What it does: grades a Haiku 5.5 tool-using agent built with the Claude Agent SDK on a frozen 40-task eval set, changing one harness setting at a time (tool descriptions, verification prompt, max turns, model) and measuring grading pass rate, tool selection rate and cost (experiments A-F; 40 tasks x 3 runs = 120 runs per setting).
- Finding 1 (tool descriptions, A): file_stats selection went from 62% (15/24) with default to 100% (24/24) with long (N=8, 24 runs, under 30). The grading pass rate is 95-100% in all four settings (N=40 each, 120 runs), so differences cannot be seen.
- Finding 2 (verification prompt, B): check_result use went from 50% (60/120) with default to 90% (108/120) with verify and 93% (112/120) with verify_tool (N=40, 120 runs). The tool does not check value correctness, so this shows more verification behavior, not evidence of correctness.
- Finding 3 (max turns, C): at max_turns 3 the normal-termination rate is 34% (41/120) while the grading pass rate is 93% (112/120) (N=40, 120 runs). All 108 runs that hit error_max_turns yet passed were cut after the result-file write had succeeded.
- Limit 1: the baseline grading pass rate is already 100% (120/120), so a ceiling effect hides differences between settings (experiment D too: haiku 100% (40/40), sonnet 100% (40/40)).
- Limit 2: experiment E is one task (H01) x 3 runs and F has only 5/20 runs per condition that the change reached, so neither effect is established (hypothesis level). Interpretations are split into "observed" and "hypothesis".
- How to read: every rate is written as (hits/sample size); fewer than 30 runs carry a warning. Full tables: [docs/results.md](docs/results.md).

## Contents

- [Key findings](#key-findings)
- [Experiments A-F at a glance](#experiments-a-f-at-a-glance)
- [Design principles](#design-principles)
- [Reproduce](#reproduce)
- [Key results](#key-results)
- [Limitations](#limitations)
- [Contributions](#contributions)
- [License](#license)

## Key findings

The primary model is claude-haiku-5-5; claude-sonnet-5-5 is used only for a partial comparison (experiment D). Sample sizes are in parentheses. "Observed" is read from the logs, "hypothesis" is interpretation.

- Tool descriptions (A): file_stats selection default 62% (15/24) -> long 100% (24/24) (N=8, 24 runs, under 30); search_text selection default 0% (0/36) -> long_directive 28% (10/36) (N=12, 36 runs). Hypothesis: describing when to use a tool increases its selection. The grading pass rate is 95-100% in all four settings (120 runs each).
- Verification prompt (B): check_result use 50% (60/120) -> 90% (108/120), 93% (112/120) (N=40, 120 runs). This is more verification behavior, not evidence of more correctness (check_result does not inspect values).
- Max turns (C): normal-termination rate at max_turns 3 34% (41/120), 4 72% (86/120), 5 92% (111/120), 7 100% (120/120) (N=40, 120 runs each) while the grading pass rate is 93%, 96%, 98%, 99% (120 runs each). The 108 runs that hit the limit yet passed were all cut after a successful write; there is no direct evidence of a wrap-up cut (hypothesis).
- Model (D): on the same 40 tasks x 1 run (40 runs) the grading pass rate is the same, haiku 100% (40/40) and sonnet 100% (40/40), and the mean cost is $0.0015 vs $0.0139 (sum ratio 9.2x). Hypothesis: the ceiling effect hides model differences.
- Output variants (E, F): E is expEctl 1/3 vs expE 3/3 on H01 alone (N=1, 6 runs); F is expFctl 18/20 vs expF 19/20 (N=4, 20 runs). Both are under 30 runs, so no effect is established.

## Experiments A-F at a glance

One variable changed at a time. Sample = N (tasks), runs per task, total runs. Details: [docs/results.md](docs/results.md).

| Experiment | Variable | Sample | Key observation | Figure |
|---|---|---|---|---|
| A | tool descriptions (default, short, long, long_directive) | N=40, 3 runs, 120 runs x 4 settings | file_stats selection 62% (15/24) -> 100% (24/24); grading pass rate 95-100% | [Fig 1](results/figures/fig1_expA_selection.png) |
| B | verification prompt (default, verify, verify_tool) | N=40, 3 runs, 120 runs x 3 settings | check_result use 50% (60/120) -> 90% (108/120), 93% (112/120) | [Fig 2](results/figures/fig2_expB_check_result.png), [Fig 6](results/figures/fig6_consistency.png) |
| C | max_turns (3, 4, 5, 7; baseline 20) | N=40, 3 runs, 120 runs x 4 settings | normal termination 34% (41/120) -> 100% (120/120); grading pass rate 93% -> 99% | [Fig 3](results/figures/fig3_expC_pass_vs_normal.png) |
| D | model (haiku, sonnet) | N=40, 1 run, 40 runs x 2 models | grading pass rate 100% (40/40) vs 100% (40/40); cost sum 9.2x | [Fig 4](results/figures/fig4_expD_cost_responses.png) |
| E | file name in file_stats output | H01 N=1, 3 runs, 6 runs (under 30) | expEctl 1/3 vs expE 3/3, effect not established | [Fig 5](results/figures/fig5_expEF_pass_by_task.png) |
| F | total match count in search_text output | N=4, 5 runs, 20 runs x 2 conditions (under 30) | expFctl 18/20 vs expF 19/20, effect not confirmed | [Fig 5](results/figures/fig5_expEF_pass_by_task.png) |

## Design principles

- Frozen eval set: 40 tasks (15 easy, 17 medium, 8 hard), graders, reference solutions, tool definitions and config defaults are pinned by sha256 in MANIFEST.json (2026-11-09); tests fail if they change. Only the same test lets a setting change be isolated.
- One variable at a time: model, prompt version, max turns and tool-description version are stored in every result file.
- Sample sizes everywhere: every reported rate carries N, runs per task and total runs, and fewer than 30 runs get a warning.
- Observation vs hypothesis: values read from logs are "observed", interpretation is "hypothesis", anything without evidence is "unknown" (확인 불가). Post-hoc analysis is labeled as such.
- Least privilege: each task runs in its own temp folder as cwd with an explicit tool allow-list and no access outside it. External connectors linked to the account are blocked from loading into the agent, and the run aborts if the tool list differs from the allow-list.
- Log everything, resume safely: every run is saved as trajectory jsonl (messages, tool calls, results, tokens, cost estimate, latency, config); usage limits stop the run safely and it can be resumed. Large runs show the expected call count and ask for confirmation.
- Auth and secrets: authentication is not handled in code; the SDK uses the environment (claude login or ANTHROPIC_API_KEY). No secrets go into code, logs or commits.

## Reproduce

1. Get and install: `git clone <repository URL>`, `cd agent-harness-eval`, `py -3.12 -m venv .venv`, `.venv\Scripts\activate`, `pip install -r requirements.txt` (Python 3.12).
2. Check without any model call: `python -m pytest -q` (grader, tool and aggregation tests) and `python -m src.eval.freeze --verify` (should print the freeze-match message). `results/raw` is not in the repository because of its size, so tests that need logs are skipped.
3. Model calls need authentication: use either `claude login` or `ANTHROPIC_API_KEY`, never both. The measurements here were run with claude login.
4. Connection check (one model call): `python -m src.agent.smoke`.
5. Example run: `python -m src.eval.batch --experiment expA --tasks E01,H01 --runs 1 --config-name long`. It shows the call count and asks for confirmation; split large runs if your subscription limit is small.
6. Tables and figures are built from the `results/raw` logs: `python -m src.eval.exp_compare --exp A` (A..F), `python -m src.eval.plots` (results/figures), `python -m src.eval.results_summary` (docs/results.md). Without the logs they can only be rebuilt after running the experiments yourself.
7. Reproducibility: that a rerun with the same model and settings gives the same numbers is unknown (확인 불가); runs vary between repeats.

## Key results

Full tables and interpretation are in [docs/results.md](docs/results.md) (generated from the results/raw logs by `python -m src.eval.results_summary`; the document is in Korean). Parentheses give the sample size (N tasks, M runs per task, total runs). "Observed" is a value read from the logs; "hypothesis" is interpretation. Main model haiku, 40-task evaluation set.

- Observed (A, tool descriptions): file_stats selection default 62% (15/24) -> long 100% (24/24) (N=8, 3 runs per task, 24 runs, under 30). search_text selection default 0% (0/36) -> long_directive 28% (10/36) (N=12, 3 runs per task, 36 runs). Success is 95-100% in all four settings (each N=40, 3 runs per task, 120 runs), so the ceiling effect hides any success-rate difference. Hypothesis: describing when to use a tool increases its selection. ([Figure 1](results/figures/fig1_expA_selection.png))
- Observed (B, verification prompts): check_result use default 50% (60/120) -> verify 90% (108/120), verify_tool 93% (112/120) (N=40, 3 runs per task, 120 runs). check_result does not verify values, so the increase shows more verification behaviour, not more accuracy. ([Figure 2](results/figures/fig2_expB_check_result.png))
- Observed (C, max turns): normal-termination rate at max_turns 3: 34% (41/120), 4: 72% (86/120), 5: 92% (111/120), 7: 100% (120/120) (each N=40, 3 runs per task, 120 runs). Success falls much less (93%, 96%, 98%, 99%). Observed: of the error_max_turns runs that passed (71/79, 29/34, 8/9), all 108 were cut off after the result-file write had succeeded (48 right after the write, 60 with another tool call after it). There is no direct evidence that the cut happened in the wrap-up response (hypothesis). ([Figure 3](results/figures/fig3_expC_pass_vs_normal.png))
- Observed (D, model): on the same 40 tasks x 1 run (40 runs) success is 100% (40/40) for both haiku and sonnet; mean cost $0.0015 vs $0.0139 (9.2x by total). Hypothesis: the ceiling effect means this set cannot separate the models' accuracy. ([Figure 4](results/figures/fig4_expD_cost_responses.png))
- Observed (E, file name in file_stats output): on H01 alone (N=1, 3 runs each, 6 runs, under 30), run back to back on the same day, expEctl (long) passes 1/3 and expE (long + file name) 3/3; expA long, run 3 days earlier, passes 0/3. Hypothesis level only; the effect is not established (the same-day control also failed 2 of 3). All 5 failures (3 long, 2 expEctl) are the same name-value pairing error.
- Observed (F, total match count in search_text output): success expFctl 90% (18/20), expF 95% (19/20) (N=4, 5 runs per task, 20 runs, under 30). Effect not confirmed: the intervention reached (runs that used search_text) only 5/20 per condition, and all 3 failures had the correct count in a tool output but the agent miscounted. ([Figure 5](results/figures/fig5_expEF_pass_by_task.png))
- Observed (consistency): the share of repeated runs of the same task with the same tool order is default 49% (59/120 pairs), verify_tool 71% (85/120 pairs) (each N=40, 3 runs per task). Hypothesis: the verification prompt stabilises the order (comparison with the chance range: not verified). ([Figure 6](results/figures/fig6_consistency.png))

## Limitations
- The `file_stats` tool counts lines with `str.splitlines()`, so lone CR, U+2028 and similar characters are also treated as line breaks; the evaluation fixtures contain no such characters.
- Easy and medium tasks mostly have min_steps of 2 or less while all hard tasks have 3 or more, so the effect of step count cannot be separated from the effect of task type.
- The reported num_turns equals tool calls + 1 (all 120 baseline runs), but the max_turns limit appears to be counted in model responses, not in num_turns (hypothesis: 3 successful runs had num_turns 21-24 under max_turns=20 without error_max_turns, with 5-7 model responses). Parallel calls within one response are counted per call in num_turns.
- Experiment C, error_max_turns runs that still passed: Of the 108 runs that ended with error_max_turns yet passed (max_turns 3: 71, 4: 29, 5: 8), all were cut off after the result-file write had succeeded. 48 (44, 3, 1) were cut right after the write; in 60 (27, 26, 7) one more tool call followed the write (mostly check_result; Grep after an Edit for H05). There is no direct evidence that the cut happened in the wrap-up response (hypothesis). The grading pass rate and the normal-termination rate (1 - error_max_turns rate) should therefore be read together.
- The limit rule appears to stop when the number of model responses would exceed max_turns (hypothesis: consistent at max_turns 3, 4 and 5; undecidable at 7 and 20); the definition is not confirmed.
- `file_stats` output does not contain the file name, so when several files are queried in parallel the pairing of calls and results can only be matched by order. In experiment A this pairing error was observed in 5 runs of H01 (the tool output itself was correct). Tool definitions v1 are frozen, so this was not fixed.
- Experiment A changes the descriptions of all three tools (search_text, file_stats, check_result) at once, so the effect cannot be separated per tool, nor can the influence of one tool's description on the choice of another tool.

## Contributions
This project is under active development and is not accepting external contributions (pull requests or issues) for now. We will update this notice once things settle.

## License
MIT. See [LICENSE](LICENSE).
