# Codex Command Sequence Report

This is a privacy-safe observational summary. Canonical sequence identity excludes packaging. Raw commands, arguments, outputs, prompts, paths, and session identifiers are not included.

## Scope and evidence

- Sequence schema: `1`; parent report schema: `3`
- Date window: `2026-10-29` through `2026-11-01` (inclusive)
- Source files: 6; sessions: 3
- Timeline events classified: 44,370
- Response groups observed: 6,127
- Shell invocations linked to timeline: 4,281
- Matched shell outputs: 3,791
- Invocations excluded from sequences: 3,090 (429 ambiguous ordering)
- Requested batch subcommands: 0; confirmed executed: 0; unknown: 0
- Direct edges classified: 1,185; hard boundaries: 389
- Reused session IDs across source files: 3

All sequence counts below are overlapping windows. Packaging is shown separately and is not part of the canonical identity.

## Repeated command families

### Length 2

| Sequence | Total | Sessions | Sessions E/D/M/U | Explicit | Direct | Mixed | Unknown | Same response (denom) | Confirmed occurrences | Requested-only occurrences | Subcommands req/conf/unknown | Matched invocations | Batched fraction (denom) | Success | Failed (rate/known) | Unknown status | Output bytes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `rg` → `rg` | 82 | 2 | 0/1/0/1 | 0 | 21 | 0 | 61 | 11 (52.4%/21) | 23 | 59 | 164/60/104 | 164/164 | 0.0% (21) | 18 | 11 (37.9%/29) | 53 | 765,690 |
| `sed` → `sed` | 58 | 3 | 0/1/0/2 | 0 | 27 | 0 | 31 | 5 (18.5%/27) | 32 | 26 | 116/74/42 | 116/116 | 0.0% (27) | 27 | 10 (27.0%/37) | 21 | 787,728 |
| `rg` → `sed` | 56 | 3 | 0/1/0/2 | 0 | 18 | 0 | 38 | 0 (0.0%/18) | 21 | 35 | 112/54/58 | 112/112 | 0.0% (18) | 18 | 13 (41.9%/31) | 25 | 471,108 |
| `sed` → `rg` | 41 | 3 | 0/1/0/2 | 0 | 17 | 0 | 24 | 2 (11.8%/17) | 16 | 25 | 82/43/39 | 82/82 | 0.0% (17) | 14 | 10 (41.7%/24) | 17 | 425,342 |
| `git` → `git` | 32 | 3 | 0/1/0/2 | 0 | 11 | 0 | 21 | 6 (54.5%/11) | 11 | 21 | 64/22/42 | 60/64 | 0.0% (11) | 11 | 0 (0.0%/11) | 21 | 186,711 |
| `python -m unittest` → `python -m unittest` | 31 | 2 | 0/1/0/1 | 0 | 7 | 0 | 24 | 1 (14.3%/7) | 9 | 22 | 62/30/32 | 62/62 | 0.0% (7) | 1 | 11 (91.7%/12) | 19 | 292,722 |
| `gh` → `gh` | 30 | 2 | 0/1/0/1 | 0 | 28 | 0 | 2 | 5 (17.9%/28) | 20 | 10 | 60/47/13 | 60/60 | 0.0% (28) | 10 | 10 (50.0%/20) | 10 | 100,157 |
| `forge` → `forge` | 27 | 1 | 0/0/0/1 | 0 | 0 | 0 | 27 | 0 (n/a/0) | 2 | 25 | 54/11/43 | 20/54 | n/a (0) | 0 | 6 (100.0%/6) | 21 | 106,754 |
| `git` → `cat` | 18 | 3 | 0/1/0/2 | 0 | 1 | 0 | 17 | 0 (0.0%/1) | 1 | 17 | 36/3/33 | 35/36 | 0.0% (1) | 1 | 0 (0.0%/1) | 17 | 366,526 |
| `python -m unittest` → `sed` | 14 | 2 | 0/1/0/1 | 0 | 8 | 0 | 6 | 0 (0.0%/8) | 4 | 10 | 28/16/12 | 28/28 | 0.0% (8) | 0 | 8 (100.0%/8) | 6 | 140,526 |
| `curl` → `gh` | 12 | 1 | 0/1/0/0 | 0 | 12 | 0 | 0 | 11 (91.7%/12) | 12 | 0 | 24/24/0 | 24/24 | 0.0% (12) | 12 | 0 (0.0%/12) | 0 | 17,888 |
| `cargo test` → `cargo test` | 11 | 3 | 0/1/0/2 | 0 | 6 | 0 | 5 | 0 (0.0%/6) | 8 | 3 | 22/19/3 | 22/22 | 0.0% (6) | 5 | 4 (44.4%/9) | 2 | 98,761 |
| `python -m unittest` → `rg` | 11 | 2 | 0/1/0/1 | 0 | 1 | 0 | 10 | 0 (0.0%/1) | 4 | 7 | 22/11/11 | 22/22 | 0.0% (1) | 0 | 7 (100.0%/7) | 4 | 104,370 |
| `python -m unittest` → `git` | 10 | 2 | 0/1/0/1 | 0 | 6 | 0 | 4 | 3 (50.0%/6) | 6 | 4 | 20/14/6 | 20/20 | 0.0% (6) | 5 | 2 (28.6%/7) | 3 | 57,469 |
| `git` → `rg` | 9 | 2 | 0/1/0/1 | 0 | 7 | 0 | 2 | 2 (28.6%/7) | 7 | 2 | 18/14/4 | 18/18 | 0.0% (7) | 6 | 1 (14.3%/7) | 2 | 38,405 |
| `sed` → `python -m unittest` | 9 | 2 | 0/1/0/1 | 0 | 7 | 0 | 2 | 0 (0.0%/7) | 6 | 3 | 18/14/4 | 18/18 | 0.0% (7) | 3 | 4 (57.1%/7) | 2 | 67,946 |
| `rg` → `python -m unittest` | 8 | 2 | 0/1/0/1 | 0 | 4 | 0 | 4 | 0 (0.0%/4) | 4 | 4 | 16/9/7 | 16/16 | 0.0% (4) | 2 | 2 (50.0%/4) | 4 | 50,521 |
| `cat` → `git` | 7 | 3 | 0/1/0/2 | 0 | 2 | 0 | 5 | 2 (100.0%/2) | 2 | 5 | 14/4/10 | 13/14 | 0.0% (2) | 2 | 0 (0.0%/2) | 5 | 18,791 |
| `gh` → `curl` | 7 | 1 | 0/1/0/0 | 0 | 7 | 0 | 0 | 2 (28.6%/7) | 6 | 1 | 14/13/1 | 14/14 | 0.0% (7) | 5 | 1 (16.7%/6) | 1 | 7,930 |
| `node` → `node` | 7 | 1 | 0/1/0/0 | 0 | 7 | 0 | 0 | 4 (57.1%/7) | 7 | 0 | 14/14/0 | 14/14 | 0.0% (7) | 5 | 2 (28.6%/7) | 0 | 17,964 |

### Length 3

| Sequence | Total | Sessions | Sessions E/D/M/U | Explicit | Direct | Mixed | Unknown | Same response (denom) | Confirmed occurrences | Requested-only occurrences | Subcommands req/conf/unknown | Matched invocations | Batched fraction (denom) | Success | Failed (rate/known) | Unknown status | Output bytes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `rg` → `rg` → `rg` | 27 | 2 | 0/1/0/1 | 0 | 7 | 0 | 20 | 3 (42.9%/7) | 8 | 19 | 81/29/52 | 81/81 | 0.0% (7) | 7 | 3 (30.0%/10) | 17 | 409,456 |
| `rg` → `rg` → `sed` | 21 | 2 | 0/1/0/1 | 0 | 8 | 0 | 13 | 0 (0.0%/8) | 8 | 13 | 63/32/31 | 63/63 | 0.0% (8) | 6 | 6 (50.0%/12) | 9 | 373,289 |
| `sed` → `sed` → `sed` | 20 | 3 | 0/1/0/2 | 0 | 13 | 0 | 7 | 1 (7.7%/13) | 13 | 7 | 60/44/16 | 60/60 | 0.0% (13) | 13 | 2 (13.3%/15) | 5 | 416,104 |
| `gh` → `gh` → `gh` | 17 | 2 | 0/1/0/1 | 0 | 16 | 0 | 1 | 0 (0.0%/16) | 10 | 7 | 51/41/10 | 51/51 | 0.0% (16) | 2 | 8 (80.0%/10) | 7 | 81,257 |
| `sed` → `sed` → `rg` | 17 | 3 | 0/1/0/2 | 0 | 7 | 0 | 10 | 1 (14.3%/7) | 6 | 11 | 51/31/20 | 51/51 | 0.0% (7) | 6 | 6 (50.0%/12) | 5 | 318,970 |
| `rg` → `sed` → `rg` | 14 | 2 | 0/1/0/1 | 0 | 7 | 0 | 7 | 0 (0.0%/7) | 7 | 7 | 42/23/19 | 42/42 | 0.0% (7) | 4 | 5 (55.6%/9) | 5 | 188,615 |
| `sed` → `rg` → `sed` | 13 | 3 | 0/1/0/2 | 0 | 6 | 0 | 7 | 0 (0.0%/6) | 6 | 7 | 39/22/17 | 39/39 | 0.0% (6) | 6 | 3 (33.3%/9) | 4 | 152,718 |
| `rg` → `sed` → `sed` | 12 | 2 | 0/1/0/1 | 0 | 3 | 0 | 9 | 0 (0.0%/3) | 3 | 9 | 36/17/19 | 36/36 | 0.0% (3) | 3 | 4 (57.1%/7) | 5 | 210,318 |
| `forge` → `forge` → `forge` | 10 | 1 | 0/0/0/1 | 0 | 0 | 0 | 10 | 0 (n/a/0) | 1 | 9 | 30/13/17 | 21/30 | n/a (0) | 0 | 6 (100.0%/6) | 4 | 107,409 |
| `sed` → `rg` → `rg` | 10 | 2 | 0/1/0/1 | 0 | 4 | 0 | 6 | 0 (0.0%/4) | 4 | 6 | 30/15/15 | 30/30 | 0.0% (4) | 3 | 3 (50.0%/6) | 4 | 147,981 |
| `git` → `git` → `cat` | 9 | 3 | 0/1/0/2 | 0 | 1 | 0 | 8 | 0 (0.0%/1) | 1 | 8 | 27/3/24 | 25/27 | 0.0% (1) | 1 | 0 (0.0%/1) | 8 | 216,563 |
| `git` → `git` → `git` | 9 | 2 | 0/1/0/1 | 0 | 5 | 0 | 4 | 2 (40.0%/5) | 5 | 4 | 27/15/12 | 27/27 | 0.0% (5) | 5 | 0 (0.0%/5) | 4 | 205,202 |
| `curl` → `gh` → `gh` | 6 | 1 | 0/1/0/0 | 0 | 6 | 0 | 0 | 3 (50.0%/6) | 6 | 0 | 18/18/0 | 18/18 | 0.0% (6) | 5 | 1 (16.7%/6) | 0 | 12,472 |
| `python -m unittest` → `python -m unittest` → `rg` | 6 | 2 | 0/1/0/1 | 0 | 1 | 0 | 5 | 0 (0.0%/1) | 2 | 4 | 18/11/7 | 18/18 | 0.0% (1) | 0 | 5 (100.0%/5) | 1 | 92,998 |
| `node` → `node` → `node` | 5 | 1 | 0/1/0/0 | 0 | 5 | 0 | 0 | 2 (40.0%/5) | 5 | 0 | 15/15/0 | 15/15 | 0.0% (5) | 3 | 2 (40.0%/5) | 0 | 18,271 |

### Length 4

| Sequence | Total | Sessions | Sessions E/D/M/U | Explicit | Direct | Mixed | Unknown | Same response (denom) | Confirmed occurrences | Requested-only occurrences | Subcommands req/conf/unknown | Matched invocations | Batched fraction (denom) | Success | Failed (rate/known) | Unknown status | Output bytes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `rg` → `rg` → `rg` → `rg` | 11 | 2 | 0/1/0/1 | 0 | 4 | 0 | 7 | 1 (25.0%/4) | 4 | 7 | 44/16/28 | 44/44 | 0.0% (4) | 4 | 0 (0.0%/4) | 7 | 133,544 |
| `gh` → `gh` → `gh` → `gh` | 10 | 1 | 0/1/0/0 | 0 | 10 | 0 | 0 | 0 (0.0%/10) | 6 | 4 | 40/35/5 | 40/40 | 0.0% (10) | 0 | 7 (100.0%/7) | 3 | 60,250 |
| `rg` → `rg` → `sed` → `rg` | 8 | 2 | 0/1/0/1 | 0 | 4 | 0 | 4 | 0 (0.0%/4) | 4 | 4 | 32/18/14 | 32/32 | 0.0% (4) | 2 | 3 (60.0%/5) | 3 | 99,901 |
| `sed` → `sed` → `sed` → `rg` | 8 | 3 | 0/1/0/2 | 0 | 4 | 0 | 4 | 0 (0.0%/4) | 4 | 4 | 32/20/12 | 32/32 | 0.0% (4) | 4 | 2 (33.3%/6) | 2 | 172,472 |
| `sed` → `sed` → `sed` → `sed` | 8 | 2 | 0/1/0/1 | 0 | 7 | 0 | 1 | 0 (0.0%/7) | 7 | 1 | 32/29/3 | 32/32 | 0.0% (7) | 7 | 0 (0.0%/7) | 1 | 221,687 |
| `rg` → `rg` → `rg` → `sed` | 7 | 2 | 0/1/0/1 | 0 | 2 | 0 | 5 | 0 (0.0%/2) | 2 | 5 | 28/15/13 | 28/28 | 0.0% (2) | 2 | 3 (60.0%/5) | 2 | 162,963 |
| `rg` → `sed` → `sed` → `sed` | 6 | 2 | 0/1/0/1 | 0 | 2 | 0 | 4 | 0 (0.0%/2) | 2 | 4 | 24/13/11 | 24/24 | 0.0% (2) | 2 | 2 (50.0%/4) | 2 | 199,962 |
| `sed` → `sed` → `rg` → `sed` | 6 | 3 | 0/1/0/2 | 0 | 3 | 0 | 3 | 0 (0.0%/3) | 3 | 3 | 24/14/10 | 24/24 | 0.0% (3) | 3 | 2 (40.0%/5) | 1 | 71,178 |
| `git` → `git` → `git` → `git` | 5 | 2 | 0/1/0/1 | 0 | 3 | 0 | 2 | 0 (0.0%/3) | 3 | 2 | 20/12/8 | 20/20 | 0.0% (3) | 3 | 0 (0.0%/3) | 2 | 204,115 |
| `rg` → `rg` → `sed` → `sed` | 5 | 2 | 0/1/0/1 | 0 | 2 | 0 | 3 | 0 (0.0%/2) | 2 | 3 | 20/13/7 | 20/20 | 0.0% (2) | 2 | 3 (60.0%/5) | 0 | 154,213 |

## Repeated normalized shapes

### Length 2

| Sequence | Total | Sessions | Sessions E/D/M/U | Explicit | Direct | Mixed | Unknown | Same response (denom) | Confirmed occurrences | Requested-only occurrences | Subcommands req/conf/unknown | Matched invocations | Batched fraction (denom) | Success | Failed (rate/known) | Unknown status | Output bytes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `sed -n <arg> <arg>` → `sed -n <arg> <arg>` | 58 | 3 | 0/1/0/2 | 0 | 27 | 0 | 31 | 5 (18.5%/27) | 32 | 26 | 116/74/42 | 116/116 | 0.0% (27) | 27 | 10 (27.0%/37) | 21 | 787,728 |
| `rg -n <pattern> <paths>` → `rg -n <pattern> <paths>` | 41 | 2 | 0/1/0/1 | 0 | 5 | 0 | 36 | 2 (40.0%/5) | 5 | 36 | 82/14/68 | 82/82 | 0.0% (5) | 5 | 2 (28.6%/7) | 34 | 172,311 |
| `rg -n <pattern> <paths>` → `sed -n <arg> <arg>` | 31 | 3 | 0/1/0/2 | 0 | 3 | 0 | 28 | 0 (0.0%/3) | 5 | 26 | 62/20/42 | 62/62 | 0.0% (3) | 3 | 10 (76.9%/13) | 18 | 211,634 |
| `sed -n <arg> <arg>` → `rg -n <pattern> <paths>` | 18 | 3 | 0/1/0/2 | 0 | 3 | 0 | 15 | 0 (0.0%/3) | 3 | 15 | 36/12/24 | 36/36 | 0.0% (3) | 3 | 6 (66.7%/9) | 9 | 124,578 |
| `python -m unittest -m -v <selector>` → `python -m unittest -m -s -v <selector> <selector>` | 10 | 1 | 0/0/0/1 | 0 | 0 | 0 | 10 | 0 (n/a/0) | 0 | 10 | 20/4/16 | 20/20 | n/a (0) | 0 | 0 (n/a/0) | 10 | 84,816 |
| `forge <arg>` → `forge --match-path -vv <arg> <arg>` | 9 | 1 | 0/0/0/1 | 0 | 0 | 0 | 9 | 0 (n/a/0) | 0 | 9 | 18/0/18 | 0/18 | n/a (0) | 0 | 0 (n/a/0) | 9 | 0 |
| `git fetch` → `git status --short --branch` | 9 | 1 | 0/0/0/1 | 0 | 0 | 0 | 9 | 0 (n/a/0) | 0 | 9 | 18/0/18 | 18/18 | n/a (0) | 0 | 0 (n/a/0) | 9 | 15,110 |
| `python -m unittest -m -v <selector>` → `python -m unittest -m -v <selector>` | 9 | 2 | 0/1/0/1 | 0 | 4 | 0 | 5 | 0 (0.0%/4) | 5 | 4 | 18/14/4 | 18/18 | 0.0% (4) | 0 | 8 (100.0%/8) | 1 | 62,640 |
| `python -m unittest -m -v <selector>` → `sed -n <arg> <arg>` | 9 | 2 | 0/1/0/1 | 0 | 5 | 0 | 4 | 0 (0.0%/5) | 1 | 8 | 18/10/8 | 18/18 | 0.0% (5) | 0 | 5 (100.0%/5) | 4 | 81,049 |
| `rg -n -C <pattern> <paths>` → `rg -n -C <pattern> <paths>` | 9 | 2 | 0/1/0/1 | 0 | 3 | 0 | 6 | 3 (100.0%/3) | 5 | 4 | 18/12/6 | 18/18 | 0.0% (3) | 3 | 2 (40.0%/5) | 4 | 107,223 |
| `curl -fsS --max-time <arg> <arg>` → `gh --paginate --jq <arg> <arg> <arg>` | 7 | 1 | 0/1/0/0 | 0 | 7 | 0 | 0 | 7 (100.0%/7) | 7 | 0 | 14/14/0 | 14/14 | 0.0% (7) | 7 | 0 (0.0%/7) | 0 | 6,096 |
| `git status --short --branch` → `cat <arg>` | 7 | 1 | 0/0/0/1 | 0 | 0 | 0 | 7 | 0 (n/a/0) | 0 | 7 | 14/0/14 | 14/14 | n/a (0) | 0 | 0 (n/a/0) | 7 | 149,070 |
| `sleep <arg>` → `curl -fsS --max-time <arg> <arg>` | 7 | 1 | 0/1/0/0 | 0 | 7 | 0 | 0 | 0 (0.0%/7) | 3 | 4 | 14/10/4 | 14/14 | 0.0% (7) | 3 | 0 (0.0%/3) | 4 | 5,220 |
| `tail -n <arg> <arg>` → `tail -n <arg> <arg>` | 7 | 1 | 0/0/0/1 | 0 | 0 | 0 | 7 | 0 (n/a/0) | 0 | 7 | 14/0/14 | 14/14 | n/a (0) | 0 | 0 (n/a/0) | 7 | 44,168 |
| `forge <arg>` → `forge <arg>` | 6 | 1 | 0/0/0/1 | 0 | 0 | 0 | 6 | 0 (n/a/0) | 0 | 6 | 12/1/11 | 1/12 | n/a (0) | 0 | 0 (n/a/0) | 6 | 234 |
| `rg -n -C <pattern> <paths>` → `sed -n <arg> <arg>` | 6 | 2 | 0/0/0/2 | 0 | 0 | 0 | 6 | 0 (n/a/0) | 0 | 6 | 12/2/10 | 12/12 | n/a (0) | 0 | 2 (100.0%/2) | 4 | 63,663 |
| `sed -n <arg> <arg>` → `rg -n --glob <pattern> <paths>` | 6 | 2 | 0/1/0/1 | 0 | 3 | 0 | 3 | 1 (33.3%/3) | 3 | 3 | 12/6/6 | 12/12 | 0.0% (3) | 2 | 1 (33.3%/3) | 3 | 56,904 |
| `gh --jq <arg> <arg> <arg>` → `gh --jq <arg> <arg> <arg>` | 5 | 2 | 0/1/0/1 | 0 | 3 | 0 | 2 | 0 (0.0%/3) | 3 | 2 | 10/6/4 | 10/10 | 0.0% (3) | 1 | 2 (66.7%/3) | 2 | 6,565 |
| `git fetch --prune` → `cat <arg>` | 5 | 1 | 0/0/0/1 | 0 | 0 | 0 | 5 | 0 (n/a/0) | 0 | 5 | 10/0/10 | 10/10 | n/a (0) | 0 | 0 (n/a/0) | 5 | 116,175 |
| `python3 -c <arg>` → `go test -tags -timeout -count -run` | 5 | 1 | 0/0/0/1 | 0 | 0 | 0 | 5 | 0 (n/a/0) | 0 | 5 | 10/0/10 | 10/10 | n/a (0) | 0 | 0 (n/a/0) | 5 | 1,046 |

### Length 3

| Sequence | Total | Sessions | Sessions E/D/M/U | Explicit | Direct | Mixed | Unknown | Same response (denom) | Confirmed occurrences | Requested-only occurrences | Subcommands req/conf/unknown | Matched invocations | Batched fraction (denom) | Success | Failed (rate/known) | Unknown status | Output bytes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `sed -n <arg> <arg>` → `sed -n <arg> <arg>` → `sed -n <arg> <arg>` | 20 | 3 | 0/1/0/2 | 0 | 13 | 0 | 7 | 1 (7.7%/13) | 13 | 7 | 60/44/16 | 60/60 | 0.0% (13) | 13 | 2 (13.3%/15) | 5 | 416,104 |
| `rg -n <pattern> <paths>` → `rg -n <pattern> <paths>` → `rg -n <pattern> <paths>` | 14 | 2 | 0/1/0/1 | 0 | 1 | 0 | 13 | 0 (0.0%/1) | 1 | 13 | 42/5/37 | 42/42 | 0.0% (1) | 1 | 1 (50.0%/2) | 12 | 87,298 |
| `sed -n <arg> <arg>` → `sed -n <arg> <arg>` → `rg -n <pattern> <paths>` | 9 | 3 | 0/1/0/2 | 0 | 2 | 0 | 7 | 0 (0.0%/2) | 2 | 7 | 27/14/13 | 27/27 | 0.0% (2) | 2 | 4 (66.7%/6) | 3 | 113,794 |
| `rg -n <pattern> <paths>` → `rg -n <pattern> <paths>` → `sed -n <arg> <arg>` | 8 | 2 | 0/1/0/1 | 0 | 1 | 0 | 7 | 0 (0.0%/1) | 1 | 7 | 24/7/17 | 24/24 | 0.0% (1) | 1 | 2 (66.7%/3) | 5 | 80,693 |
| `git fetch` → `git status --short --branch` → `cat <arg>` | 6 | 1 | 0/0/0/1 | 0 | 0 | 0 | 6 | 0 (n/a/0) | 0 | 6 | 18/0/18 | 18/18 | n/a (0) | 0 | 0 (n/a/0) | 6 | 149,154 |
| `sed -n <arg> <arg>` → `rg -n <pattern> <paths>` → `sed -n <arg> <arg>` | 6 | 3 | 0/1/0/2 | 0 | 1 | 0 | 5 | 0 (0.0%/1) | 1 | 5 | 18/7/11 | 18/18 | 0.0% (1) | 1 | 3 (75.0%/4) | 2 | 50,074 |
| `rg -n -C <pattern> <paths>` → `rg -n -C <pattern> <paths>` → `rg -n -C <pattern> <paths>` | 5 | 2 | 0/1/0/1 | 0 | 2 | 0 | 3 | 2 (100.0%/2) | 3 | 2 | 15/10/5 | 15/15 | 0.0% (2) | 2 | 1 (33.3%/3) | 2 | 92,373 |
| `python -m unittest -m -v <selector>` → `python -m unittest -m -v <selector>` → `sed -n <arg> <arg>` | 4 | 2 | 0/1/0/1 | 0 | 3 | 0 | 1 | 0 (0.0%/3) | 1 | 3 | 12/9/3 | 12/12 | 0.0% (3) | 0 | 3 (100.0%/3) | 1 | 44,595 |
| `rg -n <pattern> <paths>` → `sed -n <arg> <arg>` → `rg -n <pattern> <paths>` | 4 | 1 | 0/0/0/1 | 0 | 0 | 0 | 4 | 0 (n/a/0) | 0 | 4 | 12/2/10 | 12/12 | n/a (0) | 0 | 2 (100.0%/2) | 2 | 36,006 |
| `rg -n <pattern> <paths>` → `sed -n <arg> <arg>` → `sed -n <arg> <arg>` | 4 | 1 | 0/0/0/1 | 0 | 0 | 0 | 4 | 0 (n/a/0) | 0 | 4 | 12/5/7 | 12/12 | n/a (0) | 0 | 3 (100.0%/3) | 1 | 62,645 |
| `tail -n <arg> <arg>` → `tail -n <arg> <arg>` → `tail -n <arg> <arg>` | 4 | 1 | 0/0/0/1 | 0 | 0 | 0 | 4 | 0 (n/a/0) | 0 | 4 | 12/0/12 | 12/12 | n/a (0) | 0 | 0 (n/a/0) | 4 | 38,557 |
| `curl -fsS --max-time <arg> <arg>` → `gh --paginate --jq <arg> <arg> <arg>` → `curl -fsS --max-time <arg> <arg>` | 3 | 1 | 0/1/0/0 | 0 | 3 | 0 | 0 | 0 (0.0%/3) | 3 | 0 | 9/9/0 | 9/9 | 0.0% (3) | 3 | 0 (0.0%/3) | 0 | 4,408 |
| `go test -tags -timeout -count -run` → `python3 -c <arg>` → `python3 -c <arg>` | 3 | 1 | 0/0/0/1 | 0 | 0 | 0 | 3 | 0 (n/a/0) | 0 | 3 | 9/3/6 | 9/9 | n/a (0) | 0 | 3 (100.0%/3) | 0 | 1,547 |
| `python -m unittest -m -s -q <selector> <selector>` → `sed -n <arg> <arg>` → `python -m unittest -m -s -q <selector> <selector>` | 3 | 1 | 0/1/0/0 | 0 | 3 | 0 | 0 | 0 (0.0%/3) | 3 | 0 | 9/9/0 | 9/9 | 0.0% (3) | 0 | 3 (100.0%/3) | 0 | 25,343 |
| `python -m unittest -m -v <selector>` → `python -m unittest -m -v <selector>` → `rg -n -C <pattern> <paths>` | 3 | 1 | 0/0/0/1 | 0 | 0 | 0 | 3 | 0 (n/a/0) | 1 | 2 | 9/6/3 | 9/9 | n/a (0) | 0 | 3 (100.0%/3) | 0 | 43,597 |

### Length 4

| Sequence | Total | Sessions | Sessions E/D/M/U | Explicit | Direct | Mixed | Unknown | Same response (denom) | Confirmed occurrences | Requested-only occurrences | Subcommands req/conf/unknown | Matched invocations | Batched fraction (denom) | Success | Failed (rate/known) | Unknown status | Output bytes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `sed -n <arg> <arg>` → `sed -n <arg> <arg>` → `sed -n <arg> <arg>` → `sed -n <arg> <arg>` | 8 | 2 | 0/1/0/1 | 0 | 7 | 0 | 1 | 0 (0.0%/7) | 7 | 1 | 32/29/3 | 32/32 | 0.0% (7) | 7 | 0 (0.0%/7) | 1 | 221,687 |
| `rg -n <pattern> <paths>` → `rg -n <pattern> <paths>` → `rg -n <pattern> <paths>` → `rg -n <pattern> <paths>` | 6 | 1 | 0/0/0/1 | 0 | 0 | 0 | 6 | 0 (n/a/0) | 0 | 6 | 24/0/24 | 24/24 | n/a (0) | 0 | 0 (n/a/0) | 6 | 34,758 |
| `rg -n <pattern> <paths>` → `rg -n <pattern> <paths>` → `rg -n <pattern> <paths>` → `sed -n <arg> <arg>` | 4 | 2 | 0/1/0/1 | 0 | 1 | 0 | 3 | 0 (0.0%/1) | 1 | 3 | 16/7/9 | 16/16 | 0.0% (1) | 1 | 1 (50.0%/2) | 2 | 48,587 |
| `python3 -c <arg>` → `go test -tags -timeout -count -run` → `python3 -c <arg>` → `python3 -c <arg>` | 3 | 1 | 0/0/0/1 | 0 | 0 | 0 | 3 | 0 (n/a/0) | 0 | 3 | 12/3/9 | 12/12 | n/a (0) | 0 | 3 (100.0%/3) | 0 | 1,721 |
| `rg -n <pattern> <paths>` → `rg -n <pattern> <paths>` → `sed -n <arg> <arg>` → `rg -n <pattern> <paths>` | 3 | 1 | 0/0/0/1 | 0 | 0 | 0 | 3 | 0 (n/a/0) | 0 | 3 | 12/2/10 | 12/12 | n/a (0) | 0 | 1 (100.0%/1) | 2 | 14,196 |
| `rg -n <pattern> <paths>` → `sed -n <arg> <arg>` → `sed -n <arg> <arg>` → `rg -n <pattern> <paths>` | 3 | 1 | 0/0/0/1 | 0 | 0 | 0 | 3 | 0 (n/a/0) | 0 | 3 | 12/4/8 | 12/12 | n/a (0) | 0 | 2 (100.0%/2) | 1 | 47,580 |
| `sed -n <arg> <arg>` → `sed -n <arg> <arg>` → `rg -n <pattern> <paths>` → `sed -n <arg> <arg>` | 3 | 3 | 0/1/0/2 | 0 | 1 | 0 | 2 | 0 (0.0%/1) | 1 | 2 | 12/5/7 | 12/12 | 0.0% (1) | 1 | 1 (50.0%/2) | 1 | 19,455 |
| `sed -n <arg> <arg>` → `sed -n <arg> <arg>` → `sed -n <arg> <arg>` → `rg -n <pattern> <paths>` | 3 | 2 | 0/1/0/1 | 0 | 2 | 0 | 1 | 0 (0.0%/2) | 2 | 1 | 12/8/4 | 12/12 | 0.0% (2) | 2 | 0 (0.0%/2) | 1 | 36,133 |
| `touch <arg>` → `python3 -c <arg>` → `go test -tags -timeout -count -run` → `python3 -c <arg>` | 3 | 1 | 0/0/0/1 | 0 | 0 | 0 | 3 | 0 (n/a/0) | 0 | 3 | 12/3/9 | 12/12 | n/a (0) | 0 | 3 (100.0%/3) | 0 | 1,481 |
| `curl -fsS --max-time <arg> <arg>` → `gh --repo --limit --json <arg> <arg> <arg> <arg> <arg>` → `gh --paginate --jq <arg> <arg> <arg>` → `gh --repo --exit-status --interval <arg> <arg> <arg> <arg> <arg>` | 2 | 1 | 0/1/0/0 | 0 | 2 | 0 | 0 | 0 (0.0%/2) | 1 | 1 | 8/7/1 | 8/8 | 0.0% (2) | 1 | 0 (0.0%/1) | 1 | 10,782 |

## Explicit batch sequences

No repeated explicit-batch sequence observed.

## Direct-call sequences

| Sequence | Direct | Total | Sessions | Same response | Matched invocations | Subcommands req/conf/unknown | Failed | Unknown status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `rg` → `rg` | 21 | 82 | 2 | 11 | 164/164 | 164/60/104 | 11 | 53 |
| `curl` → `gh` | 12 | 12 | 1 | 11 | 24/24 | 24/24/0 | 0 | 0 |
| `git` → `git` | 11 | 32 | 3 | 6 | 60/64 | 64/22/42 | 0 | 21 |
| `gh` → `gh` | 28 | 30 | 2 | 5 | 60/60 | 60/47/13 | 10 | 10 |
| `sed` → `sed` | 27 | 58 | 3 | 5 | 116/116 | 116/74/42 | 10 | 21 |
| `node` → `node` | 7 | 7 | 1 | 4 | 14/14 | 14/14/0 | 2 | 0 |
| `python -m unittest` → `git` | 6 | 10 | 2 | 3 | 20/20 | 20/14/6 | 2 | 3 |
| `curl` → `sudo` | 5 | 5 | 1 | 3 | 10/10 | 10/10/0 | 0 | 0 |
| `sed` → `rg` | 17 | 41 | 3 | 2 | 82/82 | 82/43/39 | 10 | 17 |
| `git` → `rg` | 7 | 9 | 2 | 2 | 18/18 | 18/14/4 | 1 | 2 |
| `rg` → `rg` → `rg` | 7 | 27 | 2 | 3 | 81/81 | 81/29/52 | 3 | 17 |
| `curl` → `gh` → `gh` | 6 | 6 | 1 | 3 | 18/18 | 18/18/0 | 1 | 0 |
| `git` → `git` → `git` | 5 | 9 | 2 | 2 | 27/27 | 27/15/12 | 0 | 4 |
| `node` → `node` → `node` | 5 | 5 | 1 | 2 | 15/15 | 15/15/0 | 2 | 0 |
| `sed` → `sed` → `sed` | 13 | 20 | 3 | 1 | 60/60 | 60/44/16 | 2 | 5 |
| `sed` → `sed` → `rg` | 7 | 17 | 3 | 1 | 51/51 | 51/31/20 | 6 | 5 |
| `git` → `git` → `rg` | 3 | 4 | 2 | 1 | 12/12 | 12/9/3 | 1 | 1 |
| `git` → `rg` → `rg` | 3 | 3 | 1 | 1 | 9/9 | 9/9/0 | 0 | 0 |
| `python -m unittest` → `go test` → `cargo fmt` | 2 | 2 | 1 | 1 | 6/6 | 6/6/0 | 0 | 0 |
| `gh` → `gh` → `gh` | 16 | 17 | 2 | 0 | 51/51 | 51/41/10 | 8 | 7 |
| `rg` → `rg` → `rg` → `rg` | 4 | 11 | 2 | 1 | 44/44 | 44/16/28 | 0 | 7 |
| `gh` → `gh` → `gh` → `gh` | 10 | 10 | 1 | 0 | 40/40 | 40/35/5 | 7 | 3 |
| `sed` → `sed` → `sed` → `sed` | 7 | 8 | 2 | 0 | 32/32 | 32/29/3 | 0 | 1 |
| `rg` → `rg` → `sed` → `rg` | 4 | 8 | 2 | 0 | 32/32 | 32/18/14 | 3 | 3 |
| `sed` → `sed` → `sed` → `rg` | 4 | 8 | 3 | 0 | 32/32 | 32/20/12 | 2 | 2 |
| `sed` → `sed` → `rg` → `sed` | 3 | 6 | 3 | 0 | 24/24 | 24/14/10 | 2 | 1 |
| `git` → `git` → `git` → `git` | 3 | 5 | 2 | 0 | 20/20 | 20/12/8 | 0 | 2 |
| `rg` → `sed` → `rg` → `sed` | 3 | 5 | 2 | 0 | 20/20 | 20/15/5 | 3 | 0 |
| `sed` → `rg` → `rg` → `sed` | 3 | 4 | 2 | 0 | 16/16 | 16/13/3 | 2 | 0 |
| `node` → `node` → `node` → `node` | 3 | 3 | 1 | 0 | 12/12 | 12/12/0 | 2 | 0 |
## Edge evidence

| Intervening class | Edges |
| --- | --- |
| `assistant_decision_observed` | 426 |
| `edit_or_other_tool` | 229 |
| `none_observed` | 75 |
| `tool_output_only` | 64 |
| `unknown` | 2 |
| `user_turn_or_session_boundary` | 389 |

### Response-boundary evidence

| Evidence class | Edges |
| --- | --- |
| `same_response_inferred` | 81 |
| `separate_response_observed` | 328 |
| `unknown_response_boundary` | 776 |

### Elapsed-time buckets

| Bucket | Edges |
| --- | --- |
| `10m_plus` | 27 |
| `1s_to_5s` | 224 |
| `2m_to_10m` | 111 |
| `30s_to_2m` | 341 |
| `5s_to_30s` | 385 |
| `lt_1s` | 97 |
## Cross-mode repeats

No repeated family sequence occurred in both explicit and direct modes.

Cross-mode evidence does not show that an unbatched occurrence was safe to batch.

## Same-response cross-mode repeats

No repeated family sequence occurred in both explicit and same-response direct contexts.

## Observed command transitions

| First | Next | Count | Follow rate (denom) | Sessions | Next output bytes |
| --- | --- | --- | --- | --- | --- |
| `rg` | `rg` | 82 | 47.1% (174) | 2 | 376,208 |
| `sed` | `sed` | 58 | 42.0% (138) | 3 | 380,555 |
| `rg` | `sed` | 56 | 32.2% (174) | 3 | 249,599 |
| `sed` | `rg` | 41 | 29.7% (138) | 3 | 180,021 |
| `git` | `git` | 32 | 41.6% (77) | 3 | 109,528 |
| `python -m unittest` | `python -m unittest` | 31 | 39.2% (79) | 2 | 182,261 |
| `gh` | `gh` | 30 | 66.7% (45) | 2 | 44,174 |
| `forge` | `forge` | 27 | 69.2% (39) | 1 | 56,021 |
| `git` | `cat` | 18 | 23.4% (77) | 3 | 332,857 |
| `python -m unittest` | `sed` | 14 | 17.7% (79) | 2 | 87,454 |
| `curl` | `gh` | 12 | 50.0% (24) | 1 | 10,240 |
| `cargo test` | `cargo test` | 11 | 42.3% (26) | 3 | 62,199 |
| `python -m unittest` | `rg` | 11 | 13.9% (79) | 2 | 18,881 |
| `python -m unittest` | `git` | 10 | 12.7% (79) | 2 | 1,538 |
| `git` | `rg` | 9 | 11.7% (77) | 2 | 33,259 |

### Low-frequency high-output transitions

| First | Next | Count | Next output bytes | Mean next output bytes |
| --- | --- | --- | --- | --- |
| `npm run` | `npm test` | 1 | 40,217 | 40,217 |
| `python -m unittest` | `npm test` | 1 | 40,217 | 40,217 |
| `sed` | `npm test` | 1 | 40,217 | 40,217 |
| `rg` | `cat` | 3 | 30,307 | 10,102 |
| `cat` | `python -m unittest` | 3 | 22,337 | 7,445 |
| `git` | `sed` | 3 | 22,303 | 7,434 |
| `go test` | `node` | 2 | 18,171 | 9,085 |
| `cat` | `sed` | 2 | 17,143 | 8,571 |
| `ps` | `python -m unittest` | 1 | 16,188 | 16,188 |
| `node` | `sed` | 2 | 15,508 | 7,754 |
Follow rates describe observed physical transitions only and do not establish batch safety.

## Conservative batching candidates

| Sequence | Sanitized shape sample | Category | Total | Explicit | Direct | Failed | Unknown status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `python -m unittest` → `go test` | `python -m unittest -m -s -q <selector> <selector>` → `go test -count -run` | `plausible_static_sequence` | 2 | 0 | 2 | 0 | 0 |
| `rg` → `rg` | `rg -n <pattern> <paths>` → `rg -n <pattern> <paths>` | `decision_dependent` | 82 | 0 | 21 | 11 | 53 |
| `sed` → `sed` | `sed -n <arg> <arg>` → `sed -n <arg> <arg>` | `decision_dependent` | 58 | 0 | 27 | 10 | 21 |
| `rg` → `sed` | `rg -n <pattern> <paths>` → `sed -n <arg> <arg>` | `decision_dependent` | 56 | 0 | 18 | 13 | 25 |
| `sed` → `rg` | `sed -n <arg> <arg>` → `rg -n <pattern> <paths>` | `decision_dependent` | 41 | 0 | 17 | 10 | 17 |
| `python -m unittest` → `python -m unittest` | `python -m unittest -m -v <selector>` → `python -m unittest -m -s -v <selector> <selector>` | `decision_dependent` | 31 | 0 | 7 | 11 | 19 |
| `gh` → `gh` | `gh --jq <arg> <arg> <arg>` → `gh --jq <arg> <arg> <arg>` | `decision_dependent` | 30 | 0 | 28 | 10 | 10 |
| `forge` → `forge` | `forge <arg>` → `forge --match-path -vv <arg> <arg>` | `decision_dependent` | 27 | 0 | 0 | 6 | 21 |
| `rg` → `rg` → `rg` | `rg -n <pattern> <paths>` → `rg -n <pattern> <paths>` → `rg -n <pattern> <paths>` | `decision_dependent` | 27 | 0 | 7 | 3 | 17 |
| `rg` → `rg` → `sed` | `rg -n <pattern> <paths>` → `rg -n <pattern> <paths>` → `sed -n <arg> <arg>` | `decision_dependent` | 21 | 0 | 8 | 6 | 9 |
| `sed` → `sed` → `sed` | `sed -n <arg> <arg>` → `sed -n <arg> <arg>` → `sed -n <arg> <arg>` | `decision_dependent` | 20 | 0 | 13 | 2 | 5 |
| `gh` → `gh` → `gh` | `gh --jq <arg> <arg> <arg>` → `gh --jq <arg> <arg> <arg>` → `gh --jq <arg> <arg> <arg>` | `decision_dependent` | 17 | 0 | 16 | 8 | 7 |
| `sed` → `sed` → `rg` | `sed -n <arg> <arg>` → `sed -n <arg> <arg>` → `rg -n <pattern> <paths>` | `decision_dependent` | 17 | 0 | 7 | 6 | 5 |
| `python -m unittest` → `sed` | `python -m unittest -m -v <selector>` → `sed -n <arg> <arg>` | `decision_dependent` | 14 | 0 | 8 | 8 | 6 |
| `rg` → `sed` → `rg` | `rg -n <pattern> <paths>` → `sed -n <arg> <arg>` → `rg -n <pattern> <paths>` | `decision_dependent` | 14 | 0 | 7 | 5 | 5 |
| `sed` → `rg` → `sed` | `sed -n <arg> <arg>` → `rg -n <pattern> <paths>` → `sed -n <arg> <arg>` | `decision_dependent` | 13 | 0 | 6 | 3 | 4 |
| `rg` → `sed` → `sed` | `rg -n <pattern> <paths>` → `sed -n <arg> <arg>` → `sed -n <arg> <arg>` | `decision_dependent` | 12 | 0 | 3 | 4 | 5 |
| `cargo test` → `cargo test` | `cargo test --locked --manifest-path --test --nocapture` → `cargo test --locked --manifest-path --test --nocapture` | `decision_dependent` | 11 | 0 | 6 | 4 | 2 |
| `python -m unittest` → `rg` | `python -m unittest -m -s -v <selector> <selector>` → `rg -n <pattern> <paths>` | `decision_dependent` | 11 | 0 | 1 | 7 | 4 |
| `forge` → `forge` → `forge` | `forge <arg>` → `forge --match-path -vv <arg> <arg>` → `forge --match-path -vvv <arg> <arg>` | `decision_dependent` | 10 | 0 | 0 | 6 | 4 |
| `gh` → `gh` → `gh` → `gh` | `gh --repo --limit --json <arg> <arg> <arg> <arg> <arg>` → `gh --paginate --jq <arg> <arg> <arg>` → `gh --repo --exit-status --interval <arg> <arg> <arg> <arg> <arg>` → `gh --repo --exit-status --interval <arg> <arg> <arg> <arg> <arg>` | `decision_dependent` | 10 | 0 | 10 | 7 | 3 |
| `python -m unittest` → `git` | `python -m unittest -m -s -q <selector> <selector>` → `git diff --check` | `decision_dependent` | 10 | 0 | 6 | 2 | 3 |
| `sed` → `rg` → `rg` | `sed -n <arg> <arg>` → `rg -n <pattern> <paths>` → `rg -n <pattern> <paths>` | `decision_dependent` | 10 | 0 | 4 | 3 | 4 |
| `git` → `rg` | `git status --short` → `rg -n <pattern> <paths>` | `decision_dependent` | 9 | 0 | 7 | 1 | 2 |
| `sed` → `python -m unittest` | `sed -n <arg> <arg>` → `python -m unittest -m -s -q <selector> <selector>` | `decision_dependent` | 9 | 0 | 7 | 4 | 2 |
| `rg` → `python -m unittest` | `rg --files --hidden <pattern>` → `python -m unittest -m -v <selector>` | `decision_dependent` | 8 | 0 | 4 | 2 | 4 |
| `rg` → `rg` → `sed` → `rg` | `rg -n <pattern> <paths>` → `rg -n <pattern> <paths>` → `sed -n <arg> <arg>` → `rg -n <pattern> <paths>` | `decision_dependent` | 8 | 0 | 4 | 3 | 3 |
| `sed` → `sed` → `sed` → `rg` | `sed -n <arg> <arg>` → `sed -n <arg> <arg>` → `sed -n <arg> <arg>` → `rg -n <pattern> <paths>` | `decision_dependent` | 8 | 0 | 4 | 2 | 2 |
| `gh` → `curl` | `gh --paginate --jq <arg> <arg> <arg>` → `curl -fsS --max-time <arg> <arg>` | `decision_dependent` | 7 | 0 | 7 | 1 | 1 |
| `node` → `node` | `node <arg>` → `node <arg>` | `decision_dependent` | 7 | 0 | 7 | 2 | 0 |

## Boundaries and limitations

- Physical JSONL order separates sources; files are never joined by timestamp.
- Same-response evidence uses a following `token_usage_record.response_id`.
- Output-only interruptions remain eligible but are labeled separately.
- Assistant reasoning or messages, edits, other tools, and user/turn boundaries are preserved as intervening evidence.
- Custom exec bundles with multiple shell calls are excluded as ambiguously ordered.
- Compound shell expressions remain one invocation; syntactic segments are not promoted to sequence atoms.
- Overlapping n-grams are windows, not independent observations.
- Batch output is not attributed to individual subcommands.
