import contextlib
import io
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import analyze_codex_commands as analyzer  # noqa: E402
from codex_compilation_analysis import (  # noqa: E402
    SUCCESS_OUTPUT,
    classify_validation_command,
    format_terse_failure,
)


class ResearchFixture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.codex_home = self.root / "codex"
        self.sessions = self.codex_home / "sessions"
        self.archive = self.codex_home / "archived_sessions"
        self.sessions.mkdir(parents=True)
        self.archive.mkdir(parents=True)
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
        timestamp="2026-10-02T10:01:00Z",
        name="exec_command",
        arguments=None,
    ):
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
                "arguments": arguments,
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
                "output": value,
            },
        }

    def write_rollout(
        self,
        events,
        *,
        directory=None,
        name=None,
        raw_suffix=b"",
    ):
        self.counter += 1
        directory = directory or self.sessions
        directory.mkdir(parents=True, exist_ok=True)
        name = name or f"rollout-2026-10-02T10-00-00-{self.counter:04d}.jsonl"
        path = directory / name
        with path.open("wb") as handle:
            for event in events:
                handle.write(json.dumps(event).encode("utf-8") + b"\n")
            handle.write(raw_suffix)
        return path

    def run_analyzer(
        self,
        *,
        extra=(),
        output_dir=None,
        expected_code=0,
    ):
        output_dir = output_dir or self.output_dir
        argv = [
            "--codex-home",
            str(self.codex_home),
            "--sessions-dir",
            str(self.sessions),
            "--output-dir",
            str(output_dir),
            *extra,
        ]
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = analyzer.main(argv)
        self.assertEqual(code, expected_code, stderr.getvalue())
        report = json.loads(
            (output_dir / "command_frequency_report.json").read_text()
        )
        research = json.loads(
            (output_dir / "compilation_output_research.json").read_text()
        )
        manifest = json.loads(
            (output_dir / "codex_history_census_manifest.json").read_text()
        )
        return report, research, manifest, stdout.getvalue(), stderr.getvalue()

    @staticmethod
    def classify(command, *, execution_form="direct", confidence="high"):
        analysis = analyzer.analyze_shell_command(command)
        return classify_validation_command(
            family=analysis.family,
            shape=analysis.shape,
            raw=command,
            confidence=confidence,
            execution_form=execution_form,
        )

    def test_full_history_scans_current_and_archive_across_default_file_limit(self):
        for index in range(1005):
            target = self.sessions if index % 2 == 0 else self.archive
            target.mkdir(parents=True, exist_ok=True)
            (target / f"rollout-2025-01-01T00-00-{index:04d}.jsonl").write_text(
                json.dumps({"fixture_index": index}) + "\n",
                encoding="utf-8",
            )
        report, research, manifest, stdout, _ = self.run_analyzer(
            extra=(
                "--full-history",
                "--max-files",
                "2000",
                "--max-total-bytes",
                str(16 * 1024 * 1024),
            )
        )
        self.assertEqual(report["schema_version"], 3)
        self.assertEqual(manifest["summary"]["files_found"], 1005)
        self.assertEqual(manifest["summary"]["files_scanned"], 1005)
        self.assertEqual(manifest["summary"]["current_files_scanned"], 503)
        self.assertEqual(manifest["summary"]["archived_files_scanned"], 502)
        self.assertTrue(manifest["completeness"]["exhaustive"])
        self.assertEqual(manifest["completeness"]["status"], "complete")
        self.assertIsNone(manifest["mode"]["since"])
        self.assertEqual(research["coverage"]["status"], "complete")
        self.assertIn("exhaustive", stdout)

    def test_full_history_caps_and_invalid_records_fail_coverage_nonzero(self):
        first = self.sessions / "rollout-a.jsonl"
        first.write_bytes(b'{"type":"session_meta"}\n')
        second = self.sessions / "rollout-b.jsonl"
        second.write_bytes(b"not-json\n")
        _, _, manifest, _, stderr = self.run_analyzer(
            extra=("--full-history", "--max-files", "1"),
            expected_code=3,
        )
        self.assertFalse(manifest["completeness"]["exhaustive"])
        self.assertTrue(manifest["completeness"]["full_coverage_failed"])
        self.assertIn("file_count_cap_reached", manifest["completeness"]["reasons"])
        self.assertIn("full-history coverage failed", stderr)

    def test_partial_malformed_and_symlink_inputs_are_not_called_exhaustive(self):
        valid = self.sessions / "rollout-valid.jsonl"
        valid.write_bytes(
            (json.dumps(self.session_meta()) + "\n").encode("utf-8")
            + b'{"partial":'
        )
        if hasattr(os, "symlink"):
            external = self.root / "external.jsonl"
            external.write_text("{}\n", encoding="utf-8")
            os.symlink(external, self.sessions / "rollout-link.jsonl")
        _, _, manifest, _, _ = self.run_analyzer(
            extra=("--full-history",),
            expected_code=3,
        )
        reasons = set(manifest["completeness"]["reasons"])
        self.assertIn("invalid_json_records", reasons)
        self.assertIn("partial_trailing_records", reasons)
        if hasattr(os, "symlink"):
            self.assertIn("symlink_inputs_skipped", reasons)
        self.assertEqual(manifest["completeness"]["status"], "partial")

    def test_duplicate_content_is_reconciled_and_reused_sessions_remain_scoped(self):
        events = [
            self.session_meta(session_id="shared-session"),
            self.call("cargo test", call_id="same-call"),
            self.output({"stdout": "ok\n", "exit_code": 0}, call_id="same-call"),
        ]
        self.write_rollout(
            events,
            name="rollout-2026-10-02T10-00-00-one.jsonl",
        )
        self.write_rollout(
            events,
            name="rollout-2026-10-02T10-00-00-two.jsonl",
        )
        self.write_rollout(
            [
                self.session_meta(session_id="shared-session"),
                self.call("git status", call_id="other-call"),
                self.output({"stdout": "clean\n", "exit_code": 0}, call_id="other-call"),
            ],
            directory=self.archive,
            name="rollout-2026-10-02T10-00-00-three.jsonl",
        )
        report, _, manifest, _, _ = self.run_analyzer(extra=("--full-history",))
        summary = manifest["summary"]
        self.assertEqual(summary["files_found"], 3)
        self.assertEqual(summary["files_eligible"], 2)
        self.assertEqual(summary["files_scanned"], 2)
        self.assertEqual(summary["files_omitted"], 1)
        self.assertEqual(summary["duplicate_rollout_files"], 1)
        self.assertEqual(summary["distinct_sessions"], 1)
        self.assertEqual(summary["session_source_instances"], 2)
        self.assertEqual(summary["reused_session_ids_across_sources"], 1)
        self.assertEqual(report["coverage"]["shell_tool_invocations"], 2)
        self.assertEqual(
            report["sequence_analysis"]["coverage"]["source_files"],
            2,
        )
        self.assertTrue(manifest["completeness"]["exhaustive"])

    def test_deterministic_private_reports_reconcile_and_hide_synthetic_secrets(self):
        self.write_rollout(
            [
                self.session_meta(session_id="secret-session-id"),
                self.call(
                    "cargo build --manifest-path /private/secret/Cargo.toml",
                    call_id="secret-call",
                ),
                self.output(
                    {
                        "stdout": "compiled /private/secret/Cargo.toml\n",
                        "stderr": "warning: token=super-secret-token\n",
                        "exit_code": 0,
                    },
                    call_id="secret-call",
                ),
            ]
        )
        first, research, manifest, stdout, stderr = self.run_analyzer(
            extra=("--full-history",)
        )
        second, _, _, _, _ = self.run_analyzer(
            extra=("--full-history",),
            output_dir=self.root / "second-report",
        )
        names = (
            "command_frequency_report.md",
            "command_frequency_report.json",
            "opaque_command_diagnostics.md",
            "opaque_command_diagnostics.json",
            "command_sequence_report.md",
            "command_sequence_report.json",
            "compilation_output_research.md",
            "compilation_output_research.json",
            "codex_history_census_manifest.json",
            "codex_history_census_summary.md",
        )
        for name in names:
            path = self.output_dir / name
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.output_dir.stat().st_mode & 0o777, 0o700)
        for name in names:
            self.assertEqual(
                (self.output_dir / name).read_bytes(),
                (self.root / "second-report" / name).read_bytes(),
            )
        combined = (
            json.dumps(first)
            + json.dumps(research)
            + json.dumps(manifest)
            + str(stdout)
            + str(stderr)
            + "".join((self.output_dir / name).read_text() for name in names)
        )
        for secret in (
            "secret-session-id",
            "secret-call",
            "super-secret-token",
            "/private/secret",
            "private/example",
        ):
            self.assertNotIn(secret, combined)
        self.assertEqual(
            sum(
                row["saved_bytes"]
                for row in research["candidate_outputs"]
                if row["candidate_id"] == "aggressive_success"
            ),
            0,
        )
        self.assertEqual(
            report_output_bytes(first),
            research["significance_gates"]["all_matched_output_bytes"],
        )

    def test_taxonomy_distinguishes_validation_from_unknown_package_scripts(self):
        expected = {
            "cargo build --release": ("rust", "compile/build", "direct"),
            "cargo check": ("rust", "type/check", "direct"),
            "cargo clippy": ("rust", "lint", "direct"),
            "cargo test": ("rust", "test", "direct"),
            "cargo fmt --check": ("rust", "format", "direct"),
            "go build ./...": ("go", "compile/build", "direct"),
            "go test ./...": ("go", "test", "direct"),
            "go vet ./...": ("go", "type/check", "direct"),
            "node --test": ("node-ts", "test", "direct"),
            "npm run build": ("node-ts", "compile/build", "direct"),
            "pnpm test": ("node-ts", "test", "direct"),
            "tsc --noEmit": ("node-ts", "type/check", "direct"),
            "npx tsc --noEmit": ("node-ts", "type/check", "direct"),
            "cmake --build build": ("c-cpp", "compile/build", "direct"),
            "forge build": ("other", "compile/build", "direct"),
            "pytest -q": ("python", "test", "direct"),
            "python -m compileall -q src": (
                "python",
                "compile/build",
                "direct",
            ),
            "uv run pytest -q": ("python", "test", "direct"),
        }
        for command, identity in expected.items():
            with self.subTest(command=command):
                result = self.classify(command)
                self.assertIsNotNone(result)
                self.assertEqual(
                    (result.ecosystem, result.operation, result.packaging),
                    identity,
                )
        unknown = self.classify("npm run custom-script")
        self.assertEqual(unknown.operation, "package-script-unknown")
        self.assertFalse(unknown.formatter_eligible)
        self.assertEqual(self.classify("node app.js").operation, "unknown")
        self.assertIsNone(self.classify("forge install"))
        batch = self.classify("cargo test", execution_form="native_batch")
        self.assertEqual(batch.packaging, "native_batch")
        compound = analyzer.analyze_shell_command("git status && cargo test")
        self.assertEqual(compound.confidence, "partial")
        self.assertEqual(compound.family, "<opaque>")

    def test_success_gate_requires_verified_clean_complete_output(self):
        command = self.classify("cargo build")
        verbose = "Compiling crate\nFinished dev profile\n"
        metrics = analyzer._metrics_for_text(
            verbose,
            exit_code=0,
            complete=True,
            output_kind="structured",
        )
        simulations, rejections = analyzer._research_simulations(
            command,
            metrics,
            verbose,
        )
        self.assertEqual(
            simulations["aggressive_success"].bytes,
            len(SUCCESS_OUTPUT.encode("utf-8")),
        )
        self.assertFalse(rejections)

        cases = [
            ("compiled successfully\n", None, True, {}),
            (
                "warning: deprecated API\nFinished dev profile\n",
                0,
                True,
                {},
            ),
            ("running 0 tests\n", 0, True, {}),
            ("test result: ok. 2 passed; 1 ignored\n", 0, True, {}),
            ("output truncated\nFinished dev profile\n", 0, False, {}),
            ("\x00binary\n", 0, True, {}),
            ("unexpected stdout\n", 0, True, {}),
            ("", 0, True, {}),
        ]
        for text, exit_code, complete, _ in cases:
            with self.subTest(text=text[:30]):
                metrics = analyzer._metrics_for_text(
                    text,
                    exit_code=exit_code,
                    complete=complete,
                    output_kind="structured",
                )
                simulations, rejections = analyzer._research_simulations(
                    command,
                    metrics,
                    text,
                )
                self.assertNotIn("aggressive_success", simulations)
                self.assertNotIn("conservative_success", simulations)
                self.assertIn("aggressive_success", rejections)
                self.assertIn("conservative_success", rejections)

        timeout = analyzer._metrics_for_text(
            "command timed out\n",
            exit_code=None,
            complete=True,
            output_kind="text",
        )
        self.assertEqual(timeout.certainty, "timeout")
        cancelled = analyzer._metrics_for_text(
            "cancelled before completion\n",
            exit_code=None,
            complete=True,
            output_kind="text",
        )
        self.assertEqual(cancelled.certainty, "cancelled")

    def test_failure_formatters_preserve_ecosystem_diagnostics_and_fallback(self):
        rust = (
            "   Compiling many dependencies\n" * 20
            +
            "error[E0425]: cannot find value `alpha`\n"
            " --> src/main.rs:4:9\n"
            +
            "   Compiling one more crate\n" * 20
            +
            "error[E0308]: mismatched types\n"
            " --> src/lib.rs:8:17\n"
            +
            "   Compiling another crate\n" * 20
            +
            "error: could not compile `demo`\n"
        )
        rust_result = format_terse_failure(
            rust,
            ecosystem="rust",
            certainty="failed_verified",
            complete=True,
            features={},
        )
        self.assertIn("E0425", rust_result)
        self.assertIn("E0308", rust_result)
        go = (
            "go: downloading many dependencies\n" * 20
            +
            "# example/pkg\n"
            "main.go:4:2: undefined: alpha\n"
            "go: downloading one more dependency\n" * 20
            +
            "--- FAIL: TestThing (0.00s)\n"
            "    thing_test.go:9: got 1, want 2\n"
            "go: downloading another dependency\n" * 20
        )
        go_result = format_terse_failure(
            go,
            ecosystem="go",
            certainty="failed_verified",
            complete=True,
            features={},
        )
        self.assertIn("main.go:4:2", go_result)
        self.assertIn("TestThing", go_result)
        typescript = (
            "webpack progress output\n" * 20
            +
            "src/app.ts(3,7): error TS2322: Type 'string' is not assignable.\n"
            "webpack more progress output\n" * 20
            +
            "npm ERR! command failed\n"
            "webpack final progress output\n" * 20
            +
            "AssertionError: expected true\n"
            "webpack test tail output\n" * 20
        )
        ts_result = format_terse_failure(
            typescript,
            ecosystem="node-ts",
            certainty="failed_verified",
            complete=True,
            features={},
        )
        self.assertIn("TS2322", ts_result)
        self.assertIn("AssertionError", ts_result)
        python = (
            "collected 100 items\n" * 20
            +
            "traceback (most recent call last)\n"
            '  File "tests/test_app.py", line 12, in test_value\n'
            "test progress output\n" * 20
            +
            "AssertionError: private detail\n"
            "test teardown output\n" * 20
        ).replace("traceback", "Traceback")
        py_result = format_terse_failure(
            python,
            ecosystem="python",
            certainty="failed_verified",
            complete=True,
            features={},
        )
        self.assertIn("test_app.py", py_result)
        self.assertIn("AssertionError", py_result)
        for text in (
            "thread 'main' panicked at src/main.rs:2\n",
            "linker command failed with exit code 1\n",
            "error: failure\noutput truncated\n",
            "error: failure\n\x00binary\n",
        ):
            with self.subTest(text=text[:30]):
                self.assertIsNone(
                    format_terse_failure(
                        text,
                        ecosystem="rust",
                        certainty="failed_verified",
                        complete=True,
                        features={},
                    )
                )

    def test_batch_output_is_owned_once_and_syntax_only_is_not_execution(self):
        self.write_rollout(
            [
                self.session_meta(),
                self.call(
                    "delayed-seq --initial-delay 0 -- 'cargo build' 'cargo test'",
                    call_id="batch",
                ),
                self.output(
                    "[delayed-seq] command 1/2: succeeded\n"
                    "[delayed-seq] command 2/2: failed\n"
                    "error[E0425]: cannot find value `x`\n",
                    call_id="batch",
                ),
                self.call("go test ./... && git status", call_id="compound"),
                self.output(
                    {"stdout": "main.go:4:2: undefined: x\n", "exit_code": 1},
                    call_id="compound",
                ),
            ]
        )
        report, research, _, _, _ = self.run_analyzer(
            extra=("--full-history",)
        )
        cargo_rows = [
            row
            for row in research["commands"]
            if row["family"] in {"cargo build", "cargo test"}
        ]
        self.assertEqual(len(cargo_rows), 2)
        self.assertTrue(all(row["matched_outputs"] == 0 for row in cargo_rows))
        self.assertTrue(
            all(row["packaging"] == "shell_batch" for row in cargo_rows)
        )
        self.assertTrue(research["syntax_only"])
        self.assertTrue(
            all(row["matched_outputs"] == 0 for row in research["syntax_only"])
        )
        self.assertEqual(
            research["significance_gates"]["all_matched_output_bytes"],
            report["output_measurement"]["total_attributed_output_bytes"],
        )


def report_output_bytes(report):
    return report["output_measurement"]["observed_model_visible_output"][
        "captured_model_visible_bytes"
    ]


if __name__ == "__main__":
    unittest.main()
