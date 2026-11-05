# Local Codex command-frequency analysis

`scripts/analyze_codex_commands.py` is a read-only observational tool for local Codex rollout histories. It answers six bounded questions:

1. Which shell tool calls, executable families, and normalized command shapes occur most often?
2. How much model-visible tool output was correlated to those calls?
3. Which deterministic `terse` output adapters have measured or plausible opportunities, and what information could they lose?
4. Where are `delayed-seq` batches used, and how large is the deliberately non-causal consecutive-command heuristic?
5. Why were shell commands left unresolved, and which compound forms contain defensible syntax-only executable families?
6. Which normalized two-, three-, and four-command sequences repeat, in what packaging and observable response-boundary contexts?

It does not build or deploy a `terse` runtime wrapper. It also does not establish cached-token behavior, billed cost, or universal command savings.

## Run locally

Use Python 3.10 or newer. The analyzer has no third-party runtime dependencies.

```sh
python3 scripts/analyze_codex_commands.py \
  --codex-home "$HOME/.codex" \
  --since 2026-10-01 \
  --until 2026-10-31 \
  --output-dir "$HOME/codex-command-report"
```

Useful bounds and overrides:

```text
--sessions-dir PATH       override the default CODEX_HOME/sessions root
--include-archived        add CODEX_HOME/archived_sessions
--max-files N             default 1,000
--max-file-bytes N        default 32 MiB per file
--max-total-bytes N       default 512 MiB total
--max-line-bytes N        default 8 MiB per JSONL record
--fingerprint-salt VALUE  optional; adds truncated HMAC fingerprints to JSON
```

The date window is inclusive. Only regular `rollout-*.jsonl` files are read. Directory and file symlinks are skipped, and no file is modified.

The command prints only aggregate counts and the six output paths. Reports are created with `0700` directory and `0600` file permissions:

```text
command_frequency_report.md
command_frequency_report.json
opaque_command_diagnostics.md
opaque_command_diagnostics.json
command_sequence_report.md
command_sequence_report.json
```

The normal report contains additive `opaque_attribution` and `sequence_analysis` sections. The diagnostics files contain the full reason/feature cross-tabs. The sequence files contain the standalone sequence schema and rankings. Prefer an output directory outside the repository. Local reports must not be committed or published without explicit review and approval.

## Observed local envelope forms

The implementation was checked against bounded local schema metadata rather than prompt or output content. Observed forms include:

- `response_item.payload.type = function_call`, with JSON `arguments`, for tools such as `exec_command`;
- `response_item.payload.type = custom_tool_call`, where `name = exec` contains structured `tools.exec_command(...)` calls;
- matching `function_call_output` or `custom_tool_call_output` records keyed by `call_id`;
- `event_msg/item_completed` telemetry and token records, which are not counted as duplicate invocations;
- plain `delayed-seq -- ...`, the routing-proxy marker form, and native `delayed_seq` command lists.

The parser is intentionally conservative. If a future schema or JavaScript object is not understood, it is left out of command-family attribution rather than guessed from text. Invalid JSON, invalid UTF-8, oversized records, partial trailing records, conflicts, and unmatched results are counted as coverage limitations.

Observed sequence-boundary structures include:

- `response_item.payload.type = reasoning` and message roles for user/assistant events;
- `event_msg` `task_started`, `task_complete`, `turn_aborted`, and `item_completed` records;
- `turn_context.turn_id` as a conservative new-turn boundary;
- `token_usage_record.response_id` for verifiable model-response grouping;
- shell calls and outputs linked by exact call ID.

No prompt, reasoning text, message text, output excerpt, raw command, or session ID is retained in a sequence report. A timestamp gap is never used as evidence of a response boundary.

## Command attribution

One shell tool invocation may contain one direct command or multiple underlying commands inside a batch.

- Tool invocations and requested subcommands are reported separately.
- Exact `call_id` matching prevents event echoes from becoming duplicate calls.
- Legitimate repeated calls with distinct IDs remain separate observations.
- Batch and compound output is owned once by its wrapper/invocation, never copied to inferred subcommands.
- Output is attributed to an executable family only for a single high-confidence command; partial syntax never receives exclusive output ownership.
- A dry run, timeout, or failed early batch does not prove later subcommands executed.
- `delayed-seq` success/failure marker lines are counted when present; otherwise subcommand completion remains unknown.

Schema version 2 keeps invocation and requested-command denominators separate from syntactic segments. It reports three attribution confidence levels:

- `high_confidence_single`: one validated executable identity, optionally behind benign literal environment assignments or the known `env`, `command`, and `timeout` wrapper forms;
- `partial_syntactic`: one or more candidate executable families were lexically identified inside a pipeline, boolean chain, command sequence, or simple redirection;
- `unresolved_opaque`: the form is malformed, shell-generating, nested, dynamic, or otherwise not safe to identify.

A partial segment is syntax evidence only. It does not prove that the executable started, succeeded, or produced any part of the combined output. `coverage.opaque_subcommands` remains the count without high-confidence executable attribution for comparability, while new fields split that count into `partial_syntactic_subcommands` and `strict_opaque_subcommands`.

Normalized shapes contain only allowlisted executable/family labels, recognized option names, and placeholders such as `<pattern>` or `<paths>`; values, patterns, paths, environment values, and raw commands are not serialized.

## Ordered sequence analysis

The top-level command report is schema version 3. Its additive `sequence_analysis` section has `sequence_schema_version: 1`; established schema-v2 metrics keep their prior meanings. The standalone sequence JSON also uses sequence schema version 1.

Sequence keys contain:

- `family` or `shape` granularity;
- the ordered tuple of two to four normalized command identities;
- parser-confidence evidence.

Packaging is deliberately excluded from the canonical key. The same ordered identities aggregate into one row whether observed as:

- `explicit_batch`: a known `delayed-seq` or native batch invocation;
- `separate_direct_calls`: successive direct shell invocations;
- `mixed_batch_and_direct`: one batch plus adjacent direct calls;
- `unknown`: a window spanning multiple batches or lacking defensible ordering.

Each canonical row retains separate occurrence counts, distinct-session and source-session support by mode, matched-call coverage, requested-only versus confirmed-executed occurrences, atom-level requested/confirmed/unknown subcommand counts, observed status and failure rate, exclusively attributable output bytes, and intervening-event classes. The cross-mode table reports how many source-session instances contain both explicit-batch and separate-direct evidence, without serializing session identifiers.

Ordering is physical JSONL order within one source file. Files are never merged by timestamp or reused session ID. A reused session ID across source files increases `reused_session_ids_across_sources`; source histories remain separate.

Direct-call boundaries use these evidence classes:

- `same_response_inferred` only when direct calls share the next explicit `token_usage_record.response_id`;
- `separate_response_observed` when adjacent calls resolve to different explicit response IDs;
- `unknown_response_boundary` when no defensible response ID is available.

Intervening classes distinguish `none_observed`, tool output only, an observed assistant reasoning/message action, edits or other tools, user/turn/session boundaries, and unknown. These labels describe the trace, not hidden provider state. An absent reasoning record does not prove that a model decision did not occur.

Custom `exec` bundles with multiple shell calls preserve their source order only when every call site is a separately awaited operation. Their packaging remains `unknown` because this is one outer tool bundle, not proof of separate shell invocations or an explicit batch. `Promise.all`/`allSettled`/`race`/`any` and other non-awaited multi-call bundles are treated as ambiguously ordered and excluded from sequence atoms. A single nested shell call can remain an ordered observation. Shell pipelines, boolean chains, variable expansion, heredocs, and other compound shell expressions remain one invocation; syntax-only segments are never promoted to batch steps.

Sequence counts use overlapping windows by definition. Four consecutive commands produce three pair windows, two triple windows, and one four-command window. `coverage.occurrences_by_length` exposes these overlapping totals. Repeated rankings include only canonical sequences observed at least twice.

`coverage.non_overlapping_occurrences_by_length` separately reports a greedy non-overlapping count per ordered chain. That metric is not used for rankings and does not convert overlapping windows into independent samples.

The transition section reports `P(B next | A)` with its observed denominator and distinct-session support. It also lists low-frequency transitions that produced large exclusively attributable next-command output; these are review priorities, not evidence that either command should be suppressed or batched.

Unknown packaging is broken down as `custom_outer_bundle`, `multiple_batch_boundaries`, or `unresolved_packaging` on each canonical row. Invalid or ambiguous physical records create hard `unknown` boundaries, so sequences are not manufactured across missing data.

Batch requested-versus-confirmed accounting is conservative:

- requested counts are the known subcommands in every batch;
- confirmed counts require explicit success/failure markers or a matched complete status;
- dry runs, timeouts, missing output, malformed wrappers, and unreported early-stopped commands remain unknown;
- batch output is never multiplied across its subcommands.

`batched_fraction` uses only explicit and separate-direct occurrences as its eligible denominator and excludes mixed and unknown windows. It is a descriptive packaging ratio, not a claim about how often batching was safe. `unbatched_same_response_count` is zero unless explicit response-ID evidence supports it; `unbatched_same_response_fraction` uses the same explicit-plus-direct denominator. Repeated sequences with both explicit-batch and same-response direct evidence are ranked separately because that consistency is stronger review evidence than an unknown response boundary.

The conservative candidate table labels parsed family sequences as `plausible_static_sequence`, `already_batched`, `mixed_evidence_requires_review`, `decision_dependent`, or `unsafe_or_ambiguous`, with sanitized normalized-shape examples. Observed failures force a decision-dependent classification before mixed, batched, or otherwise static labels are considered. These are review aids and upper bounds, not automatic rewrite instructions.

## Opaque reason diagnostics

Each structurally non-simple command receives one primary reason using deterministic precedence and may have secondary flags:

```text
null_byte_or_invalid
shell_function_or_control_flow
variable_or_command_expansion
redirect_or_heredoc
subshell_or_group
command_sequence
boolean_chain
shell_pipeline
multiline_script
environment_assignment
unsupported_quote_or_lexer
unknown_or_other
```

The lexer distinguishes operators in quotes and comments from real operators, handles escapes, skips literal `#` content in words, and fails closed on unbalanced quotes, NUL bytes, excessive commands, or unexpected forms. Diagnostics include command/session counts, matched invocation counts, execution forms, confidence, secondary flags, byte-derived token ranges, and syntax-only family cross-tabs. Reason counts explicitly reconcile to the non-high-confidence command count.

The supported attribution expansions are intentionally bounded:

- leading literal assignments when shell-control environment names such as `PATH`, `BASH_ENV`, `LD_PRELOAD`, and `IFS` are not used;
- `env` with validated assignment/option forms, `command` without lookup-only modes, and `timeout` with a validated duration;
- top-level `|`, `&&`, `||`, `;`, background `&`, and newline boundaries where every segment resolves to one lexical executable;
- simple redirection removal, including numeric file-descriptor duplication such as `2>&1`.

Command/parameter expansion, backticks, heredocs and here-strings, process/command substitution, subshells, groups, shell functions, loops/conditionals, `eval`, and ambiguous wrapper options remain opaque. This is a bounded lexer, not a complete POSIX/Bash parser.

## Output correlation and measurement

A result is correlated only when the exact session and call ID resolve to one shell invocation and one non-composite output record. Candidate executable attribution additionally requires a high-confidence single command. Common output-value variants are supported:

- plain strings;
- lists of textual content items;
- objects with `stdout`, `stderr`, and `exit_code`.

The report distinguishes:

- captured model-visible bytes and lines;
- median, p90, p95, and maximum output size;
- matched, duplicate, ambiguous, composite, and unmatched results;
- exclusively attributable command output versus output still owned only by a batch or compound invocation;
- success, failure, and unknown status;
- ANSI controls, repeated lines, warnings, traces/assertions, Git hunks, JSON-like output, timestamps, truncation, and binary controls.

Session output bytes are a proxy for the newly introduced observation. They are not evidence that those bytes were uncached or billed at a particular rate. Because reliable request boundaries and usage counters are not assumed, the JSON reports `provider_measured_uncached_input_tokens: null` and `cache_status: "not_measured"`.

## Terse adapter ranking

The analyzer groups observed commands into candidate adapter areas such as:

- `rg` / `grep`;
- successful pytest, Cargo, Go, and JavaScript tests;
- compiler and linter output;
- `git status`, history, and diff;
- package managers and filesystem/source reads.

Safe simulations operate only on already captured output:

- strip ANSI controls;
- retain pytest summaries and warnings for successful runs;
- retain test summaries/warnings/ignores for successful runs;
- collapse clean compiler/linter success only when no warning is present.

The simulation never reruns a command and never changes files. Failing, truncated, ambiguous, unsupported, `git diff`, and source-read output remain passthrough or high-risk. Every candidate lists its edge cases, fallback behavior, and information-loss risks.

Ranking uses the measured output reduction, then total observed output and call frequency. A frequent short command therefore does not automatically outrank a moderately frequent verbose log.

Token ranges are heuristic:

```text
lower = UTF-8 bytes / 6
point = UTF-8 bytes / 4
upper = UTF-8 bytes / 3
```

These are explicitly not tokenizer counts. The eventual runtime wrapper still requires a controlled A/B benchmark that measures task success, extra model calls, retries, and lost-diagnostic recovery.

## Synthetic illustrative example

The following is illustrative only, not a measured finding:

```sh
delayed-seq --initial-delay 0 -- \
  'python -m pytest -q' \
  'git diff -- src'
```

A synthetic trace with one successful pytest call might produce:

```text
pytest_success:
  calls: 1
  matched_output_count: 1
  observed_output_bytes: 2400
  simulated_saved_bytes: 1800
  safety_class: safe_to_aggregate

git_diff:
  calls: 1
  matched_output_count: 1
  safety_class: requires_original_output_recovery
  simulated_saved_bytes: 0
```

The second row intentionally shows no recommended reduction even if a diff is large. Removing context from a diff can invalidate review or patch reasoning.

If local histories are unavailable, the analyzer and synthetic tests still run, but real command frequencies must be reported as unmeasured.

## Validation

```sh
python3 -m unittest discover -s python_tests -v
python3 -m compileall -q scripts
```

Tests create all rollout fixtures in temporary directories. They do not read real session histories and do not invoke commands extracted from synthetic traces.
