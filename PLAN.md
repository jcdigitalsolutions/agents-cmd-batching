# PLAN.md — Codex command history and tool-output research

## Objective, status and baseline

**Planning artifact only.** This commit authorizes **only this PLAN.md**, not implementation. Repository: \`jcdigitalsolutions/agents-cmd-batching\`; target: \`main\`; inspected HEAD: \`0be829c56f1282cc8b3b97aea4d0fea3f8e01e53\` (\`Update LICENSE\`). Reverify latest remote main and reconcile changes before execution.

Build a **read-only, offline, reproducible Python analyzer** of the user's local Codex session JSONL to answer: (1) which shell commands and tool families are most frequently invoked, directly and within \`delayed-seq\`; (2) how much **actual model-visible output** these commands return; (3) which deterministic **terse-only** command-output adapters merit implementation first, based on estimated avoidable **uncached input** and information-loss risk; (4) where existing command batching is used or might be applicable. Deliver Markdown and machine-readable JSON reports. Never equate output bytes with measured uncached tokens without validated usage and request boundaries. The session data is **not in GitHub**; run only with authorized local access. Do not upload/commit session histories or raw private reports.

**Single integrated workstream.** Extraction, event correlation, command grouping, privacy, output measurement and reporting share one typed representation. No artificial parallel workstreams or \`PLAN_*.md\` files. Do not implement the prospective runtime \`terse\` wrapper as part of this research.

## Verified repository facts and implementation scope

At baseline, the repo contains only \`delayed-seq\`, \`README.md\`, \`AGENTS_APPEND.md\`, \`REPORT.md\`, and \`LICENSE\`. There is no analysis executable or test framework.

**Read first, exact surfaces:**
- \`README.md\` (1–84): standalone Python 3 stdlib wrapper, POSIX shell requirements, installation, published study limitations, no raw benchmark artifacts.
- \`REPORT.md\` (1–113): existing 288-assignment controlled Go/Rust/Python/TypeScript/JavaScript benchmarking, weighted model \`U + 0.1*C + 5*O\`, uncertainty and raw-data privacy restrictions. **Do not modify** or misrepresent it as the new observational study.
- \`AGENTS_APPEND.md\` (1–5): original tested batching selection instruction; **do not change**.
- \`delayed-seq\`: \`SequenceConfig\` (~53), \`ShellCommandRunner.run\` (~142), \`run_sequence\` (~300+), \`_parser\` (~420+), \`main\` (~480+). Arguments after \`--\` are complete shell-command strings; commands run sequentially through \`sh\`, stop on failure, and have bounded delay, total deadline and cancellation. **Do not change its execution semantics.**

**Proposed implementation files and ownership:** \`scripts/analyze_codex_commands.py\` (Python standard library CLI, streaming JSONL, extraction and conservative parsing, output correlation, metrics, redaction, reports); \`tests/test_analyze_codex_commands.py\` (pytest with generated synthetic fixtures); \`docs/codex-command-frequency.md\` (methodology, explicit illustrative example, local invocation, limitations); a brief addition to \`README.md\`. Actual results \`command_frequency_report.md\` and \`command_frequency_report.json\` go into a user-chosen **local output directory**, preferably outside Git, and are not committed without explicit authorization. Pytest is acceptable for tests; production code has stdlib-only dependencies. If repository structure evolves, widen only for compilation/correctness and report deviations.

## Source format and research caveats

Typical Codex rollout history: \`\${CODEX_HOME:-~/.codex}/sessions/YYYY/MM/DD/rollout-*.jsonl\`; optionally \`\${CODEX_HOME:-~/.codex}/archived_sessions/\`. Public format pointers: https://github.com/openai/codex/discussions/12668 and https://docs.rs/crate/txcript/latest/source/docs/formats/codex.md . These are **format hypotheses**, not proof of the user's current installed Codex schema. Inspect a bounded representative local sample **without exposing its content** before finalizing parsing.

Common event envelopes include \`session_meta\`, \`turn_context\`, \`response_item\`, \`event_msg\`; real invocations may use \`response_item.payload.type == "function_call"\` or a custom-tool call with \`name\`, JSON-encoded \`arguments\`, \`call_id\`; results may be \`function_call_output\` / \`custom_tool_call_output\` with metadata. Determine exact shapes empirically; never treat an event echo as a second invocation or assume a tool-result string equals unadorned stdout. Distinguish session identity, call ID and invocations. Observe tool families other than shell without trying to execute them.

Virtual batching may appear as \`delayed_seq\` function calls, the proxy-rewritten \`exec_command\` form with \`CODEX_ROUTING_PROXY_VIRTUAL_BATCH=1 delayed-seq --initial-delay 0 -- ...\`, or normal \`delayed-seq -- 'cmd1' 'cmd2'\`. Count **tool invocations** separately from requested **underlying shell subcommands**. A failed early batch or dry run does not prove later commands actually ran.

## Detailed required behavior

### A. Secure, read-only local CLI

Example:

\`\`\`sh
python3 scripts/analyze_codex_commands.py --codex-home "$HOME/.codex" --since 2026-10-01 --output-dir "$HOME/codex-command-report"
\`\`\`

Support \`--sessions-dir\` override, inclusive \`--since\`/\`--until\`, \`--include-archived\`, optional max-file/max-byte bounds, and deterministic output ordering. Recursively enumerate only recognized rollout JSONL paths beneath the chosen root; prohibit directory-symlink traversal and reject escapes. Never read credentials (\`auth.json\`, token stores), unrelated files, network endpoints, or invoke extracted commands. Stream files and lines with finite limits; handle actively appended partial records, invalid JSON, invalid UTF-8 and unreadable files conservatively, reporting coverage and skip reasons without leaking text. No raw command text, secrets, exact private paths, env var contents, user prompts, raw output excerpts or sensitive arguments in default Markdown/JSON/stderr. Output-directory permissions should be restrictive; redact project identity into categorical labels.

### B. Exact invocation extraction and conservative command grouping

Read actual version-supported \`response_item\` function and custom-tool requests, not merely text containing shell-looking syntax. Recognize \`exec_command\`, \`functions.shell_command\` and other observed command schemas, including array forms only when verified. Pair calls by \`(session ID, call_id)\`; dedupe the same call's alternate telemetry representations, **not** legitimate repeated invocations or retries with distinct IDs. Track observed timestamp, anonymized project category, tool name, invocation vs subcommand index, execution form (direct/native batch/proxy batch), matched completion status, and parsing-confidence level.

Normalize for aggregation, not execution, with safe \`shlex\` parsing of **simple** shell shapes. Report separately: tool invocations; executable families (\`git\`, \`rg\`, \`cargo\`, \`python -m pytest\`, etc.); stable argument shapes (\`rg <pattern> <path>\`); and optional per-run salted fingerprints. Never naively split quoted batch commands. Treat pipelines, \`&&\`, semicolons, redirects, subshells, environment assignments, shell expansion and ambiguous/nested invocations as **opaque or explicitly low-confidence**, rather than attributing incorrect executable counts. Report a parsing/unknown denominator. Preserve distinctions such as pytest module invocation versus arbitrary Python.

Rank top-N commands by call count and **number of distinct sessions**, plus shape-frequency distribution, direct versus batched use, repeated identical calls, high-frequency search/read/validation/Git families, unparsed share and long tail. Do not infer that two observed commands could have been batched merely because they were consecutive; model decisions may have been required. Candidate batching opportunities are heuristic upper bounds only.

### C. **Actual tool-output** measurement (essential)

Correlate tool calls with their **model-visible output records** using exact session and call ID, across observed function/custom/batched forms. Distinguish shell stdout, stderr, exit status and wrapper-added metadata where separately available; if not separable report a combined tool observation. Explicitly count unmatched, duplicated, truncated, partial, ambiguous, binary or unparsable outputs. Never multiply one composite batch output by its number of subcommands, and never assert that every proposed command in a failed batch executed.

Compute, per executable family **and stable command shape**:
- Observed invocation count, number of distinct sessions, matched-output count/coverage, captured bytes, lines and any legitimately measured token counts; medians, p90/p95, max and total size (including distribution across sessions).
- Model-visible total payload bytes versus extracted command stdout/stderr bytes when separately measurable; note truncation, ANSI coloring, progress noise, repeated headings, repeated warnings, redundant successes, success/failure mix, and diagnostic structure.
- Structural features only in privacy-safe aggregation, not raw messages or exact paths: lines/file counts, typical boilerplate markers, repetitive success lines, stack traces, test assertion locations, Git patch hunks, source-like content, JSON structures, timestamps.
- Unknown and high-risk output classifications, with examples expressed as sanitized patterns, **never** verbatim private content.

Do not conflate provider output-generation tokens with the model's input observations. If session traces expose reliable request boundaries and usage, correlate \`input_tokens\`, \`input_tokens_details.cached_tokens\`, \`output_tokens\` only after validation; otherwise label fresh-output token counts **estimated**, not provider-measured uncached input.

### D. Rank candidate Python \`terse\` adapters by **measurable opportunity**

The proposed eventual wrapper has exactly one output mode: **terse**. Running a command **without** the wrapper is raw. Unknown executables, unsupported option/argument shapes and unsafe transformations are **byte-for-byte passthrough** of the captured command output, preserving exit semantics. An adapter parse failure must never rerun a command (side effects). This research **does not build or deploy** that wrapper.

Produce an evidence-based priority table for candidate adapters: \`git status/log/show --stat\`, \`rg\`/\`grep\`, pytest/Cargo/Go tests, compilers/linters, package managers, common filesystem commands. Treat \`git diff\`, source reads and rich failing diagnostics as high-risk; lossless formatting or passthrough is preferable to deleting information required by an agent.

For each candidate include:
1. Measured calls, sessions and observed aggregate model-visible output bytes/tokens and matched-output coverage.
2. Captured output type(s), repetition/noise structure, failure versus success prevalence, recoverability needs, and whether \`delayed-seq\` or other existing mechanisms already suppress the output.
3. Plausible deterministic transform and parser edge cases; implementation/test complexity and an explicit safety class: \`safe to aggregate\`, \`high diagnostic risk\`, \`requires original-output recovery\`, or \`passthrough\`.
4. Measured or **confidence-labeled** offline simulated reduction in the **observed payload** if a safe transform can be reproduced in-memory during analysis; estimated avoidable observation tokens **per invocation** and **across the window**, with lower/upper bounds and assumptions. If no reliable simulation exists, provide qualitative opportunity and mark savings **unknown** rather than fabricating them.
5. A ranking emphasizing **avoided fresh/likely uncached input**, not frequency alone; e.g., a common 20-byte command may be less valuable than a moderately frequent verbose test log. Identify the smallest safe initial adapter set.
6. Risks of extra Codex model calls, repeated inspections, debugging mistakes and lost assertions that may offset token savings.

A read-only transform feasibility simulation may be added **inside the analyzer** on captured outputs using robust deterministic rules (e.g. consolidate repeated successful test names, retain exact failed test diagnostics). It must not change underlying files or build a production command wrapper. Compare simulated output to original structurally and require proven safe fallback. Do not substitute lexical bytes for actual tokenizer counts without labeling the approximation.

### E. Uncached-input and cost methodology

**Primary goal:** reduce *new* uncached model input by shortening the first model-visible observation after a tool finishes. Session history output size is a proxy for that opportunity, **not** proof of cache status. When request-level token usage is unavailable, report projected newly introduced observation size and uncertainty; never invent cache hits, weighted task-level cost savings, or absent usage counters. Where request-level usage exists, compute \`U = input - cached\`, \`W = U + 0.1*cached + 5*output\` only with validated counters and matching request boundaries. Report raw/terse estimated observations separately from complete-task weighted tokens. Require eventual controlled A/B benchmark against the current optimized proxy + \`delayed-seq\`; measure successful task completions, tool retries and additional calls, not only per-command compression percentages.

### F. Reproducible, private report outputs

Write \`command_frequency_report.md\` and \`command_frequency_report.json\` to an **explicit** output directory. Both contain report schema version, date window, source categories, file/session/record counts, parser and result-match coverage, top 20 executable families, top 30 normalized shapes, distinct-session counts, direct/batched breakdown, observed tool-output size distributions, repetition and boilerplate characterization, ranked **actual-output-grounded terse adapter opportunities**, conservative fresh-token bounds, implementation difficulty, information-loss risks, passthrough recommendations, likely batching opportunities and limitations. Order ties deterministically; never expose raw shell commands containing secrets, prompt text, literal private paths or raw tool-result content. Print only a short summary and paths. Include a *clearly illustrative* synthetic example in documentation; if local traces unavailable, provide parser and synthetic report, saying real frequencies are unmeasured.

Do not edit or replace \`REPORT.md\`: that is the existing controlled batching study, not this personal-history observational analysis. Do not publish local real reports without privacy review and approval.

## Deterministic tests and validation

Build synthetic JSONL fixtures **in tests**, never using private history in the repository. Cover:
- Single \`exec_command\`, custom tool call, \`event_msg\` duplicate echo; repeated real calls with distinct IDs; duplicate telemetry with same ID; matched/missing/ambiguous/duplicate/truncated tool outputs and correct coverage.
- Multiple Codex envelope variants verified from local shape samples, nested/escaped command JSON, malformed lines, partial trailing line, UTF-8, oversized records, active files, malformed arguments and shell metacharacters.
- Native \`delayed-seq\` quoted command list and proxy virtual marker serialization; proper distinction among tool invocations, proposed subcommands and **actually observed completed** subcommands. Stop-on-error/dry-run ambiguity.
- Simple-shell \`shlex\` normalization and opaque fallback for pipes, multiline scripts, subshells, redirects, env assignments and complex quoting; no execution.
- Symlink exclusion, custom sessions root, archived selection, inclusive date filters, file/byte caps and input never modified.
- Synthetic \`git status\`, \`git diff\`, \`rg\`, pytest/Cargo/Go success/failure, compiler diagnostics, generic unknown, binary/invalid UTF-8 tool outputs: output-size attribution, percentiles, ranking high total output over mere frequency, risk categories, simulated safe transformations and passthrough.
- Failure traceback preservation, stdout/stderr metadata variation, ANSI codes, truncated records, missing usage fields; **no false claim of measured uncached tokens**.
- Secrets in command arguments and outputs never appear in Markdown, JSON, stderr or summaries. Identical fixtures produce byte-for-byte identical reports. No network or subprocess execution from session content.

Suggested validation (commands may be batched with installed \`delayed-seq\` when safely consecutive):
\`\`\`sh
python3 -m pytest -q tests/test_analyze_codex_commands.py
python3 -m compileall -q scripts
\`\`\`
Then run a synthetic end-to-end report and inspect the outputs. With authorized local Codex history available, run a bounded real-data report, explicitly record count/output matching confidence, and privacy-audit the report before publication. Stop on parsing ambiguities that would invalidate rankings or risk leaking secrets.

## Executor handoff and final-diff checklist

1. Verify the latest intended remote \`main\`; reconcile changes in README, report, or command wrapper. Read \`PLAN.md\` first and inspect the precise starting files/symbols above, then inspect only small, redacted local history envelopes to verify schemas. Do not have to rediscover already established repo facts.
2. Implement as one bounded workstream with minimal dependencies. Treat numbered requirements as a contract, **not individual model calls**. Batch independent reads, compatible writes and validation; use \`delayed-seq\` for consecutive shell steps requiring no intermediate model decision. Stop on failures, data access uncertainty or privacy risk.
3. Return changed files, tests, deviations, actual observed counts if accessible, output coverage, top commands, ranking of terse adapters **grounded in measured outputs**, modeled fresh-input token opportunities with confidence bounds, and unresolved assumptions. Do not invent local findings if only synthetic fixtures were available.
4. Final diff: no changes to \`delayed-seq\`, \`AGENTS_APPEND.md\`, existing \`REPORT.md\`, private history or proxy. Do not commit implementation/research outputs without separate explicit authorization.

**Planning commit contains only \`PLAN.md\`.**
