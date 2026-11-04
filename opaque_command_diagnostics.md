# Codex Opaque Command Diagnostics

This is a privacy-safe, reason-only diagnostic report. It contains no raw commands, arguments, output excerpts, prompts, session IDs, environment values, or exact paths.

## Scope

- Date window: `2026-11-01` through `unbounded` (inclusive)
- Shell invocations: 3,346
- Requested commands: 3,496
- Legacy v1 opaque commands: 2,225
- Recovered as high-confidence single commands: 1,379
- Partial syntactic-only commands: 1,414
- Strict unresolved opaque commands: 703
- Reason/opaque reconciliation: yes

## Confidence

| Confidence | Requested commands | Share |
| --- | --- | --- |
| `high_confidence_single` | 1,379 | 39.4% |
| `partial_syntactic` | 1,414 | 40.4% |
| `unresolved_opaque` | 703 | 20.1% |

## Primary reasons

| Reason | Commands | Sessions | Matched invocations | Exclusive bytes | Heuristic source tokens |
| --- | --- | --- | --- | --- | --- |
| `shell_function_or_control_flow` | 243 | 7 | 241 | 0 | 29,591–59,181 |
| `variable_or_command_expansion` | 63 | 6 | 63 | 0 | 5,169–10,337 |
| `redirect_or_heredoc` | 414 | 7 | 400 | 0 | 20,964–41,928 |
| `subshell_or_group` | 20 | 4 | 20 | 0 | 598–1,196 |
| `command_sequence` | 139 | 5 | 118 | 0 | 3,690–7,380 |
| `boolean_chain` | 791 | 7 | 721 | 0 | 19,593–39,186 |
| `shell_pipeline` | 288 | 7 | 263 | 0 | 6,118–12,235 |
| `multiline_script` | 15 | 3 | 15 | 0 | 1,421–2,842 |
| `environment_assignment` | 247 | 3 | 247 | 166,832 | 6,401–12,802 |
| `unsupported_quote_or_lexer` | 1 | 1 | 1 | 0 | 43–86 |
| `unknown_or_other` | 2 | 1 | 1 | 0 | 8–15 |

Reasons use deterministic precedence; secondary flags are included in the JSON report. Counts in this table reconcile to commands with diagnostics, not to claimed execution of every syntactic segment.

## Syntax-only families

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

## Output ownership

- Matched invocation output bytes: 10,468,017
- Exclusively attributable bytes: 3,801,724
- Still-unattributable bytes: 6,666,293

Composite, partial, ambiguous, unmatched, and wrapper-batch outputs remain owned by the originating invocation and are not multiplied across syntactic segments.

## Limits

- Segment detection is lexical, not a complete POSIX/Bash parser.
- The analyzer does not execute commands, evaluate expansions, or inspect files.
- Token ranges are byte-derived heuristics, not provider-measured usage.
