# Agent Command Batching

A small, language-independent command-batching setup for AI coding agents: **one executable** plus **one paragraph of agent instructions**.

The executable `delayed-seq` runs a known sequence of shell commands in order, stops on the first failure, and reports command status. The `AGENTS_APPEND.md` paragraph instructs an agent to use it only when no new model decision is needed between commands.

This public repository contains the original benchmarked wrapper and selection paragraph; the original research and local benchmark infrastructure are not included. See [REPORT.md](REPORT.md) for results and limitations.

## Requirements

- Python 3 (standard library only)
- A POSIX-compatible `sh` available in `PATH` (Linux/macOS or an appropriate Unix-like environment)
- An AI coding agent that reads `AGENTS.md` (or equivalent guidance)

The executable intentionally accepts **shell command strings**; only execute commands you trust. It is not a sandbox, security boundary, or patch-completion detector.

## Install the executable

Clone this repository and install the wrapper into a directory in your shell `PATH`:

```sh
git clone https://github.com/jcdigitalsolutions/agents-cmd-batching.git
cd agents-cmd-batching
mkdir -p "$HOME/.local/bin"
cp delayed-seq "$HOME/.local/bin/delayed-seq"
chmod 755 "$HOME/.local/bin/delayed-seq"
export PATH="$HOME/.local/bin:$PATH"
command -v delayed-seq
```

Make that `PATH` change persistent in your shell configuration if needed. Ensure the *agent's execution environment* also inherits it. Alternatively, use the absolute executable path in your guidance/commands.

The Python source is copied without runtime dependencies or a compilation step.

## Add the agent guidance

Open [AGENTS_APPEND.md](AGENTS_APPEND.md) and append **only its instruction paragraph** (the paragraph after the introductory heading) to the end of your existing project `AGENTS.md`. This avoids overwriting unrelated rules. For a global default, add the same paragraph to your agent's global instructions if that agent supports them.

The exact tested paragraph is:

> When two or more shell commands are already known and can execute consecutively without further model decisions, use `delayed-seq -- 'command 1' 'command 2'`. Sequential dependencies such as formatting before testing are valid: the wrapper executes commands in order and stops on failure. Use ordinary commands for single operations, initial exploration, or when the next command requires interpreting the previous result. Do not generate custom delay, polling, or sequencing Bash. Preserve required validation and never assume incomplete edits succeeded.

Do not assume that copying the full research repository's `AGENTS.md` is necessary; that file contains unrelated testing-toolkit instructions.

## Usage

Each argument after `--` is **one complete shell command**. Quote each command as a single argument:

```sh
delayed-seq -- 'cargo fmt --check' 'cargo test --offline'
delayed-seq -- 'gofmt -w file.go' 'go test -count=1 ./...'
delayed-seq -- 'python -m pytest -q' 'python -m compileall -q src'
delayed-seq -- 'npm run typecheck' 'npm test'
```

The wrapper waits **5 seconds by default** before running the first command. It executes commands sequentially and stops if any command returns a nonzero status. The total default deadline is 900 seconds, including the initial wait. Long-running suites can use `--timeout`:

```sh
delayed-seq --initial-delay 0 --timeout 1800 -- 'cargo test --offline' 'cargo clippy --all-targets'
```

`--initial-delay 0` overrides the default and is a choice for your environment; the benchmarked default used 5 seconds.

To inspect without executing the commands:

```sh
delayed-seq --initial-delay 0 --dry-run -- 'python -m pytest -q' 'echo done'
```

Optional source quiet checks: `--quiet-path src --quiet-window 30 --quiet-timeout 60`. This checks for an unchanged observed set of files; **it does not prove that edits completed successfully**. Start validation only after the editing operation has explicitly succeeded.

## When agents should use it

Use `delayed-seq` for two or more already-known commands when the next command needs only successful completion of the previous one. Formatting → tests → linting is a typical case. Do not use it for single commands, first-pass repository exploration, or debugging steps where the next action depends on interpreting output.

Never bypass required checks, suppress failures, or queue validation behind an unfinished patch.

## Analyze local Codex command history

`scripts/analyze_codex_commands.py` is a read-only, standard-library analyzer for local Codex rollout JSONL. It correlates structured shell calls and exact call IDs with model-visible tool output, measures normalized command families without retaining raw commands, explains opaque shell forms by reason, conservatively identifies syntax-only executable segments, ranks repeated ordered command sequences across batching modes, and ranks future `terse` adapter opportunities.

Write reports outside Git unless you have reviewed and explicitly approved publishing them:

```sh
python3 scripts/analyze_codex_commands.py \
  --codex-home "$HOME/.codex" \
  --since 2026-10-01 \
  --output-dir "$HOME/codex-command-report"
```

For an auditable census across both current and archived rollout roots, use `--full-history` without date flags:

```sh
python3 scripts/analyze_codex_commands.py \
  --codex-home "$HOME/.codex" \
  --full-history \
  --output-dir "$HOME/codex-full-history-report"
```

Full-history discovery is exhaustive only when every eligible readable rollout and record is accounted for. File/byte/line budgets remain active; caps, missing or empty history roots, unreadable inputs, symlinks, malformed records, partial trailing records, or files changed during scanning produce a partial or unmeasured verdict, an omission manifest, and exit status `3` after the reports are written. Exact duplicate content and hard links are reconciled once without treating the known duplicate as a coverage failure.

The analyzer writes schema-versioned command reports plus private `opaque_command_diagnostics.{md,json}`, `command_sequence_report.{md,json}`, `compilation_output_research.{md,json}`, and `codex_history_census_manifest.json` / `codex_history_census_summary.md` files. It never executes extracted commands, reads credentials, or uploads session data. Partial syntactic segments are not treated as evidence that every segment ran, and sequence adjacency is not treated as proof that batching is safe. `Success!\n` and terse-failure output are research-only in-memory simulations; the analyzer does not implement a runtime `terse` wrapper. Its byte-derived token ranges are estimates, not provider-measured uncached input. See [docs/codex-command-frequency.md](docs/codex-command-frequency.md) for the report schemas, attribution rules, status-certainty rules, compression gates, sequence-boundary evidence, privacy boundaries, and methodology.

The reviewed schema-v2 aggregate report is available in [command_frequency_report.md](command_frequency_report.md) and [command_frequency_report.json](command_frequency_report.json). Detailed sanitized reason and syntax diagnostics are in [opaque_command_diagnostics.md](opaque_command_diagnostics.md) and [opaque_command_diagnostics.json](opaque_command_diagnostics.json).

The reviewed bounded sequence study for 2026-10-29 through 2026-11-01 is available in [command_sequence_report.md](command_sequence_report.md) and [command_sequence_report.json](command_sequence_report.json). It covers six source files and three sessions; the bounded sample contained no explicit batch subcommands, so it does not establish a batched-versus-unbatched incidence rate.

## Research

[REPORT.md](REPORT.md) summarizes the 72-run Go/Rust and 216-run Python/TypeScript/JavaScript comparisons (288 assignments total). These are descriptive studies rather than proof of universal cost savings, speed gains, or code-quality equivalence. Raw artifacts and private environments are deliberately not published in this repository.

## Source attribution

`delayed-seq` and the selection paragraph were copied from `jcdigitalsolutions/testing-toolkit` as of its public-release preparation on 2026-11-02. The executable is unchanged from `scripts/delayed_seq.py` and the instruction comes from `WRAPPER_SELECTION_INSTRUCTION` in `python/testing_toolkit/agent_benchmark/fixtures.py`.
