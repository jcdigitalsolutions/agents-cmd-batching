# Agent Command Batching — Benchmark Report

**Published:** November 2, 2026  
**Implementation:** `delayed-seq` executable + the selection rule in [AGENTS_APPEND.md](AGENTS_APPEND.md)

## Overview

**Agent Command Batching showed practical efficiency gains in two controlled studies comprising 288 coding-agent assignments across five languages.** The approach packages predictable shell commands into a deterministic sequence instead of requiring the agent to orchestrate each step separately. It preserves full model context and does not require model modifications.

The strongest results came from the Go/Rust study: **7.1% lower average weighted-token consumption, 18.0% lower summed task runtime, and 5.0% fewer tool calls** for the wrapper condition. The larger Python/TypeScript/JavaScript study showed a smaller, generally favorable cost trend and nearly unchanged overall runtime. Neither study revealed a consistent correctness disadvantage attributable to the wrapper. A blinded judge found **broadly similar code quality among objectively correct Go/Rust implementations**.

These are measured outcomes, not promises that every coding task will benefit. The two studies differed in design and evaluation quality, so their percentages are reported separately rather than pooled into a single headline figure.

## At a glance

| Study | Assigned coding sessions | Weighted-token result | Runtime result | Code quality |
| --- | ---: | --- | --- | --- |
| Go + Rust | 72 | **7.1% lower mean per measured trial** | **18.0% lower summed durations** | Blinded review: broadly similar among correct implementations |
| Python + TypeScript + JavaScript | 216 | **−5,328 weighted units median across 106 complete pairs** | **0.94% lower summed durations** | Not independently judged |
| **Total coverage** | **288** | Reported separately | Reported separately | No universal equivalence claim |

The wrapper's role is selective. It is meant for *two or more already-known commands that can run consecutively without a new model decision*, such as formatting then testing. It is not intended to replace exploration, error interpretation, or decision-dependent debugging.

## How the approach works

The control condition used baseline agent instructions. The treatment added the exact [AGENTS_APPEND.md](AGENTS_APPEND.md) instruction and made the original [delayed-seq](delayed-seq) executable available.

The script runs explicitly provided shell commands in order, returns a nonzero failure immediately, forwards cancellation signals, and applies a bounded overall deadline. Its benchmarked default is a five-second initial delay. Optional source-quiet checks do **not** prove that prior edits finished successfully; validation must follow confirmed edit completion.

Both studies used Codex with DeepSeek V4.1 Flash, low reasoning effort, at most three concurrent coding sessions, and three repetitions per scenario and condition. The weighted-token proxy was:

```text
weighted_units = 0.1 × cached_input + uncached_input + 5 × output
```

Reasoning tokens are already included in the recorded output and must not be double-counted. These weighted units are **not billed dollars**. Inference request boundaries were not available in the saved traces, so the experiments do not directly quantify eliminated model API calls.

## Study 1 — Go and Rust: 72 assignments

The study included six Go and six Rust engineering scenarios, each executed three times under baseline and wrapper-selection. Work covered concurrency/cancellation, migrations, validation, multi-module features, cross-module debugging, and compatibility refactoring.

| Measurement | Baseline | Wrapper-selection |
| --- | ---: | ---: |
| Assigned trials | 36 | 36 |
| Objectively correct | 21 (58.3%) | 23 (63.9%) |
| Trials with measured token usage | 34 | 36 |
| Mean weighted units per measured trial | 211,011.9 | **196,075.4** |
| Mean raw tokens per measured trial | 1,140,286.4 | **1,059,123.9** |
| Tool calls | 725 | **689** |
| Summed assignment durations | 4,735.8 s | **3,885.7 s** |
| Observed wrapper invocations | 0 | 54 |

The paired analysis among the **20 pairs where both implementations were objectively correct** found a median wrapper-minus-baseline difference of **−11,039.7 weighted units**. Its descriptive scenario-cluster bootstrap 95% interval was **[−36,659.1, +13,776.6]**, so the experiment shows a favorable direction without establishing a universally reliable saving.

Two baseline sessions were interrupted by host disk exhaustion and lack usage measurements; means therefore use unequal denominators. The evaluator also corrected a generated-file scope-accounting issue mid-study and reevaluated completed workspaces offline without rerunning them.

### Independent blinded code-quality review

A parent-model judge, blinded to treatment labels and token usage, assessed readability, API/design fit, idiomaticity, error handling, test quality, and unnecessary complexity on 1–5 scales.

| Composite rating | Baseline | Wrapper-selection |
| --- | ---: | ---: |
| All 36 paired submissions | 4.398 | **4.602** |

When restricted to the **21 pairs where both submissions were objectively correct**, the mean composite difference was just **+0.032** in favor of wrapper-selection and the median was **−0.167**. The defensible interpretation is **similar observed code quality**, not proof of formal equivalence or systematic improvement. Ratings reflect a single model judge, without independent human calibration.

## Study 2 — Python, TypeScript, JavaScript: 216 assignments

The second study translated 12 matched functional scenarios into each of three languages, with three repetitions under both conditions. It covered 216 assignments; **214 coding sessions completed**, and **two wrapper sessions encountered provider-routing failures**.

| Measurement | Baseline | Wrapper-selection |
| --- | ---: | ---: |
| Assigned sessions | 108 | 108 |
| Completed sessions | 108 | 106 |
| Measured weighted units, total | 25,945,833.4 | 24,716,985.0 |
| Median assignment duration | 136.7 s | **132.5 s** |
| Summed assignment durations | 14,514.7 s | **14,378.6 s** |
| Tool calls | 2,385 | **2,229** |
| Wrapper invocations | 0 | 66 |

Across **106 complete paired assignments**, the unconditional median wrapper-minus-baseline token difference was **−5,328 weighted units**. Because two wrapper runs did not complete, raw *total* token consumption is not a like-for-like cost comparison. Among the **14 pairs passing every strict objective criterion on both sides**, the median difference was **+4,867.9** (slightly favoring baseline), with descriptive interval **[−57,484.7, +33,183.4]**. This smaller subset does not establish a significant cost advantage or disadvantage.

### Important evaluation-harness limitation

The polyglot study's strict correctness score was materially distorted by an inconsistency between task guidance and permitted write paths. It should **not be treated as a clean measure of language-specific code generation ability**.

- **211 of 214 completed sessions passed their public checks.** Protected behavioral tests were more demanding: **101 passed** those checks.
- Of those **101 behaviorally passing submissions, 60 were rejected solely by the frozen write-scope policy**.
- Python agents frequently created `python_tests/` following repository guidance, while the scorer allowed only `tests/`.
- TypeScript runs frequently produced `package-lock.json` or changed `package.json`, while the scorer permitted only `src/` and `tests/`.
- JavaScript assignments did not encounter this write-scope mismatch.

For completeness, strict pass counts were **19/108 baseline** and **22/108 wrapper**. Those low percentages include both genuine failures exposed by protected tests and scope rejections triggered by the benchmark design. The original scores were preserved rather than retroactively redefined. Public-test success alone must also not be mistaken for full behavioral correctness.

No blinded code-quality judge was run for this polyglot study; it cannot support a claim of cross-language code-quality equivalence.

## What these results mean for adoption

The evidence supports **using the tested guidance as an opt-out default** when a coding agent has an already-justified command sequence. The Go/Rust study showed meaningful reductions in measured cost and runtime with broadly comparable quality among correct submissions. The larger polyglot study demonstrated deployment across three more languages, a modest favorable cost signal, and no substantial overall runtime penalty.

The mechanism is intentionally modest: delegate predictable command execution to ordinary software, and reserve model reasoning for decisions that need it. It is compatible with retaining the agent's full relevant context.

This does **not** mean the wrapper wins every scenario. Particularly when a task needs iterative diagnosis, fewer tool calls may not translate into fewer model requests or lower token cost. The study also does not prove savings increase with repository size: scenarios used purpose-built fixtures rather than production-scale projects.

## Publication notes and limitations

This repository intentionally distributes only the wrapper, tested instruction paragraph, installation guide, and this public-facing report. It excludes raw session transcripts, workspace snapshots, benchmark implementation, private paths, provider settings, and local infrastructure. As a result, readers cannot independently recompute every published metric from this repository alone.

Results are descriptive. The Go/Rust paired interval and polyglot paired interval both cross zero; neither proves universal savings. Model API request counts and actual billed dollar amounts were not measured. The Go/Rust study included host-disk failures and a scope-accounting fix. The polyglot study included provider-routing failures and the instruction/scope mismatch described above. The Go/Rust judge phase involved 40 paid attempts, of which 37 produced archived ratings, one was a setup call, and two discarded attempts had unknown usage; judge usage was excluded from coding-agent costs.

## Getting started

See [README.md](README.md) to install the executable and append the exact tested guidance from [AGENTS_APPEND.md](AGENTS_APPEND.md). Keep project-specific checks, interpret failures before deciding what to do next, and never start follow-up validation before edits have successfully completed.