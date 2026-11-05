# Codex Rollout Census Reconciliation

Privacy-safe local snapshot metadata only. The manifest contains truncated hashes instead of absolute paths or session IDs.

## Completeness

- Verdict: **partial**
- Exhaustive: no
- Full coverage failed: yes
- Files found / eligible / scanned / omitted (not disjoint): 48 / 48 / 48 / 3
- Current / archived files found: 48 / 0
- Current / archived files scanned: 48 / 0
- Distinct sessions / source-session instances: 23 / 48
- Total inventory bytes: 480,112,072; records: 163,265

Coverage failures: `per_file_byte_cap_reached`, `inputs_changed_during_scan`, `invalid_json_records`, `partial_trailing_records`

## Omissions and mutation evidence

| Reason | Files/events |
| --- | --- |
| `file_changed_during_scan` | 1 |
| `per_file_byte_cap` | 2 |

- Duplicate rollout content: 0
- Duplicate physical files: 0
- Reused session IDs across sources: 25
- Changed during scan: 1
- Invalid UTF-8 / JSON records: 0 / 20
- Oversized / partial trailing records: 0 / 2

## Scan budgets

| Budget | Value |
| --- | --- |
| `max_files` | 100,000 |
| `max_file_bytes` | 67,108,864 |
| `max_total_bytes` | 8,589,934,592 |
| `max_line_bytes` | 16,777,216 |

Duplicate physical files and exact duplicate rollout content are reconciled to the first deterministic path in the manifest and are not analyzed twice. Legitimately separate files with a reused session ID remain separate source histories.
