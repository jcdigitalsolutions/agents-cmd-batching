# PLAN.md — Investigate and reduce opaque Codex shell-command attribution

## Status, objective and baseline

**Planning artifact only. No implementation or report re-publication is authorized by this plan.** Repository: \`jcdigitalsolutions/agents-cmd-batching\`, target branch \`main\`, inspected remote HEAD **\`a8ebec1d97fbd89dab352da56fb09fb11cf9f23f\`** (\`feat(analysis): add Codex command usage report\`). Verify latest remote \`main\` before implementing; reconcile any relevant changes and show a revision if the parser/report architecture materially changes.

**Problem:** The published bounded observation in \`command_frequency_report.md\` analyzed 12 files / 10 sessions / 3,319 shell invocations (3,464 requested underlying commands), matching 93.6% of outputs, but classified **2,206 commands (63.7% of requested subcommands)** as \`<opaque>\`. These opaque commands account for **6,341,324 captured model-visible bytes**, limiting the evidential value of ranked prospective \`terse\` adapters. Source inspection confirms the analyzer deliberately treats shell operators, newline scripts, variable expansions and assignments as opaque; **the report does not yet establish what fraction belongs to each cause**. Do not guess the cause distribution or obtainable savings.

**Objective:** Investigate opaque cases using a read-only, privacy-safe diagnostic taxonomy; add a conservative shell-command attribution layer that recognizes high-confidence executable families within selected compound commands **without executing, modifying or evaluating commands**, and rerun a comparable bounded Codex history report. Improve adapter-priority evidence by recovering command/output attribution where defensible. Keep uncertain forms opaque; never infer that every syntactically present command executed. Preserve existing summary/report schema consumers or provide a documented additive/versioned migration.

**Single integrated workstream.** Classifier, attribution model, output ownership, tests and report all depend on the same parser semantics. No \`PLAN_*.md\` needed.

## Verified repository facts — exact implementation starting points

At pinned HEAD:

- \`scripts/analyze_codex_commands.py\` (~2,258 lines) is a Python standard-library analyzer. Inspect exact symbols first rather than rereading the whole script:
  - \`SHELL_OPERATORS\`, \`ASSIGNMENT_RE\`, \`SHELL_TOOL_NAMES\`, \`NATIVE_BATCH_TOOL_NAMES\` near lines 30–49.
  - \`CommandView\`, \`ShellInvocation\`, \`ScanState\` near lines 114–184; \`OpaqueShell\`, \`JSLiteralParser\` near 310+.
  - \`_mask_js_strings_and_comments\`, \`_extract_embedded_tool_calls\` (~528–593) for custom \`exec\` JavaScript envelopes, separate from shell parsing.
  - \`_tokenize_simple_shell\` (~594–610): rejects newline/CR/NUL, tokens in \`SHELL_OPERATORS\`, \`$\`, backticks and lexer errors.
  - \`_safe_family\`, \`_safe_option\`, \`_family_shape\` (~611–688): recognized family and privacy-safe normalized shape. \`_parse_simple_command\` (~689–702): converts unsupported forms into a single \`<opaque>\`/\`<opaque shell form>\` class; leading \`NAME=value\` assignments are rejected.
  - \`_parse_delayed_tokens\` (~703–773), \`InvocationPlan\`, \`_plan_invocation\` (~774–820): distinguish \`delayed-seq\` shell wrapper, marked proxy batches and native \`delayed_seq\`; complex shell forms currently block batch recognition.
  - \`_process_call_payload\`, \`_process_output_payload\` (~871–1175), \`scan_rollouts\` (~1342), \`_attach_outputs\` (~1500), \`_count_execution\` (~1557): correlated output, exact call IDs, execution status.
  - \`_candidate_id\` (~1459), \`_add_to_bucket\` (~1528), \`build_report\` (~1607), \`render_markdown\` (~1995), CLI parser (~2187): aggregation, adapter ranking and reports. \`_add_to_bucket\` attributes output only to **direct single-subcommand** calls; composite output is not multiplied across inferred subcommands.
- \`python_tests/test_analyze_codex_commands.py\` (~586 lines) uses \`unittest.TestCase\` with synthetic JSONL. Inspect especially \`test_batch_forms_count_invocations_without_multiplying_output\` (~212), \`test_opaque_shell_forms_are_not_misattributed\` (~280), \`test_terse_ranking_uses_output_size_and_marks_high_risk_diff\` (~512), privacy/determinism tests (~539+). Continue using the existing unittest style; do not migrate frameworks incidentally.
- \`docs/codex-command-frequency.md\` (~160 lines) documents intentional opacity for pipelines/\`&&\`/\`;\`/redirects/subshells/assignments/substitution/newlines and cautions shell output bytes aren't measured uncached tokens. \`README.md\` links to analyzer. \`REPORT.md\` is the distinct prior 288-run batching benchmark and is read-only for this task.
- \`command_frequency_report.{md,json}\` are **currently committed aggregate reports** based on a bounded local dataset. Published: 2,206 opaque commands, 6.34 MB opaque output, 229 each for \`git\`/\`sed\`, 118 \`rg\`, 108 \`cargo test\`, 104 \`cat\`. Replacing published outputs requires separate review/approval; regenerating locally is not permission to commit raw or derived session data.
- The CLI reads local Codex rollout JSONL offline, bounds file/line/total bytes, skips symlinks and never executes extracted commands. Exact session/call-ID matching and duplicate handling must remain intact. Output may contain secrets: **never print raw input commands or captured output in diagnostics or reports**.

## Investigation phase — before expanding the parser

1. Establish a **frozen baseline** with the published report and, where available, a fresh run using the same 12 source files, dates and limits. Save private output outside Git; record inclusion criteria, analyzer version, file/session counts, matching and opaque denominator. Don't claim exact reproduction if old files grew or rotated; separate cohort effects from parser effects.
2. Implement a **reason-only, non-content classifier** for every opaque \`CommandView\`. Emit one mutually exclusive primary reason plus optional secondary flags, with explicit precedence and totals reconciling to opaque count. Initial groups: \`shell_pipeline\`, \`boolean_chain\`, \`command_sequence\`, \`redirect_or_heredoc\`, \`subshell_or_group\`, \`environment_assignment\`, \`variable_or_command_expansion\`, \`multiline_script\`, \`unsupported_quote_or_lexer\`, \`shell_function_or_control_flow\`, \`unknown_or_other\`, plus \`null_byte_or_invalid\` when observed. Reason-classification errors return unknown, never crash or leak private text.
3. Report by reason: requested-command count, distinct sessions, matched-output invocation count, **exclusively attributable** output bytes and p50/p90/p95, batching forms, and heuristic token ranges. Include unmatched/composite counts, avoiding any double attribution of one tool result. Distinguish **one actual shell invocation** from **N syntactic command segments**.
4. Add a **local privacy-safe diagnostic review workflow**: aggregated reason/feature cross-tabs, optional salted ephemeral fingerprints or sanitized structural skeletons (operator tokens, allowlisted executable families, argument placeholders) in permissions-restricted local reports. Never include raw histories, command strings, arguments, output excerpts, private paths, env values or prompts in the repo, stderr or default reports. Manual examination of selected records may be done by the authorized local user; the tool itself must not print secrets.
5. Pick parser expansion **from measured causes**. Document cases impossible to classify safely (nested quotes, heredocs, generated shell, substitution). If diagnostics remain inconclusive, stop with findings rather than implementing speculative parsing.

## Attribution design — bounded, conservative, no shell execution

**Proposed internal types:** \`OpaqueReason\` enum/constants; \`ShellSegment\` containing family, shape, control-flow position and confidence; \`CommandAnalysis\` containing private original command, segments, primary reason, feature flags and \`attribution_confidence\` (\`high\`, \`partial\`, \`opaque\`). Extend \`CommandView\` or refactor internally without silently changing public report fields. No shell interpreter, command execution, \`eval\`, subprocess probing, filesystem expansion or LLM classification.

1. Parse **lexical boundaries** using Python stdlib where safe; preserve quotes/escapes and distinguish true operators from literals. Validate \`shlex\` punctuation on synthetic shell cases. If insufficient for POSIX shell grammar, implement only a bounded diagnostic tokenizer with strict unknown fallback, not a claimed complete shell parser. Dialect may be \`sh\`, \`bash\`, or \`zsh\`; don't assume equivalence.
2. **High-confidence recovery:** one simple command with benign leading environment assignments (record assignment presence, not value), known wrappers \`env\`, \`command\`, \`timeout\` when arguments are validated, simple \`cmd1 && cmd2\`, \`cmd1 ; cmd2\`, \`cmd1 | cmd2\` with unambiguous tokens and no nested control flow. Keep distinct segment lists; **do not claim all segments executed**. Only the first segment can be assumed attempted when the shell invocation starts, subject to shell pre-execution failure.
3. **Partial classification:** identify candidate executable families within a pipeline, condition or redirection but store **syntax-only frequencies** separately from executed-command counts. Pipeline output and exit status describe the whole expression; pipefail and shell-specific semantics defeat simple per-segment inference.
4. **Remain opaque:** nested substitution, variable/parameter expansion affecting executable identity, shell aliases/functions, loops/conditionals, \`eval\`, heredoc scripts, here-strings, process substitution, arbitrary multiline scripts and nested subshells unless independently proven safe. Quoted \`|\` or \`&&\` are literals.
5. **Output accounting:** attach combined output to originating tool invocation only; attribute exclusively to a family only if demonstrably one executable produced it. Composite/partial results remain \`composite_unattributed\` with related syntactic families, never duplicated into candidate totals. Preserve existing delayed-seq completion markers without extrapolating compound command segments.
6. Preserve exact original grouping, call IDs, deduplication, failure accounting, native/proxy/shell batching, and bounded limits. Invalid syntax or parser failures must remain counted opaque, not dropped.

## Revised reports and measurable success criteria

- Generate **local** \`opaque_command_diagnostics.md\` and \`opaque_command_diagnostics.json\` within the selected output directory, plus additive/versioned opaque-attribution sections in \`command_frequency_report.{md,json}\`. Keep top-family metrics comparable and explicitly distinguish \`high_confidence_single\`, \`partial_syntactic\`, \`unresolved_opaque\`. Bump \`SCHEMA_VERSION\` and document/test migration if semantics change; never silently redefine \`calls\`.
- Show before/after opaque fraction by requested commands and by shell invocations, high-confidence family coverage, partial syntax coverage and still-unattributable output bytes, each with denominator. Show top reasons, confidence levels, and terse-adapter opportunities supported by *exclusive* output ownership.
- **No fixed opaque-reduction quota.** Do not incentivize guessing merely to drive 63.7% lower. Success means useful explanatory coverage, validated syntax classifications, unchanged invocation/result totals, and more defensible adapter decisions.
- Compare only matched cohorts; provide reconciliation of source records, invocations, requested subcommands, matching, total tool-output bytes, success/failure/unknown and composite output. Explicitly separate source reads such as \`sed\`/\`cat\` (often passthrough) from repetitive tests and diagnostics.
- Token opportunities remain clearly byte-derived estimates, not provider-measured uncached tokens; compute \`U + 0.1C + 5O\` only with actual validated usage/request data.
- Do not modify \`REPORT.md\`, core \`delayed-seq\`, \`AGENTS_APPEND.md\`, Codex proxy, or build a \`terse\` executable in this task.

## Deterministic regression tests

Extend \`python_tests/test_analyze_codex_commands.py\` with synthetic JSONL and focused parser tests covering:

- Operators inside/outside single/double quotes, escaping, empty strings, comments, whitespace, CR/LF, invalid UTF-8, malformed lexer forms. Quoted \`|\`, \`&&\`, \`;\`, \`>\`, \`$\` are not actual operators.
- \`git status && cargo test\`, \`rg x src | head -20\`, \`cd src && pytest\`, \`VAR=secret cargo test\`, \`env VAR=secret rg x\`, \`2>&1\`, redirects, arithmetic/parameter/command substitution, \`$(...)\`, backticks, subshells, braces, \`for\`/\`if\`, heredocs, \`eval\`, multiline scripts and POSIX/Bash edge cases. Ambiguous forms remain partial/opaque.
- Failing first command with skipped later commands, successful chains, pipeline composite outputs/status, and no duplicate attribution; maintain native/proxy \`delayed_seq\` stop-on-error and requested-versus-executed boundaries.
- Existing call-ID matching, duplicate handling, incomplete/composite outputs, stable unchanged aggregate totals, no duplicate syntax-count attribution.
- Privacy with secret env assignments, tokens, passwords, query strings, paths, heredocs and arbitrary outputs: zero leakage into Markdown, JSON, stderr, reports or test failures. Keep report permissions restrictive.
- Deterministic sort order, versioning, estimates, date/symlink/size limits, repeated byte-identical reports, empty/fully opaque datasets, unknown-on-parser-error handling.

Validation commands (batch where safe using installed \`delayed-seq\`): \`python3 -m unittest discover -s python_tests -v\`; \`python3 -m compileall -q scripts\`; synthetic end-to-end JSON/report reconciliation. Run a bounded private comparison on frozen local histories **only if available and authorized**; never invent real-data results. No external network or sleeps. Bound tokenizer nesting/segment length and total processing to avoid malformed-record denial of service.

## Execution handoff and final diff

1. Verify latest \`main\`, read \`PLAN.md\` first, inspect exact starting symbols and tests above. Investigate measured opaque *reasons* before deciding parser breadth. Stop for uncertain dialect or privacy hazards.
2. One bounded executor owns \`scripts/analyze_codex_commands.py\`, \`python_tests/test_analyze_codex_commands.py\`, \`docs/codex-command-frequency.md\`, minimal \`README.md\` clarification if needed. Introduce a helper module only if complexity warrants it. No incidental test-framework migration.
3. Codex must decide how to batch execution efficiently: combine independent reads, compatible edits and validations; numbered steps are requirements, not individual tool calls. Use installed \`delayed-seq\` for consecutive commands needing no intermediate decision. Do not sacrifice correctness or required checks for fewer turns. Stop on failed validation or unsafe assumptions.
4. Report changed files, commit SHA if implementation commits are independently authorized, tests, exact cohorts, before/after totals, opaque reasons, confidence and privacy status, report locations, limitations and deviations. Do not publish private derived data without explicit consent.
5. Final diff: identical command/output totals on same cohort, no invented per-segment execution, privacy-safe, simple-command behavior unchanged, opaque fallback when uncertain, no modifications to \`delayed-seq\`, \`AGENTS_APPEND.md\`, \`REPORT.md\`, histories or proxy.

**Planning-file policy:** Commit only \`PLAN*.md\` with explicit approval and a rechecked target branch. No implementation code is authorized by the planning commit.
