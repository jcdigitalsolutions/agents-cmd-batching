# Compilation and Validation Output Research

Research-only simulation. Raw commands, paths, diagnostics, outputs, prompts, and session IDs are not serialized.

## Coverage

- Cohort: `8e310b5753f4ce1dd4e71e87`
- Coverage verdict: **partial**
- Exhaustive: no
- Classified validation commands: 1,464
- Matched outputs: 14,902
- Status certainty: `cancelled`=54, `failed_verified`=716, `failure_text_inferred`=556, `success_text_inferred`=195, `success_verified`=9,507, `timeout`=116, `unknown`=3,758

## Candidate simulations

| Candidate | Eligible | Transformed | Skipped | Original bytes | Saved bytes | Targeted savings | All matched output | Likely token range |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `aggressive_success` | 578 | 52 | 526 | 1,830,111 | 9,686 | 0.5% | 2.9% | 1,615–3,229 |
| `conservative_success` | 578 | 52 | 526 | 1,830,111 | 9,036 | 0.5% | 2.9% | 1,506–3,012 |
| `terse_failure` | 558 | 126 | 432 | 2,439,516 | 539,863 | 22.1% | 3.8% | 89,978–179,955 |

Significance gates: 102,400 saved bytes and 20% of targeted bytes for an ecosystem/operation.

**Conclusion:** Significant savings observed for at least one targeted ecosystem/operation, but the cohort is not exhaustive.

## Ecosystem and operation comparison

| Ecosystem | Operation | Calls | Sessions | Matched | Original bytes | Clean verified success | Aggressive saved | Conservative saved | Terse failure saved | Certainty |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `go` | `type/check` | 2 | 1 | 2 | 204 | 0.0% | 0 | 0 | 0 | success_verified=2 |
| `go` | `test` | 163 | 3 | 150 | 163,015 | 18.0% | 3,579 | 3,363 | 78,603 | failed_verified=28, success_verified=55, unknown=67 |
| `go` | `format` | 10 | 3 | 9 | 874 | 0.0% | 0 | 0 | 0 | success_verified=8, unknown=1 |
| `node-ts` | `compile/build` | 41 | 3 | 40 | 11,095 | 0.0% | 0 | 0 | 2,286 | failed_verified=6, success_verified=21, unknown=13 |
| `node-ts` | `type/check` | 1 | 1 | 1 | 147 | 0.0% | 0 | 0 | 0 | failed_verified=1 |
| `node-ts` | `test` | 140 | 3 | 132 | 1,562,987 | 0.0% | 0 | 0 | 189,392 | failed_verified=33, failure_text_inferred=3, success_verified=77, unknown=19 |
| `node-ts` | `package-script-unknown` | 13 | 2 | 8 | 1,858 | 0.0% | 0 | 0 | 0 | success_verified=8 |
| `node-ts` | `unknown` | 58 | 4 | 58 | 30,977 | 0.0% | 0 | 0 | 2,781 | failed_verified=8, success_verified=46, unknown=4 |
| `other` | `compile/build` | 13 | 1 | 4 | 33,616 | 0.0% | 0 | 0 | 0 | failure_text_inferred=2, unknown=2 |
| `other` | `test` | 28 | 2 | 17 | 73,205 | 0.0% | 0 | 0 | 0 | failed_verified=1, failure_text_inferred=4, success_text_inferred=6, unknown=6 |
| `python` | `compile/build` | 50 | 3 | 34 | 13,396 | 0.0% | 0 | 0 | 6,508 | failed_verified=5, success_verified=29 |
| `python` | `test` | 355 | 5 | 320 | 1,230,079 | 2.2% | 1,369 | 1,159 | 201,438 | cancelled=1, failed_verified=56, failure_text_inferred=26, success_text_inferred=5, success_verified=126, timeout=3, unknown=103 |
| `rust` | `compile/build` | 41 | 10 | 30 | 43,430 | 26.7% | 1,936 | 1,840 | 834 | failed_verified=1, success_verified=10, unknown=19 |
| `rust` | `type/check` | 16 | 4 | 13 | 32,010 | 15.4% | 476 | 452 | 3,869 | failed_verified=2, failure_text_inferred=1, success_verified=7, unknown=3 |
| `rust` | `lint` | 42 | 7 | 18 | 9,476 | 44.4% | 2,326 | 2,222 | 3,628 | failed_verified=3, failure_text_inferred=1, success_verified=8, unknown=6 |
| `rust` | `test` | 350 | 11 | 238 | 943,288 | 0.0% | 0 | 0 | 50,524 | failed_verified=49, failure_text_inferred=4, success_text_inferred=14, success_verified=114, unknown=57 |
| `rust` | `format` | 141 | 10 | 62 | 119,970 | 0.0% | 0 | 0 | 0 | failed_verified=13, success_verified=42, unknown=7 |

## Packaging

| Packaging | Calls | Matched | Output bytes |
| --- | --- | --- | --- |
| `direct` | 1,136 | 1,136 | 4,269,627 |
| `mixed_unknown` | 61 | 0 | 0 |
| `proxy_batch` | 16 | 0 | 0 |
| `shell_batch` | 251 | 0 | 0 |

## Normalized commands and shapes

| Ecosystem | Operation | Family | Shape | Packaging | Calls | Sessions | Matched | Output bytes | Aggressive saved | Terse saved |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `go` | `type/check` | `go vet` | `go vet` | `direct` | 2 | 1 | 2 | 204 | 0 | 0 |
| `go` | `test` | `go test` | `go test` | `direct` | 150 | 3 | 150 | 163,015 | 3,579 | 78,603 |
| `go` | `test` | `go test` | `go test` | `mixed_unknown` | 11 | 1 | 0 | 0 | 0 | 0 |
| `go` | `test` | `go test` | `go test` | `shell_batch` | 2 | 1 | 0 | 0 | 0 | 0 |
| `go` | `format` | `gofmt` | `gofmt` | `direct` | 9 | 3 | 9 | 874 | 0 | 0 |
| `go` | `format` | `gofmt` | `gofmt` | `mixed_unknown` | 1 | 1 | 0 | 0 | 0 | 0 |
| `node-ts` | `compile/build` | `npm run` | `npm run build` | `direct` | 27 | 2 | 27 | 9,379 | 0 | 2,286 |
| `node-ts` | `compile/build` | `npm run` | `npm run build --prefix` | `direct` | 13 | 1 | 13 | 1,716 | 0 | 0 |
| `node-ts` | `compile/build` | `npm run` | `npm run build --prefix` | `mixed_unknown` | 1 | 1 | 0 | 0 | 0 | 0 |
| `node-ts` | `type/check` | `tsc` | `tsc --version` | `direct` | 1 | 1 | 1 | 147 | 0 | 0 |
| `node-ts` | `test` | `node --test` | `node --test` | `direct` | 77 | 3 | 77 | 574,588 | 0 | 171,043 |
| `node-ts` | `test` | `npm test` | `npm test` | `direct` | 37 | 3 | 37 | 880,854 | 0 | 3,137 |
| `node-ts` | `test` | `node --test` | `node --test --test-name-pattern` | `direct` | 14 | 2 | 14 | 59,109 | 0 | 15,212 |
| `node-ts` | `test` | `node --test` | `node --test` | `mixed_unknown` | 5 | 1 | 0 | 0 | 0 | 0 |
| `node-ts` | `test` | `npm test` | `npm test` | `mixed_unknown` | 2 | 1 | 0 | 0 | 0 | 0 |
| `node-ts` | `test` | `npm test` | `npm test --test-reporter` | `direct` | 2 | 1 | 2 | 567 | 0 | 0 |
| `node-ts` | `test` | `node --test` | `node --test --test-name-pattern` | `mixed_unknown` | 1 | 1 | 0 | 0 | 0 | 0 |
| `node-ts` | `test` | `node --test` | `node --test --test-reporter` | `direct` | 1 | 1 | 1 | 40,217 | 0 | 0 |
| `node-ts` | `test` | `npm test` | `npm test --prefix` | `direct` | 1 | 1 | 1 | 7,652 | 0 | 0 |
| `node-ts` | `package-script-unknown` | `npm <subcommand>` | `npm <subcommand> --prefix` | `shell_batch` | 4 | 1 | 0 | 0 | 0 | 0 |
| `node-ts` | `package-script-unknown` | `npm ci` | `npm ci` | `direct` | 4 | 1 | 4 | 710 | 0 | 0 |
| `node-ts` | `package-script-unknown` | `npm install` | `npm install` | `direct` | 2 | 1 | 2 | 352 | 0 | 0 |
| `node-ts` | `package-script-unknown` | `npm <subcommand>` | `npm <subcommand> --prefix` | `direct` | 1 | 1 | 1 | 636 | 0 | 0 |
| `node-ts` | `package-script-unknown` | `npm cache` | `npm cache --force` | `direct` | 1 | 1 | 1 | 160 | 0 | 0 |
| `node-ts` | `package-script-unknown` | `npm js` | `npm js --prefix` | `shell_batch` | 1 | 1 | 0 | 0 | 0 | 0 |
| `node-ts` | `unknown` | `node` | `node` | `direct` | 51 | 4 | 51 | 20,296 | 0 | 2,781 |
| `node-ts` | `unknown` | `node` | `node --input-type` | `direct` | 5 | 1 | 5 | 6,181 | 0 | 0 |
| `node-ts` | `unknown` | `node` | `node --dry-run` | `direct` | 1 | 1 | 1 | 4,389 | 0 | 0 |
| `node-ts` | `unknown` | `node` | `node --version` | `direct` | 1 | 1 | 1 | 111 | 0 | 0 |
| `other` | `compile/build` | `forge build` | `forge build` | `mixed_unknown` | 9 | 1 | 0 | 0 | 0 | 0 |
| `other` | `compile/build` | `forge build` | `forge build` | `direct` | 3 | 1 | 3 | 17,459 | 0 | 0 |
| `other` | `compile/build` | `forge build` | `forge build --skip --skip` | `direct` | 1 | 1 | 1 | 16,157 | 0 | 0 |
| `other` | `test` | `forge test` | `forge test --match-path` | `direct` | 13 | 1 | 13 | 25,327 | 0 | 0 |
| `other` | `test` | `forge test` | `forge test --match-path` | `mixed_unknown` | 11 | 1 | 0 | 0 | 0 | 0 |
| `other` | `test` | `forge test` | `forge test --match-contract` | `direct` | 1 | 1 | 1 | 477 | 0 | 0 |
| `other` | `test` | `forge test` | `forge test --match-path --match-test` | `direct` | 1 | 1 | 1 | 32,520 | 0 | 0 |
| `other` | `test` | `forge test` | `forge test --match-path --match-test --block-gas-limit` | `direct` | 1 | 1 | 1 | 8,170 | 0 | 0 |
| `other` | `test` | `forge test` | `forge test --match-test` | `direct` | 1 | 1 | 1 | 6,711 | 0 | 0 |
| `python` | `compile/build` | `python -m py_compile` | `python -m py_compile` | `direct` | 20 | 2 | 20 | 2,162 | 0 | 124 |
| `python` | `compile/build` | `python -m compileall` | `python -m compileall` | `direct` | 14 | 3 | 14 | 11,234 | 0 | 6,384 |
| `python` | `compile/build` | `python -m compileall` | `python -m compileall` | `proxy_batch` | 9 | 1 | 0 | 0 | 0 | 0 |
| `python` | `compile/build` | `python -m compileall` | `python -m compileall` | `shell_batch` | 4 | 2 | 0 | 0 | 0 | 0 |
| `python` | `compile/build` | `python -m py_compile` | `python -m py_compile` | `shell_batch` | 3 | 1 | 0 | 0 | 0 | 0 |
| `python` | `test` | `python -m unittest` | `python -m unittest` | `direct` | 298 | 5 | 298 | 1,220,898 | 0 | 196,076 |
| `python` | `test` | `python -m pytest` | `python -m pytest` | `direct` | 22 | 1 | 22 | 9,181 | 1,369 | 5,362 |
| `python` | `test` | `python -m pytest` | `python -m pytest` | `shell_batch` | 19 | 1 | 0 | 0 | 0 | 0 |
| `python` | `test` | `python -m unittest` | `python -m unittest` | `shell_batch` | 7 | 2 | 0 | 0 | 0 | 0 |
| `python` | `test` | `python -m unittest` | `python -m unittest` | `proxy_batch` | 6 | 1 | 0 | 0 | 0 | 0 |
| `python` | `test` | `python -m unittest` | `python -m unittest` | `mixed_unknown` | 2 | 1 | 0 | 0 | 0 | 0 |
| `python` | `test` | `python -m pytest` | `python -m pytest` | `proxy_batch` | 1 | 1 | 0 | 0 | 0 | 0 |
| `rust` | `compile/build` | `cargo build` | `cargo build --release` | `shell_batch` | 11 | 3 | 0 | 0 | 0 | 0 |
| `rust` | `compile/build` | `cargo build` | `cargo build --release` | `direct` | 10 | 6 | 10 | 7,502 | 1,694 | 0 |
| `rust` | `compile/build` | `cargo build` | `cargo build --manifest-path --release --locked` | `direct` | 5 | 2 | 5 | 7,661 | 0 | 0 |
| `rust` | `compile/build` | `cargo build` | `cargo build --locked --release --manifest-path` | `direct` | 4 | 1 | 4 | 10,268 | 0 | 0 |
| `rust` | `compile/build` | `cargo build` | `cargo build --manifest-path --example --locked` | `direct` | 3 | 2 | 3 | 5,874 | 0 | 0 |
| `rust` | `compile/build` | `cargo build` | `cargo build --manifest-path --target --release --locked` | `direct` | 2 | 1 | 2 | 3,348 | 0 | 0 |
| `rust` | `compile/build` | `cargo build` | `cargo build --release --offline --manifest-path` | `direct` | 2 | 1 | 2 | 1,456 | 0 | 0 |
| `rust` | `compile/build` | `cargo build` | `cargo build --manifest-path` | `direct` | 1 | 1 | 1 | 1,963 | 0 | 0 |
| `rust` | `compile/build` | `cargo build` | `cargo build --manifest-path --example` | `direct` | 1 | 1 | 1 | 3,748 | 0 | 0 |
| `rust` | `compile/build` | `cargo build` | `cargo build --manifest-path --target --target-dir --release --locked` | `direct` | 1 | 1 | 1 | 1,359 | 0 | 834 |
| `rust` | `compile/build` | `cargo build` | `cargo build --release --locked` | `direct` | 1 | 1 | 1 | 251 | 242 | 0 |
| `rust` | `type/check` | `cargo check` | `cargo check --manifest-path` | `direct` | 8 | 1 | 8 | 20,328 | 0 | 3,869 |
| `rust` | `type/check` | `cargo check` | `cargo check --all-targets` | `direct` | 4 | 2 | 4 | 7,263 | 476 | 0 |
| `rust` | `type/check` | `cargo check` | `cargo check --all-targets` | `shell_batch` | 3 | 2 | 0 | 0 | 0 | 0 |
| `rust` | `type/check` | `cargo check` | `cargo check` | `direct` | 1 | 1 | 1 | 4,419 | 0 | 0 |
| `rust` | `lint` | `cargo clippy` | `cargo clippy --all-targets` | `shell_batch` | 23 | 2 | 0 | 0 | 0 | 0 |
| `rust` | `lint` | `cargo clippy` | `cargo clippy --all-targets` | `direct` | 11 | 5 | 11 | 4,586 | 952 | 1,718 |
| `rust` | `lint` | `cargo clippy` | `cargo clippy --manifest-path --all-targets` | `direct` | 3 | 1 | 3 | 2,913 | 382 | 1,910 |
| `rust` | `lint` | `cargo clippy` | `cargo clippy --lib --tests` | `direct` | 2 | 1 | 2 | 650 | 632 | 0 |
| `rust` | `lint` | `cargo clippy` | `cargo clippy --all-targets --all-features` | `shell_batch` | 1 | 1 | 0 | 0 | 0 | 0 |
| `rust` | `lint` | `cargo clippy` | `cargo clippy --lib` | `direct` | 1 | 1 | 1 | 369 | 360 | 0 |
| `rust` | `lint` | `cargo clippy` | `cargo clippy --offline --all-targets` | `direct` | 1 | 1 | 1 | 958 | 0 | 0 |
| `rust` | `test` | `cargo test` | `cargo test --manifest-path` | `direct` | 49 | 2 | 49 | 266,552 | 0 | 7,318 |
| `rust` | `test` | `cargo test` | `cargo test --manifest-path --nocapture` | `direct` | 41 | 2 | 41 | 146,057 | 0 | 8,544 |
| `rust` | `test` | `cargo test` | `cargo test` | `shell_batch` | 24 | 3 | 0 | 0 | 0 | 0 |
| `rust` | `test` | `cargo test` | `cargo test --lib` | `shell_batch` | 20 | 2 | 0 | 0 | 0 | 0 |
| `rust` | `test` | `cargo test` | `cargo test --test` | `shell_batch` | 19 | 2 | 0 | 0 | 0 | 0 |
| `rust` | `test` | `cargo test` | `cargo test` | `direct` | 18 | 5 | 18 | 92,510 | 0 | 0 |
| `rust` | `test` | `cargo test` | `cargo test --lib` | `direct` | 16 | 2 | 16 | 57,936 | 0 | 3,354 |
| `rust` | `test` | `cargo test` | `cargo test --locked --manifest-path --test --nocapture` | `direct` | 16 | 1 | 16 | 21,536 | 0 | 0 |
| `rust` | `test` | `cargo test` | `cargo test --lib --nocapture` | `shell_batch` | 12 | 1 | 0 | 0 | 0 | 0 |
| `rust` | `test` | `cargo test` | `cargo test --locked --manifest-path --lib` | `direct` | 12 | 1 | 12 | 33,800 | 0 | 8,640 |
| `rust` | `test` | `cargo test` | `cargo test --all-targets` | `shell_batch` | 11 | 1 | 0 | 0 | 0 | 0 |
| `rust` | `test` | `cargo test` | `cargo test --test --nocapture` | `direct` | 11 | 1 | 11 | 14,001 | 0 | 0 |
| `rust` | `test` | `cargo test` | `cargo test --test --nocapture` | `shell_batch` | 10 | 1 | 0 | 0 | 0 | 0 |
| `rust` | `test` | `cargo test` | `cargo test --offline --manifest-path` | `direct` | 9 | 1 | 9 | 10,930 | 0 | 0 |
| `rust` | `test` | `cargo test` | `cargo test --locked --manifest-path` | `direct` | 8 | 1 | 8 | 73,208 | 0 | 16,516 |
| `rust` | `test` | `cargo test` | `cargo test --offline` | `direct` | 6 | 2 | 6 | 30,712 | 0 | 1,026 |
| `rust` | `test` | `cargo test` | `cargo test --nocapture` | `direct` | 5 | 2 | 5 | 11,161 | 0 | 0 |
| `rust` | `test` | `cargo test` | `cargo test --nocapture` | `shell_batch` | 5 | 2 | 0 | 0 | 0 | 0 |
| `rust` | `test` | `cargo test` | `cargo test --test` | `direct` | 5 | 2 | 5 | 10,789 | 0 | 0 |
| `rust` | `test` | `cargo test` | `cargo test --manifest-path --lib` | `direct` | 4 | 1 | 4 | 20,775 | 0 | 893 |
| `rust` | `test` | `cargo test` | `cargo test --manifest-path --test` | `direct` | 4 | 1 | 4 | 5,586 | 0 | 0 |
| `rust` | `test` | `cargo test` | `cargo test --manifest-path --test --nocapture` | `direct` | 4 | 1 | 4 | 15,163 | 0 | 0 |
| `rust` | `test` | `cargo test` | `cargo test --manifest-path --lib --locked` | `direct` | 3 | 1 | 3 | 18,818 | 0 | 0 |
| `rust` | `test` | `cargo test` | `cargo test --manifest-path --lib --no-fail-fast` | `direct` | 3 | 1 | 3 | 11,937 | 0 | 616 |
| `rust` | `test` | `cargo test` | `cargo test --manifest-path --locked` | `direct` | 3 | 2 | 3 | 10,395 | 0 | 3,617 |
| `rust` | `test` | `cargo test` | `cargo test --manifest-path --no-fail-fast` | `direct` | 3 | 1 | 3 | 38,604 | 0 | 0 |
| `rust` | `test` | `cargo test` | `cargo test --all-targets` | `direct` | 2 | 1 | 2 | 17,276 | 0 | 0 |
| `rust` | `test` | `cargo test` | `cargo test --all-targets --all-features` | `direct` | 2 | 1 | 2 | 12,397 | 0 | 0 |
| `rust` | `test` | `cargo test` | `cargo test --manifest-path` | `mixed_unknown` | 2 | 1 | 0 | 0 | 0 | 0 |
| `rust` | `test` | `cargo test` | `cargo test --manifest-path --lib --nocapture` | `direct` | 2 | 1 | 2 | 5,022 | 0 | 0 |
| `rust` | `test` | `cargo test` | `cargo test --manifest-path --locked --lib --no-fail-fast` | `direct` | 2 | 1 | 2 | 3,098 | 0 | 0 |
| `rust` | `test` | `cargo test` | `cargo test --manifest-path --no-run` | `direct` | 2 | 1 | 2 | 3,855 | 0 | 0 |
| `rust` | `test` | `cargo test` | `cargo test --manifest-path --test --locked` | `mixed_unknown` | 2 | 1 | 0 | 0 | 0 | 0 |
| `rust` | `test` | `cargo test` | `cargo test --quiet --lib --exact` | `direct` | 2 | 1 | 2 | 432 | 0 | 0 |
| `rust` | `test` | `cargo test` | `cargo test --lib` | `mixed_unknown` | 1 | 1 | 0 | 0 | 0 | 0 |
| `rust` | `test` | `cargo test` | `cargo test --lib --nocapture` | `direct` | 1 | 1 | 1 | 1,106 | 0 | 0 |
| `rust` | `test` | `cargo test` | `cargo test --manifest-path` | `shell_batch` | 1 | 1 | 0 | 0 | 0 | 0 |
| `rust` | `test` | `cargo test` | `cargo test --manifest-path --exact` | `direct` | 1 | 1 | 1 | 1,837 | 0 | 0 |
| `rust` | `test` | `cargo test` | `cargo test --manifest-path --lib` | `mixed_unknown` | 1 | 1 | 0 | 0 | 0 | 0 |
| `rust` | `test` | `cargo test` | `cargo test --manifest-path --lib --locked` | `mixed_unknown` | 1 | 1 | 0 | 0 | 0 | 0 |
| `rust` | `test` | `cargo test` | `cargo test --manifest-path --locked --lib` | `mixed_unknown` | 1 | 1 | 0 | 0 | 0 | 0 |
| `rust` | `test` | `cargo test` | `cargo test --manifest-path --locked --test --exact` | `mixed_unknown` | 1 | 1 | 0 | 0 | 0 | 0 |
| `rust` | `test` | `cargo test` | `cargo test --manifest-path --test --locked` | `direct` | 1 | 1 | 1 | 1,927 | 0 | 0 |
| `rust` | `test` | `cargo test` | `cargo test --manifest-path --test --test --test` | `direct` | 1 | 1 | 1 | 3,678 | 0 | 0 |
| `rust` | `test` | `cargo test` | `cargo test --offline --manifest-path --exact` | `direct` | 1 | 1 | 1 | 568 | 0 | 0 |
| `rust` | `test` | `cargo test` | `cargo test --offline --test --nocapture` | `direct` | 1 | 1 | 1 | 1,622 | 0 | 0 |
| `rust` | `test` | `cargo test` | `cargo test --test` | `mixed_unknown` | 1 | 1 | 0 | 0 | 0 | 0 |
| `rust` | `format` | `cargo fmt` | `cargo fmt --all` | `shell_batch` | 34 | 2 | 0 | 0 | 0 | 0 |
| `rust` | `format` | `cargo fmt` | `cargo fmt --manifest-path --check` | `direct` | 19 | 3 | 19 | 103,939 | 0 | 0 |
| `rust` | `format` | `rustfmt` | `rustfmt --edition` | `direct` | 15 | 2 | 15 | 1,530 | 0 | 0 |
| `rust` | `format` | `cargo fmt` | `cargo fmt` | `shell_batch` | 14 | 2 | 0 | 0 | 0 | 0 |
| `rust` | `format` | `cargo fmt` | `cargo fmt --check` | `shell_batch` | 12 | 1 | 0 | 0 | 0 | 0 |
| `rust` | `format` | `cargo fmt` | `cargo fmt --all --check` | `shell_batch` | 11 | 1 | 0 | 0 | 0 | 0 |
| `rust` | `format` | `cargo fmt` | `cargo fmt --all` | `direct` | 6 | 3 | 6 | 661 | 0 | 0 |
| `rust` | `format` | `cargo fmt` | `cargo fmt --check` | `direct` | 6 | 2 | 6 | 612 | 0 | 0 |
| `rust` | `format` | `cargo fmt` | `cargo fmt --all --check` | `mixed_unknown` | 5 | 1 | 0 | 0 | 0 | 0 |
| `rust` | `format` | `cargo fmt` | `cargo fmt --all --check` | `direct` | 4 | 3 | 4 | 7,263 | 0 | 0 |
| `rust` | `format` | `cargo fmt` | `cargo fmt` | `direct` | 3 | 1 | 3 | 153 | 0 | 0 |
| `rust` | `format` | `cargo fmt` | `cargo fmt --manifest-path` | `direct` | 3 | 3 | 3 | 262 | 0 | 0 |
| `rust` | `format` | `rustfmt` | `rustfmt --edition --check` | `direct` | 3 | 1 | 3 | 1,890 | 0 | 0 |
| `rust` | `format` | `cargo fmt` | `cargo fmt --all` | `mixed_unknown` | 1 | 1 | 0 | 0 | 0 | 0 |
| `rust` | `format` | `cargo fmt` | `cargo fmt --check --manifest-path` | `direct` | 1 | 1 | 1 | 3,007 | 0 | 0 |
| `rust` | `format` | `cargo fmt` | `cargo fmt --manifest-path` | `mixed_unknown` | 1 | 1 | 0 | 0 | 0 | 0 |
| `rust` | `format` | `rustfmt` | `rustfmt --check` | `direct` | 1 | 1 | 1 | 551 | 0 | 0 |
| `rust` | `format` | `rustfmt` | `rustfmt --edition` | `mixed_unknown` | 1 | 1 | 0 | 0 | 0 | 0 |
| `rust` | `format` | `rustfmt` | `rustfmt --edition --check --config` | `direct` | 1 | 1 | 1 | 102 | 0 | 0 |

## Gated opportunities

| Ecosystem | Operation | Candidate | Saved bytes | Targeted fraction | Both gates |
| --- | --- | --- | --- | --- | --- |
| `python` | `test` | `terse_failure` | 201,438 | 24.2% | yes |
| `node-ts` | `test` | `terse_failure` | 189,392 | 29.8% | yes |
| `go` | `test` | `terse_failure` | 78,603 | 61.0% | no |
| `rust` | `test` | `terse_failure` | 50,524 | 9.4% | no |
| `python` | `compile/build` | `terse_failure` | 6,508 | 62.3% | no |
| `rust` | `type/check` | `terse_failure` | 3,869 | 19.2% | no |
| `rust` | `lint` | `terse_failure` | 3,628 | 51.3% | no |
| `go` | `test` | `aggressive_success` | 3,579 | 10.5% | no |
| `go` | `test` | `conservative_success` | 3,363 | 9.8% | no |
| `node-ts` | `unknown` | `terse_failure` | 2,781 | 42.9% | no |
| `rust` | `lint` | `aggressive_success` | 2,326 | 97.0% | no |
| `node-ts` | `compile/build` | `terse_failure` | 2,286 | 36.4% | no |
| `rust` | `lint` | `conservative_success` | 2,222 | 92.7% | no |
| `rust` | `compile/build` | `aggressive_success` | 1,936 | 33.6% | no |
| `rust` | `compile/build` | `conservative_success` | 1,840 | 31.9% | no |
| `python` | `test` | `aggressive_success` | 1,369 | 0.3% | no |
| `python` | `test` | `conservative_success` | 1,159 | 0.3% | no |
| `rust` | `compile/build` | `terse_failure` | 834 | 2.2% | no |
| `rust` | `type/check` | `aggressive_success` | 476 | 4.0% | no |
| `rust` | `type/check` | `conservative_success` | 452 | 3.8% | no |
| `go` | `format` | `aggressive_success` | 0 | 0.0% | no |
| `go` | `format` | `conservative_success` | 0 | 0.0% | no |
| `go` | `format` | `terse_failure` | 0 | 0.0% | no |
| `go` | `type/check` | `aggressive_success` | 0 | 0.0% | no |
| `go` | `type/check` | `conservative_success` | 0 | 0.0% | no |
| `node-ts` | `compile/build` | `aggressive_success` | 0 | 0.0% | no |
| `node-ts` | `compile/build` | `conservative_success` | 0 | 0.0% | no |
| `node-ts` | `package-script-unknown` | `aggressive_success` | 0 | 0.0% | no |
| `node-ts` | `package-script-unknown` | `conservative_success` | 0 | 0.0% | no |
| `node-ts` | `test` | `aggressive_success` | 0 | 0.0% | no |
| `node-ts` | `test` | `conservative_success` | 0 | 0.0% | no |
| `node-ts` | `type/check` | `terse_failure` | 0 | 0.0% | no |
| `node-ts` | `unknown` | `aggressive_success` | 0 | 0.0% | no |
| `node-ts` | `unknown` | `conservative_success` | 0 | 0.0% | no |
| `other` | `compile/build` | `terse_failure` | 0 | 0.0% | no |
| `other` | `test` | `aggressive_success` | 0 | 0.0% | no |
| `other` | `test` | `conservative_success` | 0 | 0.0% | no |
| `other` | `test` | `terse_failure` | 0 | 0.0% | no |
| `python` | `compile/build` | `aggressive_success` | 0 | 0.0% | no |
| `python` | `compile/build` | `conservative_success` | 0 | 0.0% | no |
| `rust` | `format` | `aggressive_success` | 0 | 0.0% | no |
| `rust` | `format` | `conservative_success` | 0 | 0.0% | no |
| `rust` | `format` | `terse_failure` | 0 | 0.0% | no |
| `rust` | `test` | `aggressive_success` | 0 | 0.0% | no |
| `rust` | `test` | `conservative_success` | 0 | 0.0% | no |

## Syntax-only appearances

| Ecosystem | Operation | Family | Shape | Appearances |
| --- | --- | --- | --- | --- |
| `go` | `compile/build` | `go build` | `go build` | 1 |
| `go` | `format` | `gofmt` | `gofmt` | 121 |
| `go` | `test` | `go test` | `go test` | 128 |
| `node-ts` | `type/check` | `tsc` | `tsc` | 1 |
| `node-ts` | `unknown` | `node` | `node` | 37 |
| `rust` | `compile/build` | `cargo build` | `cargo build` | 10 |
| `rust` | `compile/build` | `rustc` | `rustc` | 4 |
| `rust` | `format` | `cargo fmt` | `cargo fmt` | 126 |
| `rust` | `format` | `rustfmt` | `rustfmt` | 39 |
| `rust` | `lint` | `cargo clippy` | `cargo clippy` | 19 |
| `rust` | `test` | `cargo test` | `cargo test` | 129 |
| `rust` | `type/check` | `cargo check` | `cargo check` | 6 |

## Required counterexamples

| Case | Required behavior |
| --- | --- |
| `warning_bearing_exit_zero` | Retain warning; aggressive success is rejected. |
| `ignored_or_skipped_tests` | Retain test disposition; aggressive success is rejected. |
| `mixed_batch_output` | Keep one outer batch output; do not infer per-member success. |
| `failed_nested_invocation` | Never convert non-authoritative success text into success. |
| `truncated_or_partial_output` | Passthrough; neither candidate is safe. |
| `unknown_exit_status` | Passthrough; text markers alone are insufficient. |
| `panic_linker_race_or_runtime_failure` | Passthrough terse-failure parser output. |

## Limitations

- Token ranges are byte heuristics, not tokenizer or provider usage.
- The report measures captured model-visible payload bytes, not cache misses or dollars.
- Token and byte accounting covers captured payload text; provider prompt/tool-schema wrapper overhead is not reconstructed.
- Output was transformed only in memory and was never executed, replayed, or serialized.
- A future controlled coding-agent A/B study is required before runtime adoption.
