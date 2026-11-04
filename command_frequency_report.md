# Codex Command Frequency Report

This is a privacy-safe observational summary. Raw commands, tool outputs, prompts, exact paths, and session identifiers are not included.

## Scope and coverage

- Date window: `2026-11-01` through `unbounded` (inclusive)
- Files processed: 12 of 13 discovered
- Sessions: 10; records: 38,700
- Shell tool invocations: 3,319; underlying subcommands: 3,464
- Result matching: 3107/3319 shell invocations (93.6%)
- Opaque command share: 63.7%

Skipped or incomplete records: 3 invalid JSON, 0 invalid UTF-8, 0 oversized, 1 partial trailing, 0 symlink, 0 unreadable.

## Top executable families

| Family | Calls | Sessions | Direct | Batched | Matched | Output bytes | p95 bytes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `<opaque>` | 2,206 | 8 | 2,194 | 12 | 2,061 | 6,341,324 | 16,167 |
| `git` | 229 | 5 | 175 | 54 | 171 | 213,650 | 6,536 |
| `sed` | 229 | 6 | 229 | 0 | 216 | 1,818,999 | 23,715 |
| `rg` | 118 | 6 | 118 | 0 | 93 | 379,950 | 19,090 |
| `cargo test` | 108 | 4 | 47 | 61 | 47 | 120,335 | 7,201 |
| `cat` | 104 | 7 | 104 | 0 | 94 | 401,599 | 9,719 |
| `cargo fmt` | 56 | 4 | 8 | 48 | 8 | 14,121 | 7,006 |
| `codex` | 52 | 6 | 51 | 1 | 41 | 159,453 | 12,844 |
| `python` | 39 | 1 | 39 | 0 | 39 | 200,504 | 20,746 |
| `systemctl` | 37 | 3 | 17 | 20 | 11 | 6,731 | 2,934 |
| `jq` | 30 | 3 | 30 | 0 | 27 | 27,595 | 3,608 |
| `python3` | 22 | 5 | 22 | 0 | 20 | 16,336 | 1,513 |
| `wc` | 22 | 2 | 22 | 0 | 22 | 3,701 | 311 |
| `cargo clippy` | 20 | 3 | 7 | 13 | 7 | 4,045 | 1,318 |
| `cargo build` | 12 | 4 | 4 | 8 | 4 | 952 | 251 |
| `go test` | 11 | 1 | 11 | 0 | 11 | 5,403 | 1,631 |
| `python -m py_compile` | 11 | 1 | 11 | 0 | 11 | 1,122 | 102 |
| `python -m unittest` | 11 | 1 | 11 | 0 | 11 | 17,765 | 1,965 |
| `find` | 10 | 3 | 10 | 0 | 10 | 1,103 | 173 |
| `tail` | 9 | 3 | 9 | 0 | 9 | 104,814 | 40,213 |

## Top normalized shapes

| Shape | Calls | Sessions | Matched | Output bytes |
| --- | --- | --- | --- | --- |
| `<opaque shell form>` | 2,206 | 8 | 2,061 | 6,341,324 |
| `sed -n <arg> <arg>` | 224 | 6 | 211 | 1,815,350 |
| `cat <arg>` | 104 | 7 | 94 | 401,599 |
| `rg -n <pattern> <paths>` | 57 | 5 | 44 | 148,900 |
| `cargo fmt --all` | 37 | 2 | 3 | 306 |
| `git diff --check` | 29 | 4 | 17 | 1,932 |
| `git push` | 28 | 3 | 28 | 23,248 |
| `cargo test --lib` | 23 | 2 | 13 | 43,584 |
| `git status --short --branch` | 23 | 3 | 21 | 4,521 |
| `systemctl --user <arg> <arg>` | 22 | 3 | 4 | 1,048 |
| `cargo test --test --nocapture` | 21 | 1 | 11 | 14,001 |
| `python --browser <arg>` | 19 | 1 | 19 | 174,208 |
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
| `cargo fmt --all --check` | 12 | 1 | 1 | 7,006 |
| `git status --short` | 12 | 4 | 6 | 2,196 |
| `cargo build --release` | 11 | 4 | 3 | 701 |
| `jq -r <arg> <arg>` | 11 | 2 | 10 | 16,969 |
| `codex --help <arg>` | 10 | 4 | 7 | 14,718 |

## Batching observations

- Batch tool invocations: 87
- Requested subcommands: 3,464
- Consecutive direct-call pairs (heuristic upper bound only): 3,223

Consecutive calls may still require a model decision between them. Batch output is not multiplied across the commands it contains.

## Terse adapter priorities

| Adapter | Safety | Calls | Matched | Observed bytes | Simulated saved bytes | Likely token range |
| --- | --- | --- | --- | --- | --- | --- |
| `rust_test_success` | safe_to_aggregate | 108 | 47 | 120,335 | 67,979 | 11,330–22,660 |
| `compiler_linter` | safe_to_aggregate | 40 | 16 | 12,407 | 2,495 | 416–832 |
| `rg_grep` | safe_to_aggregate | 118 | 93 | 379,950 | 0 | 0–0 |
| `pytest_success` | safe_to_aggregate | 11 | 11 | 17,765 | 0 | 0–0 |
| `js_test_success` | safe_to_aggregate | 4 | 4 | 8,048 | 0 | 0–0 |
| `go_test_success` | safe_to_aggregate | 11 | 11 | 5,403 | 0 | 0–0 |
| `filesystem_read` | passthrough | 376 | 353 | 2,347,350 | 0 | 0–0 |
| `git_diff` | requires_original_output_recovery | 53 | 28 | 103,437 | 0 | 0–0 |
| `git_history` | high_diagnostic_risk | 25 | 25 | 33,604 | 0 | 0–0 |
| `git_status` | high_diagnostic_risk | 43 | 35 | 7,986 | 0 | 0–0 |
| `package_manager` | high_diagnostic_risk | 7 | 7 | 1,241 | 0 | 0–0 |

Smallest safe initial set with measured reductions: `rust_test_success`, `compiler_linter`

`git diff`, source reads, package-manager diagnostics, and rich failures remain passthrough or high-risk. Terse output must preserve exit semantics and fall back byte-for-byte without rerunning a command.

## Measurement limits

- Tool-output bytes are the observed model-visible payload, not proof of cache status.
- Token ranges are explicitly heuristic and are not provider-measured uncached input.
- Composite and unmatched tool outputs are counted but not attributed to subcommands.
- The analyzer is read-only and never executes extracted commands.
