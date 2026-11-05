import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import analyze_codex_commands as analyzer  # noqa: E402


class AnalyzerFixture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.codex_home = self.root / "codex"
        self.sessions = self.codex_home / "sessions"
        self.sessions.mkdir(parents=True)
        self.output_dir = self.root / "report"
        self.counter = 0

    def tearDown(self):
        self.temporary.cleanup()

    @staticmethod
    def session_meta(session_id="private-session", timestamp="2026-10-02T10:00:00Z"):
        return {
            "timestamp": timestamp,
            "type": "session_meta",
            "payload": {
                "session_id": session_id,
                "id": session_id,
                "cwd": "/private/example/project",
            },
        }

    @staticmethod
    def call(
        command,
        call_id="call-1",
        *,
        name="exec_command",
        timestamp="2026-10-02T10:01:00Z",
        raw_arguments=None,
    ):
        arguments = raw_arguments
        if arguments is None:
            arguments = json.dumps(
                {
                    "cmd": command,
                    "workdir": "/private/example/project",
                    "yield_time_ms": 1000,
                }
            )
        return {
            "timestamp": timestamp,
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": name,
                "call_id": call_id,
                "id": f"item-{call_id}",
                "arguments": arguments,
            },
        }

    @staticmethod
    def custom_exec(source, call_id="custom-1", timestamp="2026-10-02T10:02:00Z"):
        return {
            "timestamp": timestamp,
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call",
                "name": "exec",
                "call_id": call_id,
                "id": f"item-{call_id}",
                "input": source,
            },
        }

    @staticmethod
    def output(value, call_id="call-1", timestamp="2026-10-02T10:03:00Z"):
        return {
            "timestamp": timestamp,
            "type": "response_item",
            "payload": {
                "type": "function_call_output",
                "call_id": call_id,
                "id": f"result-{call_id}",
                "output": value,
            },
        }

    @staticmethod
    def response_boundary(
        response_id,
        *,
        timestamp="2026-10-02T10:03:00Z",
        turn_id="private-turn",
    ):
        return {
            "timestamp": timestamp,
            "type": "token_usage_record",
            "payload": {
                "response_id": response_id,
                "turn_id": turn_id,
                "usage": {"input_tokens": 1},
            },
        }

    @staticmethod
    def user_message(timestamp="2026-10-02T10:03:00Z"):
        return {
            "timestamp": timestamp,
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "private prompt"}],
            },
        }

    @staticmethod
    def assistant_reasoning(timestamp="2026-10-02T10:03:00Z"):
        return {
            "timestamp": timestamp,
            "type": "response_item",
            "payload": {
                "type": "reasoning",
                "summary": [{"type": "summary_text", "text": "private reasoning"}],
            },
        }

    @staticmethod
    def turn_context(
        turn_id="private-new-turn",
        timestamp="2026-10-02T10:03:00Z",
    ):
        return {
            "timestamp": timestamp,
            "type": "turn_context",
            "payload": {"turn_id": turn_id, "cwd": "/private/example/project"},
        }

    @staticmethod
    def non_shell_call(
        name="apply_patch",
        call_id="patch-1",
        timestamp="2026-10-02T10:03:00Z",
    ):
        return {
            "timestamp": timestamp,
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call",
                "name": name,
                "call_id": call_id,
                "input": "*** Begin Patch\n*** End Patch\n",
            },
        }

    def write_rollout(
        self,
        events,
        *,
        name=None,
        directory=None,
        raw_suffix=b"",
    ):
        self.counter += 1
        target_dir = directory or self.sessions
        target_dir.mkdir(parents=True, exist_ok=True)
        filename = name or f"rollout-2026-10-02T10-00-00-{self.counter:04d}.jsonl"
        path = target_dir / filename
        with path.open("wb") as handle:
            for event in events:
                handle.write(json.dumps(event, ensure_ascii=False).encode("utf-8") + b"\n")
            handle.write(raw_suffix)
        return path

    def run_analyzer(
        self,
        *,
        since="2026-10-02",
        until="2026-10-02",
        include_archived=False,
        output_dir=None,
        extra=(),
    ):
        target = output_dir or self.output_dir
        argv = [
            "--codex-home",
            str(self.codex_home),
            "--sessions-dir",
            str(self.sessions),
            "--output-dir",
            str(target),
            *extra,
        ]
        if since:
            argv.extend(["--since", since])
        if until:
            argv.extend(["--until", until])
        if include_archived:
            argv.append("--include-archived")
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = analyzer.main(argv)
        self.assertEqual(code, 0, stderr.getvalue())
        report = json.loads((target / "command_frequency_report.json").read_text())
        markdown = (target / "command_frequency_report.md").read_text()
        return report, markdown, stdout.getvalue(), stderr.getvalue()

    @staticmethod
    def family(report, name):
        return next(
            row
            for row in report["command_frequency"]["top_executable_families"]
            if row["family"] == name
        )

    @staticmethod
    def sequence_row(report, identities, length=None):
        length = length or len(identities)
        for row in report["sequence_analysis"]["ranking"][f"family_{length}"]:
            if tuple(item["identity"] for item in row["sequence"]) == tuple(identities):
                return row
        raise AssertionError(f"sequence not found: {identities}")

    def test_extracts_direct_call_correlates_output_and_deduplicates_telemetry(self):
        self.write_rollout(
            [
                self.session_meta(),
                self.call("rg needle src"),
                self.call("rg needle src"),
                self.output("src/file.txt: needle\n"),
                self.output("src/file.txt: needle\n"),
            ]
        )
        report, _, _, _ = self.run_analyzer()
        self.assertEqual(report["coverage"]["shell_tool_invocations"], 1)
        self.assertEqual(report["coverage"]["matched_shell_invocations"], 1)
        self.assertEqual(report["coverage"]["duplicate_request_events"], 1)
        self.assertEqual(report["coverage"]["duplicate_output_events"], 1)
        family = self.family(report, "rg")
        self.assertEqual(family["calls"], 1)
        self.assertEqual(family["output"]["captured_model_visible_bytes"], 21)
        self.assertIsNone(
            report["output_measurement"]["provider_measured_uncached_input_tokens"]
        )

    def test_custom_exec_extracts_structured_nested_tool_call(self):
        source = """
        const result = await tools.exec_command({
          cmd: "python -m pytest -q tests",
          yield_time_ms: 1000,
        });
        text(result);
        """
        self.write_rollout(
            [
                self.session_meta(),
                self.custom_exec(source),
                self.output(
                    "\n".join(["." * 100, "120 passed, 0 failed in 4.25s"]),
                    call_id="custom-1",
                ),
            ]
        )
        report, _, _, _ = self.run_analyzer()
        family = self.family(report, "python -m pytest")
        self.assertEqual(family["calls"], 1)
        self.assertEqual(family["output"]["status_counts"], {"success": 1})
        adapter = next(
            row for row in report["terse_adapters"] if row["candidate_id"] == "pytest_success"
        )
        self.assertGreater(adapter["simulation"]["removed_observed_bytes"], 50)
        self.assertEqual(
            adapter["simulation"]["status"], "measured_on_observed_output"
        )

    def test_batch_forms_count_invocations_without_multiplying_output(self):
        native = {
            "type": "function_call",
            "name": "delayed_seq",
            "call_id": "native-1",
            "id": "item-native-1",
            "arguments": json.dumps({"commands": ["git status", "cargo test"]}),
        }
        self.write_rollout(
            [
                self.session_meta(),
                self.call(
                    "delayed-seq --initial-delay 0 -- 'git status --short' 'rg TODO src'",
                    call_id="plain-1",
                ),
                self.output(
                    "[delayed-seq] command 1/2: succeeded\n"
                    "[delayed-seq] command 2/2: succeeded\n"
                    "[delayed-seq] completed: 2 command(s)\n",
                    call_id="plain-1",
                ),
                self.call(
                    "CODEX_ROUTING_PROXY_VIRTUAL_BATCH=1 delayed-seq --dry-run -- "
                    "'go test ./...' 'git diff'",
                    call_id="proxy-1",
                ),
                self.output(
                    '{"event":"dry-run","index":1}\n{"event":"dry-run","index":2}\n',
                    call_id="proxy-1",
                ),
                {
                    "timestamp": "2026-10-02T10:04:00Z",
                    "type": "response_item",
                    "payload": native,
                },
                self.output(
                    "[delayed-seq] command 1/2: succeeded\n"
                    "[delayed-seq] command 2/2: succeeded\n"
                    "[delayed-seq] completed: 2 command(s)\n",
                    call_id="native-1",
                ),
            ]
        )
        report, _, _, _ = self.run_analyzer()
        self.assertEqual(report["coverage"]["shell_tool_invocations"], 3)
        self.assertEqual(report["coverage"]["requested_underlying_subcommands"], 6)
        self.assertEqual(
            report["batching"]["execution_forms"],
            {
                "native_batch": 1,
                "proxy_batch": 1,
                "shell_batch": 1,
            },
        )
        self.assertEqual(report["batching"]["dry_run_batch_invocations"], 1)
        self.assertEqual(report["batching"]["dry_run_subcommands"], 2)
        self.assertEqual(self.family(report, "git")["output"]["matched_output_count"], 0)
        self.assertEqual(self.family(report, "rg")["output"]["matched_output_count"], 0)
        observed = report["batching"]["observed_subcommand_outcomes"]
        self.assertEqual(observed["succeeded"], 4)
        self.assertEqual(observed["unknown"], 2)
        self.assertEqual(
            report["output_measurement"]["observed_model_visible_output"][
                "matched_output_count"
            ],
            3,
        )

    def test_sequence_identity_merges_batch_and_same_response_direct_calls(self):
        self.write_rollout(
            [
                self.session_meta(),
                self.call(
                    "delayed-seq --initial-delay 0 -- 'git status' 'cargo test'",
                    call_id="batch",
                ),
                self.output(
                    "[delayed-seq] command 1/2: succeeded\n"
                    "[delayed-seq] command 2/2: succeeded\n"
                    "[delayed-seq] completed: 2 command(s)\n",
                    call_id="batch",
                ),
                self.response_boundary("response-batch"),
                self.call("git status", call_id="direct-a"),
                self.call("cargo test", call_id="direct-b"),
                self.output("clean\n", call_id="direct-a"),
                self.output("test result: ok\n", call_id="direct-b"),
                self.response_boundary("response-direct"),
            ]
        )
        report, _, _, _ = self.run_analyzer()
        sequence = report["sequence_analysis"]
        row = self.sequence_row(report, ("git", "cargo test"))
        self.assertEqual(row["total"], 2)
        self.assertEqual(row["explicit_batch"], 1)
        self.assertEqual(row["separate_direct_calls"], 1)
        self.assertEqual(row["distinct_sessions_by_mode"]["explicit_batch"], 1)
        self.assertEqual(row["distinct_sessions_by_mode"]["separate_direct_calls"], 1)
        self.assertEqual(row["same_response_inferred"], 1)
        self.assertTrue(row["cross_mode_repeat"])
        self.assertEqual(
            sequence["response_boundary_evidence"]["same_response_inferred"],
            1,
        )
        self.assertEqual(
            sequence["response_boundary_evidence"]["separate_response_observed"],
            1,
        )

    def test_triple_sequence_merges_explicit_direct_and_mixed_modes(self):
        commands = ("cargo fmt --check", "cargo test", "cargo clippy")
        self.write_rollout(
            [
                self.session_meta(),
                self.call(
                    "delayed-seq --initial-delay 0 -- "
                    "'cargo fmt --check' 'cargo test' 'cargo clippy'",
                    call_id="explicit",
                ),
                self.output(
                    "[delayed-seq] command 1/3: succeeded\n"
                    "[delayed-seq] command 2/3: succeeded\n"
                    "[delayed-seq] command 3/3: succeeded\n",
                    call_id="explicit",
                ),
                self.user_message(),
                self.call(commands[0], call_id="direct-a"),
                self.output(
                    {"stdout": "format ok\n", "exit_code": 0},
                    call_id="direct-a",
                ),
                self.call(commands[1], call_id="direct-b"),
                self.output("test result: ok\n", call_id="direct-b"),
                self.call(commands[2], call_id="direct-c"),
                self.output(
                    {"stdout": "lint ok\n", "exit_code": 0},
                    call_id="direct-c",
                ),
                self.response_boundary("direct-response"),
                self.user_message(timestamp="2026-10-02T10:04:00Z"),
                self.call(
                    "delayed-seq --initial-delay 0 -- "
                    "'cargo fmt --check' 'cargo test'",
                    call_id="mixed-batch",
                ),
                self.output(
                    "[delayed-seq] command 1/2: succeeded\n"
                    "[delayed-seq] command 2/2: succeeded\n",
                    call_id="mixed-batch",
                ),
                self.call(commands[2], call_id="mixed-direct"),
                self.output(
                    {"stdout": "lint ok\n", "exit_code": 0},
                    call_id="mixed-direct",
                ),
            ]
        )
        report, _, _, _ = self.run_analyzer()
        row = self.sequence_row(
            report,
            ("cargo fmt", "cargo test", "cargo clippy"),
        )
        self.assertEqual(row["total"], 3)
        self.assertEqual(row["explicit_batch"], 1)
        self.assertEqual(row["separate_direct_calls"], 1)
        self.assertEqual(row["mixed"], 1)
        self.assertEqual(row["unknown"], 0)
        self.assertEqual(row["batched_fraction"], 0.5)
        self.assertEqual(row["batched_fraction_denominator"], 2)
        self.assertEqual(row["unbatched_same_response_count"], 1)
        self.assertEqual(row["unbatched_same_response_fraction"], 0.5)
        self.assertEqual(row["unbatched_same_response_denominator"], 2)
        self.assertEqual(row["requested_subcommands"], 9)
        self.assertEqual(row["confirmed_executed_subcommands"], 9)
        self.assertEqual(row["unknown_subcommand_statuses"], 0)
        self.assertEqual(row["matched_invocations"], 6)
        self.assertEqual(row["invocation_occurrences"], 6)
        self.assertEqual(
            row["within_session_mode_overlap"][
                "explicit_and_direct_session_instances"
            ],
            1,
        )
        self.assertTrue(row["cross_mode_same_response_repeat"])
        self.assertIn(
            row,
            report["sequence_analysis"]["cross_mode_same_response_repeats"][
                "family_3"
            ],
        )
        self.assertEqual(
            row["by_mode"]["separate_direct_calls"]["same_response_inferred"],
            1,
        )
        self.assertEqual(
            row["by_mode"]["separate_direct_calls"]["intervening_events"],
            {"tool_output_only": 2},
        )

    def test_response_ids_override_equal_timestamps_and_physical_order_wins(self):
        same_time = "2026-10-02T10:01:00Z"
        self.write_rollout(
            [
                self.session_meta(),
                self.call("git status", call_id="a1", timestamp=same_time),
                self.output("clean\n", call_id="a1", timestamp=same_time),
                self.response_boundary("response-one", timestamp=same_time),
                self.call("cargo test", call_id="b1", timestamp=same_time),
                self.output("test result: ok\n", call_id="b1", timestamp=same_time),
                self.response_boundary("response-two", timestamp=same_time),
                self.call("git status", call_id="a2", timestamp=same_time),
                self.output("clean\n", call_id="a2", timestamp=same_time),
                self.response_boundary("response-three", timestamp=same_time),
                self.call("cargo test", call_id="b2", timestamp=same_time),
                self.output("test result: ok\n", call_id="b2", timestamp=same_time),
                self.response_boundary("response-four", timestamp=same_time),
            ]
        )
        report, _, _, _ = self.run_analyzer()
        row = self.sequence_row(report, ("git", "cargo test"))
        self.assertEqual(row["separate_direct_calls"], 2)
        self.assertEqual(row["same_response_inferred"], 0)
        self.assertEqual(
            report["sequence_analysis"]["response_boundary_evidence"][
                "separate_response_observed"
            ],
            3,
        )
        self.assertEqual(
            report["sequence_analysis"]["elapsed_time_histogram"]["lt_1s"],
            3,
        )

    def test_user_turn_breaks_sequence_but_output_and_reasoning_are_retained(self):
        self.write_rollout(
            [
                self.session_meta(),
                self.call("git status", call_id="a"),
                self.output("clean\n", call_id="a"),
                self.assistant_reasoning(),
                self.call("cargo test", call_id="b"),
                self.output("test result: ok\n", call_id="b"),
                self.call("git status", call_id="c"),
                self.output("clean\n", call_id="c"),
                self.assistant_reasoning(timestamp="2026-10-02T10:03:30Z"),
                self.call("cargo test", call_id="d"),
                self.output("test result: ok\n", call_id="d"),
                self.user_message(timestamp="2026-10-02T10:04:00Z"),
                self.call("rg needle src", call_id="e"),
                self.output("needle\n", call_id="e"),
            ]
        )
        report, _, _, _ = self.run_analyzer()
        sequence = report["sequence_analysis"]
        row = self.sequence_row(report, ("git", "cargo test"))
        self.assertEqual(row["separate_direct_calls"], 2)
        self.assertEqual(
            row["intervening_events"]["assistant_decision_observed"],
            2,
        )
        self.assertEqual(sequence["coverage"]["hard_boundaries"], 1)
        self.assertEqual(
            sequence["intervening_event_histogram"][
                "user_turn_or_session_boundary"
            ],
            1,
        )
        self.assertEqual(sequence["coverage"]["occurrences_by_length"]["2"], 3)

    def test_turn_context_creates_a_hard_sequence_boundary(self):
        self.write_rollout(
            [
                self.session_meta(),
                self.call("git status", call_id="before"),
                self.output("clean\n", call_id="before"),
                self.turn_context(),
                self.call("cargo test", call_id="after"),
                self.output("test result: ok\n", call_id="after"),
            ]
        )
        report, _, _, _ = self.run_analyzer()
        sequence = report["sequence_analysis"]
        self.assertEqual(sequence["coverage"]["hard_boundaries"], 1)
        self.assertEqual(sequence["ranking"]["family_2"], [])
        self.assertEqual(
            sequence["intervening_event_histogram"][
                "user_turn_or_session_boundary"
            ],
            1,
        )

    def test_failed_direct_retry_sequence_is_not_a_static_candidate(self):
        def pair(suffix, failed, timestamp):
            return [
                self.call(
                    "cargo test",
                    call_id=f"a-{suffix}",
                    timestamp=timestamp,
                ),
                self.output(
                    "test result: failed\n" if failed else "test result: ok\n",
                    call_id=f"a-{suffix}",
                    timestamp=timestamp,
                ),
                self.call(
                    "cargo clippy",
                    call_id=f"b-{suffix}",
                    timestamp=timestamp,
                ),
                self.output(
                    "clean\n",
                    call_id=f"b-{suffix}",
                    timestamp=timestamp,
                ),
            ]

        self.write_rollout(
            [
                self.session_meta(),
                *pair("one", True, "2026-10-02T10:01:00Z"),
                self.response_boundary("response-one"),
                self.user_message(timestamp="2026-10-02T10:02:00Z"),
                *pair("two", False, "2026-10-02T10:03:00Z"),
                self.response_boundary("response-two"),
            ]
        )
        report, _, _, _ = self.run_analyzer()
        row = self.sequence_row(report, ("cargo test", "cargo clippy"))
        self.assertEqual(row["observed_status"]["failed"], 1)
        self.assertEqual(row["candidate_category"], "decision_dependent")

    def test_overlapping_lengths_and_edit_interruptions_are_counted(self):
        self.write_rollout(
            [
                self.session_meta(),
                self.call("rg needle src", call_id="a"),
                self.output("needle\n", call_id="a"),
                self.call("git status", call_id="b"),
                self.output("clean\n", call_id="b"),
                self.non_shell_call(),
                self.call("cargo test", call_id="c"),
                self.output("test result: ok\n", call_id="c"),
                self.call("pytest -q", call_id="d"),
                self.output("1 passed\n", call_id="d"),
                self.user_message(timestamp="2026-10-02T10:03:30Z"),
                self.call("rg needle src", call_id="e"),
                self.output("needle\n", call_id="e"),
                self.call("git status", call_id="f"),
                self.output("clean\n", call_id="f"),
                self.non_shell_call(call_id="patch-2"),
                self.call("cargo test", call_id="g"),
                self.output("test result: ok\n", call_id="g"),
                self.call("pytest -q", call_id="h"),
                self.output("1 passed\n", call_id="h"),
                self.response_boundary("response-all"),
            ]
        )
        report, _, _, _ = self.run_analyzer()
        sequence = report["sequence_analysis"]
        self.assertEqual(
            sequence["coverage"]["occurrences_by_length"],
            {"2": 6, "3": 4, "4": 2},
        )
        self.assertEqual(
            sequence["coverage"]["non_overlapping_occurrences_by_length"],
            {"2": 4, "3": 2, "4": 2},
        )
        pair = self.sequence_row(report, ("git", "cargo test"))
        self.assertEqual(pair["total"], 2)
        self.assertEqual(pair["intervening_events"]["edit_or_other_tool"], 2)
        self.assertEqual(pair["same_response_inferred"], 1)
        quadruple = self.sequence_row(
            report,
            ("rg", "git", "cargo test", "pytest"),
        )
        self.assertEqual(quadruple["same_response_inferred"], 1)
        transition = next(
            row
            for row in sequence["transitions"]["rows"]
            if row["first"] == "git" and row["second"] == "cargo test"
        )
        self.assertEqual(transition["count"], 2)
        self.assertGreater(
            transition["next_command_exclusive_output_bytes"],
            0,
        )
        self.assertGreaterEqual(
            transition["denominator"],
            transition["count"],
        )

    def test_mixed_and_cross_batch_windows_are_not_conflated(self):
        self.write_rollout(
            [
                self.session_meta(),
                self.call(
                    "delayed-seq --initial-delay 0 -- 'git status' 'rg needle src'",
                    call_id="batch-one",
                ),
                self.output(
                    "[delayed-seq] command 1/2: succeeded\n"
                    "[delayed-seq] command 2/2: succeeded\n",
                    call_id="batch-one",
                ),
                self.call("cargo test", call_id="direct"),
                self.output("test result: ok\n", call_id="direct"),
                self.call(
                    "delayed-seq --initial-delay 0 -- 'pytest -q' 'go test ./...'",
                    call_id="batch-two",
                ),
                self.output(
                    "[delayed-seq] command 1/2: succeeded\n"
                    "[delayed-seq] command 2/2: succeeded\n",
                    call_id="batch-two",
                ),
                self.response_boundary("response-one"),
                self.call(
                    "delayed-seq --initial-delay 0 -- 'git status' 'rg needle src'",
                    call_id="batch-three",
                ),
                self.output(
                    "[delayed-seq] command 1/2: succeeded\n"
                    "[delayed-seq] command 2/2: succeeded\n",
                    call_id="batch-three",
                ),
                self.call("cargo test", call_id="direct-two"),
                self.output("test result: ok\n", call_id="direct-two"),
                self.call(
                    "delayed-seq --initial-delay 0 -- 'pytest -q' 'go test ./...'",
                    call_id="batch-four",
                ),
                self.output(
                    "[delayed-seq] command 1/2: succeeded\n"
                    "[delayed-seq] command 2/2: succeeded\n",
                    call_id="batch-four",
                ),
                self.user_message(timestamp="2026-10-02T10:05:00Z"),
                self.call(
                    "delayed-seq --initial-delay 0 -- 'cargo clippy' 'go test ./...'",
                    call_id="batch-five",
                ),
                self.output(
                    "[delayed-seq] command 1/2: succeeded\n"
                    "[delayed-seq] command 2/2: succeeded\n",
                    call_id="batch-five",
                ),
                self.call(
                    "delayed-seq --initial-delay 0 -- 'git status' 'pytest -q'",
                    call_id="batch-six",
                ),
                self.output(
                    "[delayed-seq] command 1/2: succeeded\n"
                    "[delayed-seq] command 2/2: succeeded\n",
                    call_id="batch-six",
                ),
                self.call(
                    "delayed-seq --initial-delay 0 -- 'cargo clippy' 'go test ./...'",
                    call_id="batch-seven",
                ),
                self.output(
                    "[delayed-seq] command 1/2: succeeded\n"
                    "[delayed-seq] command 2/2: succeeded\n",
                    call_id="batch-seven",
                ),
                self.call(
                    "delayed-seq --initial-delay 0 -- 'git status' 'pytest -q'",
                    call_id="batch-eight",
                ),
                self.output(
                    "[delayed-seq] command 1/2: succeeded\n"
                    "[delayed-seq] command 2/2: succeeded\n",
                    call_id="batch-eight",
                ),
            ]
        )
        report, _, _, _ = self.run_analyzer()
        mixed = self.sequence_row(report, ("rg", "cargo test"))
        self.assertEqual(mixed["mixed"], 2)
        self.assertEqual(mixed["explicit_batch"], 0)
        self.assertEqual(mixed["separate_direct_calls"], 0)
        cross_batch = self.sequence_row(report, ("go test", "git"))
        self.assertEqual(cross_batch["unknown"], 3)
        self.assertEqual(
            cross_batch["unknown_reasons"],
            {"multiple_batch_boundaries": 3},
        )
        self.assertEqual(cross_batch["mixed"], 0)

    def test_batch_requested_versus_confirmed_execution_is_conservative(self):
        self.write_rollout(
            [
                self.session_meta(),
                self.call(
                    "delayed-seq --initial-delay 0 -- 'git status' 'rg x src' 'cargo test'",
                    call_id="one-failure",
                ),
                self.output(
                    "[delayed-seq] command 1/3: succeeded\n"
                    "[delayed-seq] command 2/3: failed\n"
                    "[delayed-seq] failed: command 3/3 not started\n",
                    call_id="one-failure",
                ),
                self.call(
                    "delayed-seq --dry-run -- 'go test ./...' 'pytest -q' 'git diff'",
                    call_id="dry",
                ),
                self.output(
                    '{"event":"dry-run","index":1}\n'
                    '{"event":"dry-run","index":2}\n'
                    '{"event":"dry-run","index":3}\n',
                    call_id="dry",
                ),
                self.call(
                    "delayed-seq --initial-delay 0 -- 'npm test' 'git status'",
                    call_id="missing",
                ),
            ]
        )
        report, _, _, _ = self.run_analyzer()
        coverage = report["sequence_analysis"]["coverage"]
        self.assertEqual(coverage["requested_batch_subcommands"], 8)
        self.assertEqual(coverage["confirmed_executed_batch_subcommands"], 2)
        self.assertEqual(coverage["unknown_batch_subcommand_statuses"], 6)

    def test_timeout_cancellation_and_malformed_wrapper_remain_unknown(self):
        commands = "'git status' 'cargo test'"
        self.write_rollout(
            [
                self.session_meta(),
                self.call(
                    f"delayed-seq --initial-delay 0 -- {commands}",
                    call_id="timeout",
                ),
                self.output(
                    "[delayed-seq] command 1/2: timed out\n",
                    call_id="timeout",
                ),
                self.call(
                    f"delayed-seq --initial-delay 0 -- {commands}",
                    call_id="malformed",
                    raw_arguments="{not-json",
                ),
                self.call(
                    f"delayed-seq --initial-delay 0 -- {commands}",
                    call_id="cancelled",
                ),
                self.output(
                    "[delayed-seq] cancelled before completion\n",
                    call_id="cancelled",
                ),
            ]
        )
        report, markdown, _, _ = self.run_analyzer()
        sequence = report["sequence_analysis"]
        row = self.sequence_row(report, ("git", "cargo test"))
        self.assertEqual(row["explicit_batch"], 2)
        self.assertEqual(row["confirmed_executed_occurrences"], 0)
        self.assertEqual(row["requested_only_occurrences"], 2)
        self.assertEqual(row["requested_subcommands"], 4)
        self.assertEqual(row["confirmed_executed_subcommands"], 0)
        self.assertEqual(row["unknown_subcommand_statuses"], 4)
        self.assertEqual(row["observed_status"]["failed"], 1)
        self.assertEqual(row["observed_status"]["unknown"], 1)
        self.assertEqual(row["candidate_category"], "decision_dependent")
        self.assertEqual(sequence["coverage"]["requested_batch_subcommands"], 4)
        self.assertEqual(
            sequence["coverage"]["confirmed_executed_batch_subcommands"],
            0,
        )
        self.assertEqual(sequence["coverage"]["hard_boundaries"], 1)
        sequence_markdown = (
            self.output_dir / "command_sequence_report.md"
        ).read_text()
        candidate = next(
            row
            for row in sequence["batching_candidates"]
            if row["sequence"] == ["git", "cargo test"]
        )
        self.assertTrue(candidate["shape_examples"])
        shape_example = " → ".join(
            f"`{value}`"
            for value in candidate["shape_examples"][0]["shape_sequence"]
        )
        self.assertIn("Requested-only occurrences", sequence_markdown)
        self.assertIn("Subcommands req/conf/unknown", sequence_markdown)
        self.assertIn("Sanitized shape sample", sequence_markdown)
        self.assertIn(shape_example, sequence_markdown)

    def test_ambiguous_custom_bundle_is_excluded_from_ordered_sequences(self):
        source = """
        const results = await Promise.all([
          tools.exec_command({cmd: "git status"}),
          tools.exec_command({cmd: "cargo test"}),
        ]);
        text(results);
        """
        self.write_rollout(
            [
                self.session_meta(),
                self.call("git status", call_id="before-bundle"),
                self.output("clean\n", call_id="before-bundle"),
                self.custom_exec(source),
                self.output("combined private output\n", call_id="custom-1"),
                self.call("cargo test", call_id="after-bundle"),
                self.output("test result: ok\n", call_id="after-bundle"),
            ]
        )
        report, markdown, _, _ = self.run_analyzer()
        sequence = report["sequence_analysis"]
        self.assertEqual(
            sequence["coverage"]["ambiguous_ordering_invocations_excluded"],
            2,
        )
        self.assertEqual(sequence["ranking"]["family_2"], [])
        self.assertEqual(sequence["coverage"]["hard_boundaries"], 1)
        combined = markdown + json.dumps(report)
        self.assertNotIn("combined private output", combined)
        self.assertNotIn("Promise.all", combined)

    def test_non_awaited_custom_bundle_is_excluded_from_ordered_sequences(self):
        source = """
        const first = tools.exec_command({cmd: "git status"});
        const second = tools.exec_command({cmd: "cargo test"});
        text(first);
        text(second);
        """
        self.write_rollout(
            [
                self.session_meta(),
                self.custom_exec(source),
                self.output("combined output\n", call_id="custom-1"),
            ]
        )
        report, _, _, _ = self.run_analyzer()
        sequence = report["sequence_analysis"]
        self.assertEqual(
            sequence["coverage"]["ambiguous_ordering_invocations_excluded"],
            2,
        )
        self.assertEqual(sequence["ranking"]["family_2"], [])
        self.assertNotIn("tools.exec_command", json.dumps(report))

    def test_reused_session_ids_across_sources_never_join_sequences(self):
        first = self.codex_home / "sessions" / "2026" / "10" / "02"
        second = self.codex_home / "archived_sessions" / "2026" / "10" / "02"
        self.write_rollout(
            [
                self.session_meta(session_id="shared-session"),
                self.call("git status", call_id="first"),
                self.output("clean\n", call_id="first"),
            ],
            directory=first,
            name="rollout-2026-10-02T10-00-00-first.jsonl",
        )
        self.write_rollout(
            [
                self.session_meta(session_id="shared-session"),
                self.call("cargo test", call_id="second"),
                self.output("test result: ok\n", call_id="second"),
            ],
            directory=second,
            name="rollout-2026-10-02T10-00-00-second.jsonl",
        )
        report, _, _, _ = self.run_analyzer(include_archived=True)
        sequence = report["sequence_analysis"]
        self.assertEqual(sequence["coverage"]["sessions"], 1)
        self.assertEqual(sequence["coverage"]["source_files"], 2)
        self.assertEqual(sequence["coverage"]["reused_session_ids_across_sources"], 1)
        self.assertEqual(sequence["coverage"]["occurrences_by_length"]["2"], 0)

    def test_reused_session_and_call_ids_are_scoped_to_source_file(self):
        self.write_rollout(
            [
                self.session_meta(session_id="shared-session"),
                self.call("git status", call_id="shared-call"),
                self.output("clean\n", call_id="shared-call"),
            ],
            name="rollout-2026-10-02T10-00-00-first.jsonl",
        )
        self.write_rollout(
            [
                self.session_meta(session_id="shared-session"),
                self.call("cargo test", call_id="shared-call"),
                self.output("test result: ok\n", call_id="shared-call"),
            ],
            name="rollout-2026-10-02T10-00-00-second.jsonl",
        )
        report, _, _, _ = self.run_analyzer()
        self.assertEqual(report["coverage"]["shell_tool_invocations"], 2)
        self.assertEqual(report["coverage"]["matched_shell_invocations"], 2)
        self.assertEqual(report["coverage"]["conflicting_request_events"], 0)
        self.assertEqual(self.family(report, "git")["calls"], 1)
        self.assertEqual(self.family(report, "cargo test")["calls"], 1)
        self.assertEqual(
            report["sequence_analysis"]["coverage"]["occurrences_by_length"]["2"],
            0,
        )

    def test_sequence_session_support_distinguishes_reused_source_instances(self):
        events = [
            self.session_meta(session_id="shared-session"),
            self.call(
                "delayed-seq --initial-delay 0 -- 'git status' 'cargo test'",
                call_id="shared-call",
            ),
            self.output(
                "[delayed-seq] command 1/2: succeeded\n"
                "[delayed-seq] command 2/2: succeeded\n",
                call_id="shared-call",
            ),
        ]
        self.write_rollout(
            events,
            name="rollout-2026-10-02T10-00-00-first.jsonl",
        )
        self.write_rollout(
            events,
            name="rollout-2026-10-02T10-00-00-second.jsonl",
        )
        report, _, _, _ = self.run_analyzer()
        row = self.sequence_row(report, ("git", "cargo test"))
        self.assertEqual(row["total"], 2)
        self.assertEqual(row["distinct_sessions"], 1)
        self.assertEqual(row["distinct_session_instances"], 2)
        self.assertEqual(
            report["sequence_analysis"]["coverage"][
                "reused_session_ids_across_sources"
            ],
            1,
        )

    def test_assistant_message_prevents_false_same_response_assignment(self):
        self.write_rollout(
            [
                self.session_meta(),
                self.call("git status", call_id="a1"),
                self.output("clean\n", call_id="a1"),
                self.assistant_reasoning(),
                self.call("cargo test", call_id="b1"),
                self.output("test result: ok\n", call_id="b1"),
                self.response_boundary("ambiguous-later-response"),
                self.call("git status", call_id="a2"),
                self.output("clean\n", call_id="a2"),
                self.assistant_reasoning(timestamp="2026-10-02T10:04:00Z"),
                self.call("cargo test", call_id="b2"),
                self.output("test result: ok\n", call_id="b2"),
                self.response_boundary("another-later-response"),
            ]
        )
        report, _, _, _ = self.run_analyzer()
        row = self.sequence_row(report, ("git", "cargo test"))
        self.assertEqual(row["separate_direct_calls"], 2)
        self.assertEqual(row["same_response_inferred"], 0)
        self.assertEqual(row["by_mode"]["separate_direct_calls"]["same_response_inferred"], 0)
        self.assertGreater(
            report["sequence_analysis"]["response_boundary_evidence"][
                "unknown_response_boundary"
            ],
            0,
        )

    def test_awaited_custom_bundle_preserves_order_as_unknown_packaging(self):
        source = """
        const first = await tools.exec_command({cmd: "git status"});
        const second = await tools.exec_command({cmd: "cargo test"});
        text(first);
        text(second);
        """
        self.write_rollout(
            [
                self.session_meta(),
                self.custom_exec(source, call_id="bundle-one"),
                self.output("bundle result\n", call_id="bundle-one"),
                self.custom_exec(source, call_id="bundle-two"),
                self.output("bundle result\n", call_id="bundle-two"),
            ]
        )
        report, _, _, _ = self.run_analyzer()
        sequence = report["sequence_analysis"]
        self.assertEqual(
            sequence["coverage"]["ambiguous_ordering_invocations_excluded"],
            0,
        )
        row = self.sequence_row(report, ("git", "cargo test"))
        self.assertEqual(row["unknown"], 2)
        self.assertEqual(row["unknown_reasons"], {"custom_outer_bundle": 2})
        self.assertEqual(row["separate_direct_calls"], 0)
        self.assertEqual(row["same_response_inferred"], 0)

    def test_native_proxy_and_shell_batches_merge_to_one_canonical_sequence(self):
        native = {
            "type": "function_call",
            "name": "delayed_seq",
            "call_id": "native",
            "arguments": json.dumps({"commands": ["git status", "cargo test"]}),
        }
        self.write_rollout(
            [
                self.session_meta(),
                {
                    "timestamp": "2026-10-02T10:01:00Z",
                    "type": "response_item",
                    "payload": native,
                },
                self.output(
                    "[delayed-seq] command 1/2: succeeded\n"
                    "[delayed-seq] command 2/2: succeeded\n",
                    call_id="native",
                ),
                self.call(
                    "CODEX_ROUTING_PROXY_VIRTUAL_BATCH=1 "
                    "delayed-seq --initial-delay 0 -- 'git status' 'cargo test'",
                    call_id="proxy",
                ),
                self.output(
                    "[delayed-seq] command 1/2: succeeded\n"
                    "[delayed-seq] command 2/2: succeeded\n",
                    call_id="proxy",
                ),
                self.call(
                    "delayed-seq --initial-delay 0 -- 'git status' 'cargo test'",
                    call_id="shell",
                ),
                self.output(
                    "[delayed-seq] command 1/2: succeeded\n"
                    "[delayed-seq] command 2/2: succeeded\n",
                    call_id="shell",
                ),
            ]
        )
        report, _, _, _ = self.run_analyzer()
        row = self.sequence_row(report, ("git", "cargo test"))
        self.assertEqual(row["explicit_batch"], 3)
        self.assertEqual(
            row["by_mode"]["explicit_batch"]["occurrences"],
            3,
        )

    def test_invalid_record_is_a_hard_physical_boundary(self):
        path = self.sessions / "rollout-invalid-between.jsonl"
        events = [
            self.session_meta(),
            self.call("git status", call_id="a"),
            self.output("clean\n", call_id="a"),
            self.call("cargo test", call_id="b"),
            self.output("test result: ok\n", call_id="b"),
        ]
        with path.open("wb") as handle:
            for index, event in enumerate(events):
                if index == 2:
                    handle.write(b"{bad-json\n")
                handle.write(json.dumps(event).encode("utf-8") + b"\n")
        report, _, _, _ = self.run_analyzer()
        sequence = report["sequence_analysis"]
        self.assertEqual(sequence["coverage"]["hard_boundaries"], 1)
        self.assertEqual(
            sequence["coverage"]["timeline_event_kinds"]["unknown"],
            1,
        )
        self.assertEqual(sequence["ranking"]["family_2"], [])

    def test_replayed_call_and_output_ids_do_not_inflate_sequence_windows(self):
        self.write_rollout(
            [
                self.session_meta(),
                self.call("git status", call_id="a"),
                self.output("clean\n", call_id="a"),
                self.call("cargo test", call_id="b"),
                self.output("test result: ok\n", call_id="b"),
                self.call("git status", call_id="a"),
                self.output("clean\n", call_id="a"),
                self.call("cargo test", call_id="b"),
                self.output("test result: ok\n", call_id="b"),
                self.response_boundary("response-one"),
            ]
        )
        report, _, _, _ = self.run_analyzer()
        sequence = report["sequence_analysis"]
        self.assertEqual(report["coverage"]["duplicate_request_events"], 2)
        self.assertEqual(report["coverage"]["duplicate_output_events"], 2)
        self.assertEqual(sequence["coverage"]["occurrences_by_length"]["2"], 1)
        self.assertEqual(
            sequence["coverage"]["non_overlapping_occurrences_by_length"]["2"],
            1,
        )
        self.assertEqual(sequence["ranking"]["family_2"], [])

    def test_opaque_shell_forms_are_not_misattributed(self):
        self.write_rollout(
            [
                self.session_meta(),
                self.call("rg first src | head -20", call_id="pipe"),
                self.output("first\n", call_id="pipe"),
                self.call(
                    "TOKEN=super-secret-value rg x src",
                    call_id="assignment",
                ),
                self.output("super-secret-output\n", call_id="assignment"),
            ]
        )
        report, markdown, _, _ = self.run_analyzer()
        self.assertEqual(self.family(report, "<opaque>")["calls"], 1)
        self.assertEqual(report["coverage"]["opaque_subcommands"], 1)
        self.assertEqual(report["coverage"]["partial_syntactic_subcommands"], 1)
        self.assertEqual(report["coverage"]["high_confidence_single_subcommands"], 1)
        self.assertEqual(report["coverage"]["legacy_v1_opaque_subcommands"], 2)
        self.assertEqual(self.family(report, "rg")["output"]["matched_output_count"], 1)
        combined = markdown + json.dumps(report)
        self.assertNotIn("super-secret-value", combined)
        self.assertNotIn("super-secret-output", combined)
        self.assertNotIn("/private/example/project", combined)
        self.assertNotIn("private-session", combined)

    def test_legacy_schema_v2_metrics_are_unchanged_on_frozen_fixture(self):
        self.write_rollout(
            [
                self.session_meta(),
                self.call("cargo fmt --check", call_id="format"),
                self.output("format ok\n", call_id="format"),
                self.call("cargo test", call_id="test"),
                self.output("test result: ok. 3 passed\n", call_id="test"),
                self.call("rg x src | head -1", call_id="opaque"),
                self.output("x\n", call_id="opaque"),
                self.non_shell_call(),
            ]
        )
        report, _, _, _ = self.run_analyzer()
        self.assertEqual(
            {
                "discovered_files": report["coverage"]["discovered_files"],
                "processed_files": report["coverage"]["processed_files"],
                "shell_tool_invocations": report["coverage"][
                    "shell_tool_invocations"
                ],
                "requested_underlying_subcommands": report["coverage"][
                    "requested_underlying_subcommands"
                ],
                "matched_shell_invocations": report["coverage"][
                    "matched_shell_invocations"
                ],
                "high_confidence_single_subcommands": report["coverage"][
                    "high_confidence_single_subcommands"
                ],
                "partial_syntactic_subcommands": report["coverage"][
                    "partial_syntactic_subcommands"
                ],
                "opaque_subcommands": report["coverage"]["opaque_subcommands"],
                "legacy_v1_opaque_subcommands": report["coverage"][
                    "legacy_v1_opaque_subcommands"
                ],
                "non_shell_tool_invocations": report["coverage"][
                    "non_shell_tool_invocations"
                ],
                "unmatched_result_records": report["coverage"][
                    "unmatched_result_records"
                ],
            },
            {
                "discovered_files": 1,
                "processed_files": 1,
                "shell_tool_invocations": 3,
                "requested_underlying_subcommands": 3,
                "matched_shell_invocations": 3,
                "high_confidence_single_subcommands": 2,
                "partial_syntactic_subcommands": 1,
                "opaque_subcommands": 1,
                "legacy_v1_opaque_subcommands": 1,
                "non_shell_tool_invocations": 1,
                "unmatched_result_records": 0,
            },
        )
        self.assertEqual(
            report["batching"]["requested_subcommands"],
            3,
        )
        self.assertEqual(
            report["batching"]["observed_subcommand_outcomes"],
            {"succeeded": 1, "failed": 0, "unknown": 2},
        )
        self.assertEqual(
            report["opaque_attribution"]["summary"]["requested_commands"],
            3,
        )

    def test_opaque_reason_taxonomy_and_quoted_operators(self):
        cases = {
            "rg x src | head -20": "shell_pipeline",
            "git status && cargo test": "boolean_chain",
            "git status; cargo test": "command_sequence",
            "git status 2>&1": "redirect_or_heredoc",
            "cat <<EOF\nsecret\nEOF": "redirect_or_heredoc",
            "(cd src && pytest)": "subshell_or_group",
            "TOKEN=secret cargo test": "environment_assignment",
            'rg "$TOKEN" src': "variable_or_command_expansion",
            "git status\ncargo test": "multiline_script",
            "rg 'unterminated": "unsupported_quote_or_lexer",
            'for x in one two; do echo "$x"; done': "shell_function_or_control_flow",
            "# comment only": "unknown_or_other",
            "rg x\x00src": "null_byte_or_invalid",
        }
        for command, expected in cases.items():
            with self.subTest(reason=expected):
                analysis = analyzer.analyze_shell_command(command)
                self.assertEqual(analysis.opaque_reason, expected)

        for command in (
            "rg 'a|b' src",
            'rg "a&&b" src',
            "rg 'a;b' src",
            "rg 'a>b' src",
            "rg 'a$b' src",
            r"rg a\|b src",
            "rg x src # ignored && secret",
        ):
            with self.subTest(literal_operator=command):
                analysis = analyzer.analyze_shell_command(command)
                self.assertEqual(analysis.confidence, "high")
                self.assertEqual(analysis.family, "rg")

        oversized = analyzer.analyze_shell_command("x" * (1024 * 1024 + 1))
        self.assertEqual(oversized.confidence, "opaque")
        self.assertEqual(oversized.opaque_reason, "null_byte_or_invalid")

    def test_simple_compound_forms_are_syntax_only_not_execution_claims(self):
        cases = {
            "git status && cargo test": ["git", "cargo test"],
            "rg x src | head -20": ["rg", "head"],
            "cd src; pytest": ["cd", "pytest"],
            "git status 2>&1": ["git"],
        }
        for command, expected_families in cases.items():
            with self.subTest(command_shape=expected_families):
                analysis = analyzer.analyze_shell_command(command)
                self.assertEqual(analysis.confidence, "partial")
                self.assertEqual(
                    [segment.family for segment in analysis.segments],
                    expected_families,
                )
                self.assertTrue(
                    all(segment.confidence == "partial" for segment in analysis.segments)
                )

        for command in (
            'echo "$(secret-command)"',
            "echo `secret-command`",
            "if true; then secret-command; fi",
            "cat <<EOF\nsecret-command\nEOF",
            "(secret-command)",
            "{ secret-command; }",
            "PATH=/private/bin cargo test",
        ):
            with self.subTest(uncertain_shape=command.split()[0]):
                analysis = analyzer.analyze_shell_command(command)
                self.assertNotEqual(analysis.confidence, "high")
                self.assertFalse(analysis.segments)

    def test_validated_wrappers_and_benign_assignments_recover_single_commands(self):
        cases = {
            "MODE=test cargo test": "cargo test",
            "env MODE=test rg needle src": "rg",
            "command cargo test": "cargo test",
            "timeout 5s cargo test": "cargo test",
        }
        for command, expected_family in cases.items():
            with self.subTest(wrapper=command.split()[0]):
                analysis = analyzer.analyze_shell_command(command)
                self.assertEqual(analysis.confidence, "high")
                self.assertEqual(analysis.family, expected_family)
                self.assertFalse(analysis.segments)

        active_analysis = analyzer.analyze_shell_command("MODE=test cargo test")
        self.assertEqual(active_analysis.opaque_reason, "environment_assignment")
        self.assertTrue(active_analysis.leading_assignment)
        env_analysis = analyzer.analyze_shell_command("env MODE=test rg needle src")
        self.assertEqual(env_analysis.wrapper, "env")
        self.assertTrue(env_analysis.leading_assignment)

        for command in (
            "PATH=/private/bin cargo test",
            "env -S 'cargo test'",
            "command -v cargo",
            "command MODE=test cargo test",
            "timeout --signal cargo test",
            "timeout 5s MODE=test cargo test",
        ):
            with self.subTest(unsafe_wrapper=command.split()[0]):
                analysis = analyzer.analyze_shell_command(command)
                self.assertNotEqual(analysis.confidence, "high")

    def test_composite_output_is_not_multiplied_or_attributed_to_segments(self):
        self.write_rollout(
            [
                self.session_meta(),
                self.call("rg x src | head -20", call_id="pipeline"),
                self.output("pipeline-secret-output\n", call_id="pipeline"),
                self.call("MODE=test cargo test", call_id="assignment"),
                self.output(
                    "test result: ok. 12 passed\n",
                    call_id="assignment",
                ),
            ]
        )
        report, markdown, _, _ = self.run_analyzer()
        adapter = next(
            row
            for row in report["terse_adapters"]
            if row["candidate_id"] == "rust_test_success"
        )
        self.assertEqual(adapter["calls"], 1)
        self.assertEqual(adapter["matched_output_count"], 1)
        self.assertEqual(self.family(report, "<opaque>")["output"]["matched_output_count"], 0)
        self.assertEqual(
            self.family(report, "cargo test")["output"]["matched_output_count"], 1
        )
        attribution = report["opaque_attribution"]
        self.assertEqual(
            attribution["summary"]["still_unattributable_output_bytes"],
            len("pipeline-secret-output\n"),
        )
        self.assertEqual(
            attribution["syntactic_segments"]["occurrence_count"], 2
        )
        combined = markdown + json.dumps(report)
        self.assertNotIn("pipeline-secret-output", combined)
        self.assertNotIn("test result: ok", combined)

    def test_diagnostics_are_versioned_additive_and_private(self):
        self.write_rollout(
            [
                self.session_meta(),
                self.call(
                    "SECRET_TOKEN=top-secret rg x /private/path | head -1",
                    call_id="private-shape",
                ),
                self.output("private output excerpt\n", call_id="private-shape"),
            ]
        )
        report, markdown, stdout, stderr = self.run_analyzer(
            extra=("--fingerprint-salt", "private-test-salt")
        )
        diagnostics_path = self.output_dir / "opaque_command_diagnostics.json"
        diagnostics_markdown_path = self.output_dir / "opaque_command_diagnostics.md"
        diagnostics = json.loads(diagnostics_path.read_text())
        diagnostics_markdown = diagnostics_markdown_path.read_text()
        sequence = json.loads(
            (self.output_dir / "command_sequence_report.json").read_text()
        )
        sequence_markdown = (
            self.output_dir / "command_sequence_report.md"
        ).read_text()
        self.assertEqual(report["schema_version"], 3)
        self.assertIn("opaque_attribution", report)
        self.assertIn("sequence_analysis", report)
        self.assertEqual(diagnostics["schema_version"], 3)
        self.assertEqual(sequence["schema_version"], 1)
        self.assertEqual(sequence["parent_schema_version"], 3)
        self.assertEqual(
            sequence["sequence_analysis"],
            report["sequence_analysis"],
        )
        self.assertEqual(
            diagnostics["summary"]["requested_commands"],
            report["coverage"]["requested_underlying_subcommands"],
        )
        self.assertEqual(
            sum(row["requested_commands"] for row in diagnostics["reasons"]),
            report["coverage"]["legacy_v1_opaque_subcommands"],
        )
        self.assertTrue(
            diagnostics["reconciliation"]["reconciles_to_opaque_subcommands"]
        )
        self.assertEqual(self.output_dir.stat().st_mode & 0o777, 0o700)
        for path in (
            self.output_dir / "command_frequency_report.md",
            self.output_dir / "command_frequency_report.json",
            diagnostics_path,
            diagnostics_markdown_path,
            self.output_dir / "command_sequence_report.md",
            self.output_dir / "command_sequence_report.json",
        ):
            self.assertTrue(path.is_file())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        combined = (
            markdown
            + json.dumps(report)
            + diagnostics_markdown
            + json.dumps(diagnostics)
            + json.dumps(sequence)
            + stdout
            + stderr
        )
        for secret in (
            "top-secret",
            "/private/path",
            "private output excerpt",
            "private-session",
            "/private/example/project",
        ):
            self.assertNotIn(secret, combined)
        self.assertIn("Sequence Markdown:", stdout)
        self.assertIn("Sequence JSON:", stdout)
        self.assertIn("## Edge evidence", sequence_markdown)
        self.assertIn("### Response-boundary evidence", sequence_markdown)
        self.assertIn("## Observed command transitions", sequence_markdown)

    def test_ambiguous_and_unmatched_outputs_are_reported_conservatively(self):
        self.write_rollout(
            [
                self.session_meta(),
                self.call("git status --short", call_id="ambiguous"),
                self.output("one\n", call_id="ambiguous"),
                self.output("two\n", call_id="ambiguous"),
                self.output("orphan\n", call_id="missing"),
            ]
        )
        report, _, _, _ = self.run_analyzer()
        self.assertEqual(report["coverage"]["ambiguous_output_events"], 1)
        self.assertEqual(report["coverage"]["unmatched_result_records"], 1)
        self.assertEqual(self.family(report, "git")["output"]["matched_output_count"], 0)

    def test_conflicting_same_call_id_never_pairs_output(self):
        self.write_rollout(
            [
                self.session_meta(),
                self.call("rg first src", call_id="conflict"),
                self.call("rg second src", call_id="conflict"),
                self.output("first\n", call_id="conflict"),
            ]
        )
        report, _, _, _ = self.run_analyzer()
        self.assertEqual(report["coverage"]["conflicting_request_events"], 1)
        self.assertEqual(report["coverage"]["matched_shell_invocations"], 0)
        self.assertEqual(self.family(report, "rg")["output"]["matched_output_count"], 0)

    def test_known_non_shell_tool_results_are_not_called_unmatched_shell_results(self):
        patch_call = {
            "timestamp": "2026-10-02T10:02:00Z",
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call",
                "name": "apply_patch",
                "call_id": "patch-1",
                "input": "*** Begin Patch\n*** End Patch\n",
            },
        }
        patch_output = {
            "timestamp": "2026-10-02T10:03:00Z",
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call_output",
                "call_id": "patch-1",
                "output": "Done\n",
            },
        }
        self.write_rollout([self.session_meta(), patch_call, patch_output])
        report, _, _, _ = self.run_analyzer()
        self.assertEqual(report["coverage"]["non_shell_tool_invocations"], 1)
        self.assertEqual(report["coverage"]["non_shell_result_records"], 1)
        self.assertEqual(report["coverage"]["unmatched_result_records"], 0)

    def test_date_window_is_inclusive_and_applies_to_calls_and_results(self):
        self.write_rollout(
            [
                self.session_meta(timestamp="2026-10-03T00:00:00Z"),
                self.call("rg before src", call_id="before", timestamp="2026-10-01T23:59:59Z"),
                self.output("before\n", call_id="before", timestamp="2026-10-01T23:59:59Z"),
                self.call("rg inside src", call_id="inside", timestamp="2026-10-02T00:00:00Z"),
                self.output("inside\n", call_id="inside", timestamp="2026-10-02T23:59:59Z"),
            ]
        )
        report, _, _, _ = self.run_analyzer()
        self.assertEqual(report["coverage"]["shell_tool_invocations"], 1)
        self.assertEqual(self.family(report, "rg")["calls"], 1)
        self.assertEqual(report["analysis_scope"]["date_window"]["since"], "2026-10-02")

    def test_date_window_skips_old_dated_files_before_file_limit(self):
        old_directory = self.sessions / "2026" / "10" / "01"
        current_directory = self.sessions / "2026" / "10" / "02"
        self.write_rollout(
            [self.session_meta(timestamp="2026-10-01T10:00:00Z"), self.call("rg old src")],
            directory=old_directory,
            name="rollout-2026-10-01T10-00-00-old.jsonl",
        )
        self.write_rollout(
            [self.session_meta(), self.call("rg current src")],
            directory=current_directory,
            name="rollout-2026-10-02T10-00-00-current.jsonl",
        )
        report, _, _, _ = self.run_analyzer(extra=("--max-files", "1"))
        self.assertEqual(report["coverage"]["discovered_files"], 1)
        self.assertEqual(report["coverage"]["processed_files"], 1)
        self.assertFalse(report["coverage"]["file_limit_reached"])
        self.assertEqual(self.family(report, "rg")["calls"], 1)

    def test_invalid_utf8_invalid_json_and_partial_trailing_record_are_counted(self):
        path = self.sessions / "rollout-invalid.jsonl"
        with path.open("wb") as handle:
            handle.write(b"\xff\n")
            handle.write(
                b'{"timestamp":"2026-10-02T10:00:00Z","type":"session_meta",'
            )
        report, _, _, _ = self.run_analyzer()
        coverage = report["coverage"]
        self.assertEqual(coverage["invalid_utf8_records"], 1)
        self.assertEqual(coverage["invalid_json_records"], 1)
        self.assertEqual(coverage["partial_trailing_records"], 1)
        self.assertEqual(coverage["shell_tool_invocations"], 0)

    def test_oversized_records_and_file_limits_are_bounded(self):
        first = self.sessions / "rollout-a.jsonl"
        first.write_bytes(b"x" * 400 + b"\n" + b"{}\n")
        second = self.sessions / "rollout-b.jsonl"
        second.write_bytes(
            json.dumps(self.call("rg x src")).encode("utf-8") + b"\n"
        )
        report, _, _, _ = self.run_analyzer(
            since=None,
            until=None,
            extra=("--max-line-bytes", "128", "--max-files", "1"),
        )
        self.assertEqual(report["coverage"]["oversized_records"], 1)
        self.assertTrue(report["coverage"]["file_limit_reached"])
        self.assertEqual(report["coverage"]["processed_files"], 1)

    def test_per_file_byte_cap_does_not_stop_later_files(self):
        first = self.sessions / "rollout-a.jsonl"
        first.write_bytes(
            b"\n".join(
                json.dumps(self.call("rg repeated src", call_id=f"c{index}")).encode("utf-8")
                for index in range(100)
            )
            + b"\n"
        )
        self.write_rollout(
            [
                self.session_meta(session_id="later-session"),
                self.call("git status", call_id="later"),
            ],
            name="rollout-b.jsonl",
        )
        report, _, _, _ = self.run_analyzer(
            since=None,
            until=None,
            extra=("--max-file-bytes", "1024"),
        )
        self.assertEqual(report["coverage"]["truncated_files"], 1)
        self.assertFalse(report["coverage"]["byte_limit_reached"])
        self.assertEqual(report["coverage"]["processed_files"], 2)
        self.assertEqual(self.family(report, "git")["calls"], 1)

    @unittest.skipIf(not hasattr(os, "symlink"), "symlinks unavailable")
    def test_symlinked_rollouts_are_not_traversed_or_read(self):
        external = self.root / "external-rollout.jsonl"
        external.write_text(
            json.dumps(self.call("rg should-not-read src")) + "\n",
            encoding="utf-8",
        )
        os.symlink(external, self.sessions / "rollout-link.jsonl")
        report, _, _, _ = self.run_analyzer(since=None, until=None)
        self.assertEqual(report["coverage"]["processed_files"], 0)
        self.assertEqual(report["coverage"]["skipped_symlinks"], 1)
        self.assertEqual(report["coverage"]["shell_tool_invocations"], 0)

    def test_archived_rollouts_are_opt_in(self):
        self.write_rollout(
            [self.session_meta(session_id="session-one"), self.call("rg one src")]
        )
        archived = self.codex_home / "archived_sessions"
        self.write_rollout(
            [
                self.session_meta(session_id="session-two"),
                self.call("git status", call_id="archive-call"),
            ],
            directory=archived,
            name="rollout-archived.jsonl",
        )
        report, _, _, _ = self.run_analyzer()
        self.assertEqual(report["coverage"]["sessions"], 1)
        report, _, _, _ = self.run_analyzer(include_archived=True)
        self.assertEqual(report["coverage"]["sessions"], 2)
        self.assertEqual(
            report["analysis_scope"]["source_categories"],
            {"archived_sessions": 1, "sessions": 1},
        )

    def test_output_shapes_preserve_status_stream_metadata_and_ansi(self):
        self.write_rollout(
            [
                self.session_meta(),
                self.call("rg needle src"),
                {
                    "timestamp": "2026-10-02T10:03:00Z",
                    "type": "response_item",
                    "payload": {
                        "type": "function_call_output",
                        "call_id": "call-1",
                        "output": {
                            "stdout": "\x1b[31mneedle\x1b[0m\n",
                            "stderr": "warning\n",
                            "exit_code": 0,
                        },
                    },
                },
            ]
        )
        report, _, _, _ = self.run_analyzer()
        output = self.family(report, "rg")["output"]
        self.assertEqual(output["status_counts"], {"success": 1})
        self.assertEqual(output["separate_stream_observations"], 1)
        self.assertGreater(output["structural_feature_counts"]["ansi"], 0)
        adapter = next(
            row for row in report["terse_adapters"] if row["candidate_id"] == "rg_grep"
        )
        self.assertGreater(adapter["simulation"]["removed_observed_bytes"], 0)

    def test_terse_ranking_uses_output_size_and_marks_high_risk_diff(self):
        progress = "\n".join(["." * 100, "120 passed, 0 failed in 5.00s"])
        self.write_rollout(
            [
                self.session_meta(),
                self.call("python -m pytest -q", call_id="pytest"),
                self.output(progress, call_id="pytest"),
                self.call("git diff -- src", call_id="diff"),
                self.output(
                    "\n".join(["@@ -1,2 +1,2 @@", "-old", "+new"] * 100),
                    call_id="diff",
                ),
            ]
        )
        report, markdown, _, _ = self.run_analyzer()
        pytest = next(
            row for row in report["terse_adapters"] if row["candidate_id"] == "pytest_success"
        )
        diff = next(
            row for row in report["terse_adapters"] if row["candidate_id"] == "git_diff"
        )
        self.assertGreater(pytest["simulation"]["removed_observed_bytes"], 50)
        self.assertIn("pytest_success", report["smallest_safe_initial_set"])
        self.assertEqual(diff["safety_class"], "requires_original_output_recovery")
        self.assertEqual(diff["simulation"]["removed_observed_bytes"], 0)
        self.assertLess(markdown.index("`pytest_success`"), markdown.index("`git_diff`"))

    def test_identical_fixtures_produce_byte_identical_reports(self):
        self.write_rollout(
            [
                self.session_meta(),
                self.call("git status --short"),
                self.output("?? file.txt\n"),
            ]
        )
        first, _, _, _ = self.run_analyzer(output_dir=self.root / "first")
        second, _, _, _ = self.run_analyzer(output_dir=self.root / "second")
        self.assertEqual(
            json.dumps(first, sort_keys=True),
            json.dumps(second, sort_keys=True),
        )
        for filename in (
            "command_frequency_report.md",
            "command_frequency_report.json",
            "opaque_command_diagnostics.md",
            "opaque_command_diagnostics.json",
            "command_sequence_report.md",
            "command_sequence_report.json",
        ):
            self.assertEqual(
                (self.root / "first" / filename).read_bytes(),
                (self.root / "second" / filename).read_bytes(),
            )

    def test_optional_fingerprints_are_salted_and_raw_commands_stay_hidden(self):
        self.write_rollout(
            [self.session_meta(), self.call("rg secret-value src"), self.output("x\n")]
        )
        report, markdown, _, _ = self.run_analyzer(
            extra=("--fingerprint-salt", "test-only-salt")
        )
        fingerprints = report["command_frequency"]["fingerprints"]
        self.assertTrue(fingerprints)
        self.assertTrue(report["privacy"]["fingerprints_included"])
        combined = markdown + json.dumps(report)
        self.assertNotIn("secret-value", combined)

    def test_report_targets_are_private_regular_files(self):
        self.write_rollout(
            [self.session_meta(), self.call("rg x src"), self.output("x\n")]
        )
        self.run_analyzer()
        self.assertEqual(self.output_dir.stat().st_mode & 0o777, 0o700)
        for name in (
            "command_frequency_report.md",
            "command_frequency_report.json",
            "opaque_command_diagnostics.md",
            "opaque_command_diagnostics.json",
            "command_sequence_report.md",
            "command_sequence_report.json",
        ):
            path = self.output_dir / name
            self.assertTrue(path.is_file())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
