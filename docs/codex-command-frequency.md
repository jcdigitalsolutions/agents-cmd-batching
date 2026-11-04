# Local Codex command-frequency analysis

`scripts/analyze_codex_commands.py` is a read-only observational tool for local Codex rollout histories. It answers four bounded questions:

1. Which shell tool calls, executable families, and normalized command shapes occur most often?
2. How much model-visible tool output was correlated to those calls?
3. Which deterministic `terse` output adapters have measured or plausible opportunities, and what information could they lose?
4. Where are `delayed-seq` batches used, and how large is the deliberately non-causal consecutive-command heuristic?

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

The command prints only aggregate counts and the two output paths. Reports are created with `0700` directory and `0600` file permissions:

```text
command_frequency_report.md
command_frequency_report.json
```

Prefer an output directory outside the repository. Local reports must not be committed or published without explicit review and approval.

## Observed local envelope forms

The implementation was checked against bounded local schema metadata rather than prompt or output content. Observed forms include:

- `response_item.payload.type = function_call`, with JSON `arguments`, for tools such as `exec_command`;
- `response_item.payload.type = custom_tool_call`, where `name = exec` contains structured `tools.exec_command(...)` calls;
- matching `function_call_output` or `custom_tool_call_output` records keyed by `call_id`;
- `event_msg/item_completed` telemetry and token records, which are not counted as duplicate invocations;
- plain `delayed-seq -- ...`, the routing-proxy marker form, and native `delayed_seq` command lists.

The parser is intentionally conservative. If a future schema or JavaScript object is not understood, it is left out of command-family attribution rather than guessed from text. Invalid JSON, invalid UTF-8, oversized records, partial trailing records, conflicts, and unmatched results are counted as coverage limitations.

## Command attribution

One shell tool invocation may contain one direct command or multiple underlying commands inside a batch.

- Tool invocations and requested subcommands are reported separately.
- Exact `call_id` matching prevents event echoes from becoming duplicate calls.
- Legitimate repeated calls with distinct IDs remain separate observations.
- Batch output is attributed once to its wrapper invocation, never copied to every requested subcommand.
- A dry run, timeout, or failed early batch does not prove later subcommands executed.
- `delayed-seq` success/failure marker lines are counted when present; otherwise subcommand completion remains unknown.

Simple shell forms are parsed with `shlex`. Pipelines, `&&`, semicolons, redirects, subshells, environment assignments, command substitution, and multiline forms are marked opaque. Normalized shapes contain only executable/family labels, recognized option names, and placeholders such as `<pattern>` or `<paths>`; values, patterns, paths, and raw commands are not serialized.

## Output correlation and measurement

A result is attributed only when the exact session and call ID resolve to one shell invocation and one non-composite output record. Common output-value variants are supported:

- plain strings;
- lists of textual content items;
- objects with `stdout`, `stderr`, and `exit_code`.

The report distinguishes:

- captured model-visible bytes and lines;
- median, p90, p95, and maximum output size;
- matched, duplicate, ambiguous, composite, and unmatched results;
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
