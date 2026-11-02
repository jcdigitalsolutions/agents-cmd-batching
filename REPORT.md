# Command batching for AI coding agents — public benchmark report

**Date:** 2026-11-02  
**Approach:** Deterministic sequencing of already-known shell commands using `delayed-seq` and an `AGENTS.md` selection rule.

## Summary

This project investigates whether an AI coding agent can reduce token consumption and execution overhead by delegating predictable shell command sequences to a small executable, rather than asking the model to choose each next command. The intervention does **not** compress the model's context or change the underlying model.

Two matched baseline-versus-wrapper-selection studies covered **288 assigned coding sessions** across **Go, Rust, Python, TypeScript, and JavaScript**. Both used Codex with DeepSeek V4.1 Flash at low reasoning effort, three concurrent sessions at most, and three repetitions per scenario/language/condition. Numbers below are observations of the recorded experiments, not guaranteed improvements.

## Method

The control used the task environment's baseline agent guidance. Treatment appended the exact paragraph in [AGENTS_APPEND.md](AGENTS_APPEND.md) and made `delayed-seq` available. The wrapper runs one shell command after another, stops on the first failure, and ordinarily waits five seconds before execution.

The studies measured cached and uncached input tokens, output tokens, tool calls, elapsed assignment durations, and objective test outcomes. Weighted units are an **illustrative proxy for relative cost**:

```text
weighted_units = 0.1 × cached_input + uncached_input + 5 × output
```

Output includes reasoning in the recorded provider accounting; reasoning must not be counted twice. Weighted units are **not actual billed dollars**. Provider-facing model-request boundaries were unavailable, so the number of model calls avoided was **not directly measured**.

## Study A — Go and Rust (72 assignments)

Six Go and six Rust scenarios were run three times each under baseline and treatment, for 36 assignments per condition. Scenarios covered multi-module features, concurrency/retries, durable record migration, cross-module debugging, input validation, and compatibility refactoring.

| Metric | Baseline | Wrapper selection |
| --- | ---: | ---: |
| Assigned trials | 36 | 36 |
| Objectively correct | 21 (58.3%) | 23 (63.9%) |
| Trials with measured token usage | 34 | 36 |
| Mean weighted units per measured trial | 211,011.9 | 196,075.4 |
| Mean raw tokens per measured trial | 1,140,286.4 | 1,059,123.9 |
| Tool calls across all assignments | 725 | 689 |
| Sum of assignment durations | 4,735.8 s | 3,885.7 s |
| Observed wrapper invocations | 0 | 54 |

The treatment had **7.1% lower mean weighted units per measured trial**, **5.0% fewer tool calls**, and **18.0% lower summed assignment durations** in this sample. Two baseline assignments were interrupted by host disk exhaustion and had no measured usage; cost means therefore have unequal denominators.

The prespecified primary paired endpoint compared the **20 pairs where both implementations were correct**: median wrapper-minus-baseline weighted-unit difference **−11,039.7**, with a descriptive scenario-cluster bootstrap 95% interval **[−36,659.1, +13,776.6]**. Since this interval crosses zero, the study does **not** establish reliable general token savings.

### Blinded code-quality evaluation

A separately run blinded parent-model judge scored candidate patches on six 1–5 dimensions (maintainability, design/API fit, idiomaticity, error handling, tests, and avoiding unnecessary complexity).

| Composite quality (out of 5) | Baseline | Wrapper |
| --- | ---: | ---: |
| All 36 pairs | 4.398 | 4.602 |

Across the **21 pairs where both sides were objectively correct**, the mean wrapper-minus-baseline composite difference was only **+0.032**, and median difference **−0.167**. This is consistent with broadly similar observed quality but does **not** establish statistical equivalence. Ratings are single-model judgments; no independent human calibration was performed.

## Study B — Python, TypeScript, JavaScript (216 assignments)

Twelve equivalent functional scenarios were represented in each language, with three repetitions per condition: **108 assignments per condition**. **214 sessions completed; two treatment sessions failed due to provider routing**. Maximum concurrent coding sessions: three.

| Metric | Baseline | Wrapper selection |
| --- | ---: | ---: |
| Assigned sessions | 108 | 108 |
| Completed sessions | 108 | 106 |
| Objectively correct under strict scope | 19 (17.6%) | 22 (20.4%) |
| Total measured weighted units | 25,945,833.4 | 24,716,985.0 |
| Median assignment duration | 136.7 s | 132.5 s |
| Total recorded assignment duration | 14,514.7 s | 14,378.6 s |
| Tool calls | 2,385 | 2,229 |
| Wrapper invocations | 0 | 66 |

Because two treatment sessions failed and lack comparable usage, total token figures **must not** be read as a fully balanced cost saving. The paired unconditional median difference across 106 complete pairs was **−5,328 weighted units**. In the **14 pairs where both implementations passed all objective checks**, the median difference was **+4,867.9 units** (slightly favoring baseline), with a descriptive 95% interval **[−57,484.7, +33,183.4]**. It crosses zero.

The strict objective score was substantially affected by a **benchmark design mismatch**: Python agents often wrote `python_tests/` as suggested by repository guidance although only `tests/` was permitted; TypeScript agents generated lockfiles or altered package configuration outside its frozen write scope. Of 101 behaviorally passing submissions, 60 failed only the write-scope contract. JavaScript submissions were scope-compliant. These failures were retained rather than retrospectively rescored, but they limit interpretation of the cross-language correctness figures.

The second study produced blinded review packets, but **no paid code-quality judge evaluation was completed**. It cannot support claims about quality equivalence in Python/TypeScript/JavaScript.

## Interpretation

The Go/Rust experiment showed a favorable direction in measured cost and speed, with roughly similar quality among objectively correct implementations. The polyglot experiment showed a smaller and mixed efficiency advantage, with significant rubric-design limitations. The two studies should **not** be pooled into one asserted universal savings percentage.

The observed behavior supports trying the wrapper as an **opt-out default** for known, decision-independent command sequences. It does not justify claiming that every task will use fewer tokens, that the wrapper speeds up every language, or that code-quality equivalence has been proven.

## Transparency and limitations

- This repository distributes the executable, tested agent-guidance paragraph, and this narrative report only. It **does not include raw transcripts, individual workspaces, evaluation harnesses, or underlying trial records**; independent numerical replication is therefore limited.
- Studies used purpose-built repositories, not large production codebases.
- Sample sizes, provider variability, and failure-handling limit causal interpretation.
- Actual model API request counts and provider-billed dollar costs were not measured.
- The Go/Rust run had two host-disk infrastructure interruptions and a mid-run scope-accounting correction, followed by offline reevaluation.
- The polyglot study had two provider-routing failures and a major task-guidance/write-scope mismatch.
- Wrapper invocations were verified, but tool-call reduction does not by itself prove model-request reduction.
- The parent-model review for Go/Rust reported 40 paid attempts, 37 archived ratings and one setup call; two discarded attempts had unknown usage. Review tokens were kept separate from coding-agent usage.

## Practical adoption

Install the wrapper, append the exact [AGENTS_APPEND.md](AGENTS_APPEND.md) rule, keep project-specific validation requirements, and use ordinary commands whenever debugging or exploration requires an intermediate model decision. See [README.md](README.md).
