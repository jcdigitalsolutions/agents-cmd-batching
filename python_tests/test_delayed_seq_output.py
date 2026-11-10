from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
import io
import os
import subprocess
import sys
from pathlib import Path
from threading import Event

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "delayed-seq"
LOADER = SourceFileLoader("delayed_seq_module", str(SCRIPT))
SPEC = spec_from_loader("delayed_seq_module", LOADER)
delayed_seq = module_from_spec(SPEC)
sys.modules[SPEC.name] = delayed_seq
LOADER.exec_module(delayed_seq)


def run_wrapper(tmp_path, *commands, flags=(), env=None):
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--initial-delay",
            "0",
            *flags,
            "--",
            *commands,
        ],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        timeout=10,
        check=False,
    )


def test_last_output_mode_shows_only_final_stdout_and_stderr(tmp_path):
    result = run_wrapper(
        tmp_path,
        "printf first; printf first-err >&2",
        "printf second; printf second-err >&2",
        "printf final; printf final-err >&2",
        flags=("--last-output-only",),
    )

    assert result.returncode == 0
    assert result.stdout == b"final"
    assert b"first-err" not in result.stderr
    assert b"second-err" not in result.stderr
    assert b"final-err" in result.stderr
    assert b"command 1/3: succeeded" in result.stderr
    assert b"command 3/3: succeeded" in result.stderr
    assert b"completed: 3 command(s)" in result.stderr


def test_default_mode_shows_only_final_command_output(tmp_path):
    result = run_wrapper(
        tmp_path,
        "printf first; printf first-err >&2",
        "printf second; printf second-err >&2",
    )

    assert result.returncode == 0
    assert result.stdout == b"second"
    assert b"first-err" not in result.stderr
    assert b"second-err" in result.stderr


def test_all_output_flag_preserves_fully_verbose_mode(tmp_path):
    result = run_wrapper(
        tmp_path,
        "printf first",
        "printf second",
        flags=("--all-output",),
    )

    assert result.returncode == 0
    assert result.stdout == b"firstsecond"


def test_silent_final_command_does_not_fall_back_to_earlier_output(tmp_path):
    result = run_wrapper(
        tmp_path,
        "printf should-not-fallback",
        "true",
        flags=("--last-output-only",),
    )

    assert result.returncode == 0
    assert result.stdout == b""
    assert b"should-not-fallback" not in result.stderr


@pytest.mark.parametrize(
    ("commands", "visible", "failed_index"),
    [
        (("printf bad; exit 7", "printf never"), b"bad", 1),
        (("printf hidden", "printf bad; exit 7", "printf never"), b"bad", 2),
        (("printf hidden", "printf bad; exit 7"), b"bad", 2),
    ],
)
def test_failure_always_shows_failing_command_output(
    tmp_path, commands, visible, failed_index
):
    result = run_wrapper(
        tmp_path,
        *commands,
        flags=("--last-output-only",),
    )

    assert result.returncode == 7
    assert result.stdout == visible
    assert b"hidden" not in result.stdout
    assert f"command {failed_index}/".encode() in result.stderr
    assert b"failed with status 7" in result.stderr


def test_capture_preserves_large_binary_output_and_stderr(tmp_path):
    command = (
        "python3 -c 'import os; "
        "os.write(1, b\"x\" * (1024 * 1024) + b\"\\xff\"); "
        "os.write(2, b\"err\\xfe\")'"
    )
    result = run_wrapper(
        tmp_path,
        "printf discarded",
        command,
        flags=("--last-output-only",),
    )

    assert result.returncode == 0
    assert result.stdout == b"x" * (1024 * 1024) + b"\xff"
    assert b"err\xfe" in result.stderr
    assert b"discarded" not in result.stdout


def test_timeout_preserves_interrupted_command_output(tmp_path):
    result = run_wrapper(
        tmp_path,
        "printf interrupted; exec sleep 5",
        flags=("--last-output-only", "--timeout", "0.1"),
    )

    assert result.returncode == 124
    assert result.stdout == b"interrupted"
    assert b"failed with status 124" in result.stderr


def test_signal_cancellation_preserves_interrupted_command_output(tmp_path):
    result = run_wrapper(
        tmp_path,
        'printf interrupted; kill -TERM "$PPID"; exec sleep 5',
        flags=("--last-output-only",),
    )

    assert result.returncode == 143
    assert result.stdout == b"interrupted"


def test_quiet_path_alias_remains_independent_from_output_mode(tmp_path):
    (tmp_path / "source.py").write_text("pass\n")
    result = run_wrapper(
        tmp_path,
        "printf first",
        "printf second",
        flags=("--quiet", "source.py", "--quiet-window", "0", "--all-output"),
    )

    assert result.returncode == 0
    assert result.stdout == b"firstsecond"


def test_command_start_failure_has_indexed_status_and_runs_nothing(tmp_path):
    empty_path = tmp_path / "empty-path"
    empty_path.mkdir()
    marker = tmp_path / "must-not-exist"
    environment = dict(os.environ, PATH=str(empty_path))
    result = run_wrapper(
        tmp_path,
        f"touch {marker}",
        "true",
        flags=("--last-output-only",),
        env=environment,
    )

    assert result.returncode == 2
    assert not marker.exists()
    assert b"command 1/2: failed to start" in result.stderr
    assert b"POSIX-compatible shell is not available" in result.stderr


def test_capture_setup_failure_does_not_execute_command(tmp_path, monkeypatch):
    marker = tmp_path / "must-not-exist"

    def fail_capture(**_kwargs):
        raise OSError("temporary storage unavailable")

    monkeypatch.setattr(delayed_seq.tempfile, "TemporaryFile", fail_capture)
    runner = delayed_seq.ShellCommandRunner(tmp_path, Event())
    messages = []
    result = delayed_seq.run_sequence(
        [f"touch {marker}", "true"],
        delayed_seq.SequenceConfig(
            cwd=tmp_path,
            initial_delay=0,
            last_output_only=True,
        ),
        command_runner=lambda command, timeout: runner.run(
            command, timeout, capture_output=True
        ),
        emit=messages.append,
        stdout=io.BytesIO(),
        stderr=io.BytesIO(),
    )

    assert result.exit_code == 2
    assert result.failed_command_index == 1
    assert not marker.exists()
    assert any("failed to start" in message for message in messages)
    assert any("temporary storage unavailable" in message for message in messages)


def test_broken_pipe_fails_sequence_instead_of_reporting_success(tmp_path):
    class BrokenPipe:
        def write(self, _data):
            raise BrokenPipeError("reader closed")

        def flush(self):
            pass

    runner = delayed_seq.ShellCommandRunner(tmp_path, Event())
    messages = []
    result = delayed_seq.run_sequence(
        ["printf discarded", "printf final"],
        delayed_seq.SequenceConfig(
            cwd=tmp_path,
            initial_delay=0,
            last_output_only=True,
        ),
        command_runner=lambda command, timeout: runner.run(
            command, timeout, capture_output=True
        ),
        emit=messages.append,
        stdout=BrokenPipe(),
        stderr=io.BytesIO(),
    )

    assert result.exit_code == 1
    assert result.state == "failed"
    assert result.error == "could not forward captured command output"
    assert any("cannot forward captured output" in message for message in messages)
