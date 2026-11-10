# Delayed-seq repeated-line compression audit

**Audit date:** 2026-11-10
**Session window:** 2026-11-07 through 2026-11-09 (inclusive)
**Verdict:** Generic consecutive-line RLE is not a worthwhile broad optimization on this sample. A token-count-gated implementation aimed at repetitive test output could be worthwhile if its implementation cost is negligible.

## Results

| Measure | Result |
| --- | ---: |
| Rollout files examined | 17 |
| Files with delayed-seq command output | 9 |
| Delayed-seq batches / command output segments | 1,022 / 3,109 |
| Command-output bytes / lines | 13,182,168 / 205,099 |
| Original output tokens | 3,439,851 |
| Consecutive identical-line runs | 802 |
| Redundant line occurrences in those runs | 1,048 |
| Command outputs containing a repeated run | 165 |

Run-size frequency (run size → number of runs): **2 → 760; 3 → 24; 13 → 14; 16 → 1; 20 → 3.**

### Token-counted RLE scenario

The candidate keeps the first line of a run and appends an explicit `⟦×N⟧` count, escaping literal strings that use the reserved suffix. Each command output is encoded and decoded losslessly in this representation, then both forms are counted with the same `o200k_base` tokenizer. The encoded form is selected only if its token count is lower; metadata and escaping are included.

| Scope | Output tokens | RLE savings after per-output gate | Savings |
| --- | ---: | ---: | ---: |
| All command outputs | 3,439,851 | 12,704 | 0.369% |
| Median command output | — | 0 | — |
| P90 command output (nearest-rank) | — | 0 | — |
| Maximum command output | — | 2,103 | — |
| Median session | — | 0 | — |
| P90 session (nearest-rank, 9 sessions) | — | 12,455 | — |
| Maximum session | — | 12,455 | — |

Without the per-output gate, candidate encodings expand some small outputs by 5,643 tokens; net corpus savings fall to 7,061 tokens. This is why token-count validation is essential.

## Output source

| Command class | Output lines | Output tokens | Repeated runs | Gated RLE savings |
| --- | ---: | ---: | ---: | ---: |
| Tests | 22,604 | 392,824 | 69 | 12,101 |
| Builds | 4,190 | 60,100 | 188 | 0 |
| Searches | 43,334 | 1,299,565 | 29 | 34 |
| Other | 134,971 | 1,687,362 | 516 | 569 |

Most run events were in miscellaneous commands and build output, but their repeated lines were too short to offset count metadata. Test output produced **about 95%** of gated token savings. Those gains were concentrated in one session; the median command and median session saved nothing.

## Session-token context

Eight of the nine sessions with measured command output had a cumulative thread-usage record. Their latest recorded thread totals sum to **1,108,280,459 tokens**. The one-delivery RLE saving equals **0.00115%** of that total. This is a conservative comparison: a shortened result may also reduce later prompts while it remains in context, but the local records do not support precise attribution of that repeated-context effect.

## Method and limitations

- Read the local Codex rollout JSONL files dated 2026-11-07 to 2026-11-09. Extracted delayed-seq invocations, paired results by tool call ID, and retained `command i/n` boundaries.
- For long-running calls, attached each non-empty `write_stdin` result to its process by session ID and counted each returned chunk once. The 514 included poll chunks contained no exact duplicate chunks.
- Measured UTF-8 bytes and lines from captured command output only, excluding shell-tool framing and delayed-seq status/progress lines. Token counts are from `o200k_base`, a tokenizer-based estimate; the exact tokenizer for the routed model was not available locally.
- **143 result streams contained an explicit truncation/omission marker.** Only text actually present in the local rollout records was measured; omitted output was not reconstructed.
- The RLE format is a CodexZero-style lossless repeated-line candidate, not a reproduction of CodexZero's implementation; round-trip checks passed for all measured command segments. No session data, source code, or configuration was modified.

## Recommendation

Do not prioritize generic RLE for every delayed-seq result. If a safe implementation is already cheap, retain the exact-tokenizer monotonic gate and consider targeting long, repeated test-output lines; benchmark that separately before making it a default. Search and build outputs in this sample offer negligible or no net RLE benefit after metadata.
