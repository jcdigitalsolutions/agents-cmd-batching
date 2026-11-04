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
        self.assertEqual(report["schema_version"], 2)
        self.assertIn("opaque_attribution", report)
        self.assertEqual(diagnostics["schema_version"], 2)
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
        ):
            self.assertTrue(path.is_file())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        combined = (
            markdown
            + json.dumps(report)
            + diagnostics_markdown
            + json.dumps(diagnostics)
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
        ):
            path = self.output_dir / name
            self.assertTrue(path.is_file())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
