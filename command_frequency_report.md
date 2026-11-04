# Codex Command Frequency Report

This is a privacy-safe observational summary. Raw commands, tool outputs, prompts, exact paths, and session identifiers are not included.

## Scope and coverage

- Date window: `2026-11-01` through `unbounded` (inclusive)
- Files processed: 12 of 13 discovered
- Sessions: 10; records: 39,321
- Shell tool invocations: 3,346; underlying subcommands: 3,496
- Result matching: 3134/3346 shell invocations (93.7%)
- Opaque command share: 60.6%
- High-confidence single-command attribution: 39.4%
- Partial syntactic-only attribution: 40.4%

Skipped or incomplete records: 3 invalid JSON, 0 invalid UTF-8, 0 oversized, 1 partial trailing, 0 symlink, 0 unreadable.

## Top executable families

| Family | Calls | Sessions | Direct | Batched | Matched | Output bytes | p95 bytes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `<opaque>` | 2,117 | 8 | 2,106 | 11 | 0 | 0 | 0 |
| `git` | 233 | 5 | 175 | 58 | 171 | 213,650 | 6,536 |
| `sed` | 229 | 6 | 228 | 1 | 215 | 1,820,112 | 23,715 |
| `rg` | 121 | 6 | 121 | 0 | 96 | 382,226 | 19,090 |
| `cargo test` | 116 | 4 | 53 | 63 | 53 | 138,942 | 9,351 |
| `cat` | 105 | 7 | 105 | 0 | 95 | 407,083 | 9,719 |
| `python -m unittest` | 59 | 2 | 59 | 0 | 59 | 96,205 | 7,401 |
| `cargo fmt` | 58 | 4 | 8 | 50 | 8 | 14,121 | 7,006 |
| `codex` | 53 | 6 | 52 | 1 | 42 | 168,325 | 12,844 |
| `python3` | 45 | 5 | 45 | 0 | 43 | 42,975 | 7,420 |
| `python` | 42 | 1 | 42 | 0 | 42 | 221,612 | 20,743 |
| `systemctl` | 37 | 3 | 17 | 20 | 11 | 6,731 | 2,934 |
| `jq` | 30 | 3 | 30 | 0 | 27 | 27,595 | 3,608 |
| `wc` | 22 | 2 | 22 | 0 | 22 | 3,701 | 311 |
| `cargo clippy` | 20 | 3 | 7 | 13 | 7 | 4,045 | 1,318 |
| `cargo build` | 13 | 4 | 4 | 9 | 4 | 952 | 251 |
| `go test` | 13 | 1 | 13 | 0 | 13 | 6,169 | 1,631 |
| `delayed-seq` | 12 | 1 | 12 | 0 | 12 | 13,640 | 12,410 |
| `python -m <module>` | 11 | 1 | 11 | 0 | 11 | 1,122 | 102 |
| `tail` | 9 | 3 | 9 | 0 | 9 | 104,814 | 40,213 |

## Top normalized shapes

| Shape | Calls | Sessions | Matched | Output bytes |
| --- | --- | --- | --- | --- |
| `<opaque shell form>` | 2,117 | 8 | 0 | 0 |
| `sed -n <arg> <arg>` | 226 | 6 | 212 | 1,817,502 |
| `cat <arg>` | 105 | 7 | 95 | 407,083 |
| `rg -n <pattern> <paths>` | 60 | 5 | 47 | 151,176 |
| `cargo fmt --all` | 37 | 2 | 3 | 306 |
| `python -m unittest -m -v <selector>` | 31 | 2 | 31 | 34,887 |
| `git diff --check` | 29 | 4 | 17 | 1,932 |
| `git push` | 28 | 3 | 28 | 23,248 |
| `cargo test --lib` | 26 | 2 | 16 | 57,936 |
| `git status --short --branch` | 24 | 3 | 21 | 4,521 |
| `python --browser <arg>` | 22 | 1 | 22 | 195,316 |
| `systemctl --user <arg> <arg>` | 22 | 3 | 4 | 1,048 |
| `cargo test --test --nocapture` | 21 | 1 | 11 | 14,001 |
| `cargo test --test` | 18 | 1 | 3 | 7,726 |
| `rg -n -C <pattern> <paths>` | 16 | 4 | 12 | 78,579 |
| `git commit -m` | 15 | 3 | 7 | 12,335 |
| `git commit -m -m` | 15 | 3 | 14 | 9,048 |
| `jq <arg> <arg>` | 15 | 3 | 13 | 7,882 |
| `git diff` | 14 | 3 | 9 | 100,377 |
| `python --iterations --json <arg> <arg> <arg>` | 14 | 1 | 14 | 25,491 |
| `rg -n -g <pattern> <paths>` | 14 | 3 | 14 | 67,945 |
| `cargo clippy --all-targets -D` | 13 | 2 | 1 | 113 |
| `cargo test` | 13 | 3 | 0 | 0 |
| `cargo test --all-targets` | 13 | 1 | 2 | 17,276 |
| `git add` | 13 | 2 | 3 | 306 |
| `wc -l <arg>` | 13 | 1 | 13 | 1,975 |
| `cargo build --release` | 12 | 4 | 3 | 701 |
| `cargo fmt --all --check` | 12 | 1 | 1 | 7,006 |
| `git status --short` | 12 | 4 | 6 | 2,196 |
| `jq -r <arg> <arg>` | 11 | 2 | 10 | 16,969 |

## Opaque attribution

- Legacy v1 opaque commands: 2,225
- High-confidence single commands: 1,379
- Partial syntactic-only commands: 1,414
- Still unresolved opaque commands: 703
- Still-unattributable matched output bytes: 6,666,293

A partial syntactic command identifies candidate executable families but does not prove those commands ran or produced output. Composite output remains owned by its originating invocation only.

| Reason | Commands | Sessions | Matched invocations | Exclusive bytes |
| --- | --- | --- | --- | --- |
| `shell_function_or_control_flow` | 243 | 7 | 241 | 0 |
| `variable_or_command_expansion` | 63 | 6 | 63 | 0 |
| `redirect_or_heredoc` | 414 | 7 | 400 | 0 |
| `subshell_or_group` | 20 | 4 | 20 | 0 |
| `command_sequence` | 139 | 5 | 118 | 0 |
| `boolean_chain` | 791 | 7 | 721 | 0 |
| `shell_pipeline` | 288 | 7 | 263 | 0 |
| `multiline_script` | 15 | 3 | 15 | 0 |
| `environment_assignment` | 247 | 3 | 247 | 166,832 |
| `unsupported_quote_or_lexer` | 1 | 1 | 1 | 0 |
| `unknown_or_other` | 2 | 1 | 1 | 0 |

### Syntax-only segment families

| Family | Shape | Syntactic occurrences |
| --- | --- | --- |
| `sed` | `sed -n <arg> <arg>` | 632 |
| `git` | `git status --short --branch` | 185 |
| `sed` | `sed -n <arg>` | 172 |
| `rg` | `rg -n <pattern> <paths>` | 162 |
| `true` | `true` | 140 |
| `head` | `head -<n>` | 115 |
| `git` | `git diff --check` | 109 |
| `sort` | `sort` | 107 |
| `git` | `git diff --stat` | 73 |
| `cat` | `cat <arg>` | 63 |
| `tail` | `tail -<n>` | 60 |
| `printf` | `printf <arg>` | 58 |
| `git` | `git status --short` | 52 |
| `rg` | `rg <pattern>` | 48 |
| `git` | `git log -<n> --oneline --decorate` | 44 |
| `git` | `git rev-parse` | 41 |
| `git` | `git add` | 40 |
| `git` | `git diff` | 39 |
| `nl` | `nl -ba <arg>` | 39 |
| `df` | `df -h <arg>` | 34 |
| `jq` | `jq -r <arg> <arg>` | 34 |
| `git` | `git diff --cached --check` | 32 |
| `jq` | `jq <arg>` | 31 |
| `du` | `du -sh <arg>` | 30 |
| `git` | `git commit -m` | 28 |
| `curl` | `curl -fsS <arg>` | 26 |
| `rg` | `rg -i <pattern>` | 23 |
| `git` | `git diff --cached --stat` | 22 |
| `ps` | `ps -eo <arg>` | 21 |
| `sort` | `sort -h` | 20 |

## Batching observations

- Batch tool invocations: 91
- Requested subcommands: 3,496
- Consecutive direct-call pairs (heuristic upper bound only): 3,246

Consecutive calls may still require a model decision between them. Batch output is not multiplied across the commands it contains.

## Terse adapter priorities

| Adapter | Safety | Calls | Matched | Observed bytes | Simulated saved bytes | Likely token range |
| --- | --- | --- | --- | --- | --- | --- |
| `rust_test_success` | safe_to_aggregate | 116 | 53 | 138,942 | 71,473 | 11,913–23,825 |
| `compiler_linter` | safe_to_aggregate | 41 | 16 | 12,407 | 2,495 | 416–832 |
| `rg_grep` | safe_to_aggregate | 121 | 96 | 382,226 | 0 | 0–0 |
| `pytest_success` | safe_to_aggregate | 59 | 59 | 96,205 | 0 | 0–0 |
| `js_test_success` | safe_to_aggregate | 8 | 8 | 13,139 | 0 | 0–0 |
| `go_test_success` | safe_to_aggregate | 13 | 13 | 6,169 | 0 | 0–0 |
| `filesystem_read` | passthrough | 374 | 350 | 2,353,396 | 0 | 0–0 |
| `git_diff` | requires_original_output_recovery | 53 | 28 | 103,437 | 0 | 0–0 |
| `git_history` | high_diagnostic_risk | 26 | 25 | 33,604 | 0 | 0–0 |
| `git_status` | high_diagnostic_risk | 44 | 35 | 7,986 | 0 | 0–0 |
| `package_manager` | high_diagnostic_risk | 7 | 7 | 1,241 | 0 | 0–0 |

Smallest safe initial set with measured reductions: `rust_test_success`, `compiler_linter`

`git diff`, source reads, package-manager diagnostics, and rich failures remain passthrough or high-risk. Terse output must preserve exit semantics and fall back byte-for-byte without rerunning a command.

## Measurement limits

- Tool-output bytes are the observed model-visible payload, not proof of cache status.
- Token ranges are explicitly heuristic and are not provider-measured uncached input.
- Composite and unmatched tool outputs are counted but not attributed to subcommands.
- The analyzer is read-only and never executes extracted commands.
