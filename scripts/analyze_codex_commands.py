#!/usr/bin/env python3
"""Analyze local Codex rollout JSONL without executing or publishing commands."""

from __future__ import annotations

import argparse
import collections
import dataclasses
import datetime as dt
import hashlib
import hmac
import json
import math
import os
import re
import stat
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from codex_shell_analysis import (
    OPAQUE_REASONS,
    ShellAnalysis,
    ShellLexError,
    ShellSegment,
    analyze_shell_command,
    lex_simple_words,
)


SCHEMA_VERSION = 2
DEFAULT_MAX_FILES = 1_000
DEFAULT_MAX_FILE_BYTES = 32 * 1024 * 1024
DEFAULT_MAX_TOTAL_BYTES = 512 * 1024 * 1024
DEFAULT_MAX_LINE_BYTES = 8 * 1024 * 1024
TOKEN_POINT_DIVISOR = 4
TOKEN_LOWER_DIVISOR = 6
TOKEN_UPPER_DIVISOR = 3

SHELL_TOOL_NAMES = {
    "exec_command",
    "shell_command",
    "run_command",
    "exec",
}
NATIVE_BATCH_TOOL_NAMES = {"delayed_seq", "delayed_seq_command"}
PROXY_MARKER = "CODEX_ROUTING_PROXY_VIRTUAL_BATCH=1"
ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
ANSI_RE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")
EXIT_CODE_RE = re.compile(r"(?:process\s+)?exited\s+with\s+code\s+(-?\d+)", re.I)
EXIT_CODE_FIELD_RE = re.compile(r'"exit_code"\s*:\s*(-?\d+)')
SUCCESS_MARKERS = (
    "all tests passed",
    "test result: ok",
    "tests passed",
    "passed",
    "build succeeded",
    "compiled successfully",
    "completed: ",
    "[delayed-seq] completed",
)
FAILURE_MARKERS = (
    "traceback (most recent call last)",
    "test result: failed",
    "error:",
    "panicked at",
)
TRUNCATION_MARKERS = (
    "output truncated",
    "truncated output",
    "max_output_tokens",
    "was truncated",
)


class AnalysisError(RuntimeError):
    """A bounded, user-correctable analysis failure."""


@dataclass(frozen=True)
class AnalysisOptions:
    codex_home: Path
    sessions_dir: Path | None
    output_dir: Path
    since: dt.date | None = None
    until: dt.date | None = None
    include_archived: bool = False
    max_files: int = DEFAULT_MAX_FILES
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES
    max_line_bytes: int = DEFAULT_MAX_LINE_BYTES
    fingerprint_salt: str | None = None


@dataclass
class OutputMetrics:
    bytes: int
    chars: int
    lines: int
    status: str
    features: dict[str, bool]
    stdout_bytes: int | None = None
    stderr_bytes: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class OutputObservation:
    fingerprint: str
    metrics: OutputMetrics
    simulations: dict[str, OutputMetrics]
    wrapper_succeeded: int = 0
    wrapper_failed: int = 0


@dataclass
class CommandView:
    raw: str
    family: str
    shape: str
    confidence: str
    opaque_reason: str | None = None
    secondary_reasons: tuple[str, ...] = ()
    segments: tuple[ShellSegment, ...] = ()
    would_be_opaque_under_v1: bool = False
    leading_assignment: bool = False
    wrapper: str | None = None
    features: tuple[str, ...] = ()


@dataclass
class ShellInvocation:
    session_id: str
    project_category: str
    timestamp: str
    serial: int
    call_id: str
    result_key: str
    tool_name: str
    execution_form: str
    subcommands: list[CommandView]
    dry_run: bool = False
    parent_mixed: bool = False
    duplicate_signature: tuple[Any, ...] = ()
    output_match: str = "unmatched"
    output: OutputObservation | None = None
    status: str = "unknown"


@dataclass
class SourceStats:
    discovered_files: int = 0
    processed_files: int = 0
    skipped_symlinks: int = 0
    unreadable_files: int = 0
    records: int = 0
    invalid_utf8: int = 0
    invalid_json: int = 0
    oversized_lines: int = 0
    partial_trailing_records: int = 0
    file_limit_reached: bool = False
    byte_limit_reached: bool = False
    truncated_files: int = 0
    source_categories: collections.Counter[str] = field(default_factory=collections.Counter)


@dataclass
class ScanState:
    options: AnalysisOptions
    source: SourceStats = field(default_factory=SourceStats)
    calls: list[ShellInvocation] = field(default_factory=list)
    calls_by_result_key: dict[tuple[str, str], list[ShellInvocation]] = field(
        default_factory=lambda: collections.defaultdict(list)
    )
    call_keys: dict[tuple[str, str], ShellInvocation] = field(default_factory=dict)
    outputs_by_key: dict[tuple[str, str], list[OutputObservation]] = field(
        default_factory=lambda: collections.defaultdict(list)
    )
    non_shell_tools: collections.Counter[str] = field(default_factory=collections.Counter)
    non_shell_call_keys: set[tuple[str, str]] = field(default_factory=set)
    duplicate_request_events: int = 0
    conflicting_request_events: int = 0
    malformed_arguments: int = 0
    duplicate_output_events: int = 0
    ambiguous_outputs: int = 0
    custom_bundle_count: int = 0
    serial: int = 0
    sessions_seen: set[str] = field(default_factory=set)
    missing_timestamps: int = 0


@dataclass(frozen=True)
class CandidateSpec:
    candidate_id: str
    title: str
    safety_class: str
    transform: str | None
    complexity: str
    edge_cases: str
    risks: str
    fallback: str


CANDIDATES = (
    CandidateSpec(
        "rg_grep",
        "rg / grep output",
        "safe_to_aggregate",
        "ansi",
        "low",
        "ANSI controls, binary matches, context groups, and truncation",
        "Losing match context or stable result ordering",
        "Byte-for-byte passthrough on parse or encoding failure",
    ),
    CandidateSpec(
        "pytest_success",
        "pytest successful output",
        "safe_to_aggregate",
        "pytest_success",
        "medium",
        "Warnings, skips, xfails, collection errors, and plugin output",
        "Removing a warning that later explains a failure",
        "Retain summaries/warnings; passthrough every failing run",
    ),
    CandidateSpec(
        "rust_test_success",
        "Cargo test successful output",
        "safe_to_aggregate",
        "test_success",
        "medium",
        "Doc tests, nextest, ignored tests, and doctest failures",
        "Hiding package-specific warnings or ignored-test context",
        "Retain warnings and all nonzero-exit output",
    ),
    CandidateSpec(
        "go_test_success",
        "Go test successful output",
        "safe_to_aggregate",
        "test_success",
        "low",
        "Cached results, package failures, races, and multiple packages",
        "Dropping package names needed to select a retry",
        "Retain one summary per package and all failures",
    ),
    CandidateSpec(
        "js_test_success",
        "JavaScript test successful output",
        "safe_to_aggregate",
        "test_success",
        "medium",
        "Framework-specific reporters, snapshots, and coverage tables",
        "Losing suite names or flaky-test warnings",
        "Keep summaries and warnings; passthrough failures",
    ),
    CandidateSpec(
        "compiler_linter",
        "Compiler / linter output",
        "safe_to_aggregate",
        "clean_success",
        "medium",
        "Warnings, notes, dependency errors, and machine-readable formats",
        "Dropping a warning that the next command treats as an error",
        "Preserve any diagnostic text; aggregate only clean success",
    ),
    CandidateSpec(
        "git_status",
        "git status",
        "high_diagnostic_risk",
        "ansi",
        "low",
        "Branch/upstream advice, renames, conflicts, and porcelain formats",
        "Losing staged/unstaged distinctions",
        "Only strip control codes; otherwise preserve output",
    ),
    CandidateSpec(
        "git_history",
        "git log / show --stat",
        "high_diagnostic_risk",
        "ansi",
        "medium",
        "Merge topology, rename detection, binary files, and custom formats",
        "Losing commit/stat detail needed for review",
        "Preserve full output unless a proven lossless formatter is selected",
    ),
    CandidateSpec(
        "git_diff",
        "git diff",
        "requires_original_output_recovery",
        None,
        "high",
        "Combined diffs, binary patches, rename metadata, and truncation",
        "Deleting context required for review or patch application",
        "Passthrough; no terse transform recommended initially",
    ),
    CandidateSpec(
        "package_manager",
        "Package manager output",
        "high_diagnostic_risk",
        "ansi",
        "high",
        "Dependency conflicts, audit output, lifecycle scripts, and progress",
        "Hiding a security or dependency-resolution warning",
        "Preserve warnings/errors and prefer native quiet flags",
    ),
    CandidateSpec(
        "filesystem_read",
        "Filesystem / source reads",
        "passthrough",
        None,
        "high",
        "Binary files, encoding errors, globs, and context-dependent source",
        "Silently omitting content the model needed to inspect",
        "Always passthrough",
    ),
)
CANDIDATE_BY_ID = {item.candidate_id: item for item in CANDIDATES}


OpaqueShell = ShellLexError


class JSLiteralParser:
    """Parse a conservative JSON-like JavaScript literal from a fixed offset."""

    def __init__(self, source: str, position: int):
        self.source = source
        self.position = position

    def parse(self) -> Any:
        value = self._value()
        self._space()
        return value

    def _space(self) -> None:
        while self.position < len(self.source):
            if self.source[self.position].isspace():
                self.position += 1
            elif self.source.startswith("//", self.position):
                end = self.source.find("\n", self.position + 2)
                self.position = len(self.source) if end < 0 else end + 1
            elif self.source.startswith("/*", self.position):
                end = self.source.find("*/", self.position + 2)
                if end < 0:
                    raise ValueError("unterminated comment")
                self.position = end + 2
            else:
                break

    def _value(self) -> Any:
        self._space()
        if self.position >= len(self.source):
            raise ValueError("missing value")
        char = self.source[self.position]
        if char == "{":
            return self._object()
        if char == "[":
            return self._array()
        if char in "\"'`":
            return self._string()
        if self.source.startswith("true", self.position):
            self.position += 4
            return True
        if self.source.startswith("false", self.position):
            self.position += 5
            return False
        if self.source.startswith("null", self.position):
            self.position += 4
            return None
        number = re.match(r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?", self.source[self.position :])
        if number:
            self.position += len(number.group(0))
            text = number.group(0)
            return float(text) if any(mark in text for mark in ".eE") else int(text)
        raise ValueError("unsupported JavaScript literal")

    def _object(self) -> dict[str, Any]:
        self.position += 1
        result: dict[str, Any] = {}
        self._space()
        if self._take("}"):
            return result
        while True:
            self._space()
            if self.position >= len(self.source):
                raise ValueError("unterminated object")
            if self.source[self.position] in "\"'":
                key = self._string()
            else:
                match = re.match(r"[A-Za-z_$][A-Za-z0-9_$]*", self.source[self.position :])
                if not match:
                    raise ValueError("unsupported object key")
                key = match.group(0)
                self.position += len(key)
            self._space()
            self._expect(":")
            result[key] = self._value()
            self._space()
            if self._take("}"):
                return result
            self._expect(",")
            self._space()
            if self._take("}"):
                return result

    def _array(self) -> list[Any]:
        self.position += 1
        result: list[Any] = []
        self._space()
        if self._take("]"):
            return result
        while True:
            result.append(self._value())
            self._space()
            if self._take("]"):
                return result
            self._expect(",")
            self._space()
            if self._take("]"):
                return result

    def _string(self) -> str:
        quote = self.source[self.position]
        self.position += 1
        result: list[str] = []
        while self.position < len(self.source):
            char = self.source[self.position]
            self.position += 1
            if char == quote:
                return "".join(result)
            if quote == "`" and char == "$" and self.position < len(self.source):
                if self.source[self.position] == "{":
                    raise ValueError("template interpolation is not supported")
            if char != "\\":
                result.append(char)
                continue
            if self.position >= len(self.source):
                raise ValueError("unterminated escape")
            escaped = self.source[self.position]
            self.position += 1
            escapes = {
                "b": "\b",
                "f": "\f",
                "n": "\n",
                "r": "\r",
                "t": "\t",
                "v": "\v",
                "0": "\0",
                "\\": "\\",
                "'": "'",
                '"': '"',
                "`": "`",
            }
            if escaped in escapes:
                result.append(escapes[escaped])
            elif escaped == "u" and self.position + 4 <= len(self.source):
                digits = self.source[self.position : self.position + 4]
                if not re.fullmatch(r"[0-9A-Fa-f]{4}", digits):
                    raise ValueError("invalid Unicode escape")
                result.append(chr(int(digits, 16)))
                self.position += 4
            elif escaped == "\n":
                continue
            else:
                result.append(escaped)
        raise ValueError("unterminated string")

    def _take(self, char: str) -> bool:
        if self.position < len(self.source) and self.source[self.position] == char:
            self.position += 1
            return True
        return False

    def _expect(self, char: str) -> None:
        if not self._take(char):
            raise ValueError(f"expected {char}")


def _date_from_timestamp(value: Any) -> dt.date | None:
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return dt.date.fromisoformat(value[:10])
    except ValueError:
        return None


def _within_window(timestamp: Any, options: AnalysisOptions) -> bool:
    value = _date_from_timestamp(timestamp)
    if value is None:
        return options.since is None and options.until is None
    if options.since is not None and value < options.since:
        return False
    if options.until is not None and value > options.until:
        return False
    return True


def _normal_tool_name(value: Any) -> str:
    if not isinstance(value, str):
        return "unknown"
    name = value.rsplit(".", 1)[-1]
    return name if re.fullmatch(r"[A-Za-z0-9_+-]{1,80}", name) else "unknown"


def _raw_arguments(payload: dict[str, Any]) -> tuple[dict[str, Any] | None, bool]:
    raw = payload.get("arguments")
    if raw is None:
        raw = payload.get("input")
    if isinstance(raw, dict):
        return raw, False
    if not isinstance(raw, str):
        return None, True
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None, True
    return (parsed, False) if isinstance(parsed, dict) else (None, True)


def _command_from_arguments(arguments: dict[str, Any]) -> str | None:
    for key in ("cmd", "command"):
        value = arguments.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _commands_from_native_arguments(arguments: dict[str, Any]) -> list[str] | None:
    value = arguments.get("commands")
    if isinstance(value, list) and value and all(isinstance(item, str) and item.strip() for item in value):
        return list(value)
    command = _command_from_arguments(arguments)
    return [command] if command else None


def _mask_js_strings_and_comments(source: str) -> str:
    output = list(source)
    index = 0
    state = "code"
    quote = ""
    while index < len(source):
        char = source[index]
        nxt = source[index + 1] if index + 1 < len(source) else ""
        if state == "code":
            if char in "\"'`":
                state = "string"
                quote = char
            elif char == "/" and nxt == "/":
                output[index] = output[index + 1] = " "
                state = "line_comment"
                index += 2
                continue
            elif char == "/" and nxt == "*":
                output[index] = output[index + 1] = " "
                state = "block_comment"
                index += 2
                continue
        elif state in {"string", "line_comment", "block_comment"}:
            if char != "\n":
                output[index] = " "
            if state == "string" and char == "\\" and index + 1 < len(source):
                output[index + 1] = " "
                index += 2
                continue
            if state == "string" and char == quote:
                state = "code"
            elif state == "line_comment" and char == "\n":
                state = "code"
            elif state == "block_comment" and char == "*" and nxt == "/":
                output[index + 1] = " "
                state = "code"
                index += 2
                continue
        index += 1
    return "".join(output)


def _extract_embedded_tool_calls(source: str) -> tuple[list[tuple[str, dict[str, Any]]], int]:
    masked = _mask_js_strings_and_comments(source)
    calls: list[tuple[str, dict[str, Any]]] = []
    failures = 0
    for match in re.finditer(r"\btools\.([A-Za-z_][A-Za-z0-9_]*)\s*\(", masked):
        name = match.group(1)
        position = match.end()
        while position < len(source) and source[position].isspace():
            position += 1
        if position >= len(source) or source[position] != "{":
            failures += 1
            continue
        try:
            value = JSLiteralParser(source, position).parse()
        except ValueError:
            failures += 1
            continue
        if not isinstance(value, dict):
            failures += 1
            continue
        calls.append((name, value))
    return calls, failures


def _tokenize_simple_shell(command: str) -> list[str]:
    return lex_simple_words(command)


def _safe_family(value: str) -> str:
    name = Path(value).name
    if re.fullmatch(r"[A-Za-z0-9_.+-]{1,80}", name):
        return name
    return "<unknown>"


def _parse_simple_command(command: str) -> CommandView:
    analysis: ShellAnalysis = analyze_shell_command(command)
    return CommandView(
        raw=command,
        family=analysis.family,
        shape=analysis.shape,
        confidence=analysis.confidence,
        opaque_reason=analysis.opaque_reason,
        secondary_reasons=analysis.secondary_reasons,
        segments=analysis.segments,
        would_be_opaque_under_v1=analysis.would_be_opaque_under_v1,
        leading_assignment=analysis.leading_assignment,
        wrapper=analysis.wrapper,
        features=analysis.features,
    )


def _parse_delayed_tokens(tokens: Sequence[str]) -> tuple[list[str], bool, bool] | None:
    if not tokens:
        return None
    proxy = False
    index = 0
    while index < len(tokens) and ASSIGNMENT_RE.match(tokens[index]):
        if tokens[index] != PROXY_MARKER:
            return None
        proxy = True
        index += 1
    if index >= len(tokens) or _safe_family(tokens[index]) != "delayed-seq":
        return None
    index += 1
    if "--" in tokens[index:]:
        separator = tokens.index("--", index)
        options = tokens[index:separator]
        commands = list(tokens[separator + 1 :])
    else:
        options: list[str] = []
        commands = []
        takes_value = {
            "--initial-delay",
            "--quiet-path",
            "--quiet",
            "--quiet-window",
            "--quiet-timeout",
            "--poll-interval",
            "--timeout",
        }
        while index < len(tokens):
            token = tokens[index]
            if token == "--dry-run":
                options.append(token)
                index += 1
            elif token in takes_value:
                options.append(token)
                index += 1
                if index >= len(tokens):
                    return None
                options.append(tokens[index])
                index += 1
            elif token.startswith("-"):
                return None
            else:
                commands = list(tokens[index:])
                break
    if not commands or any(not command.strip() for command in commands):
        return None
    dry_run = False
    option_index = 0
    while option_index < len(options):
        token = options[option_index]
        if token == "--dry-run":
            dry_run = True
            option_index += 1
        elif token in {
            "--initial-delay",
            "--quiet-path",
            "--quiet",
            "--quiet-window",
            "--quiet-timeout",
            "--poll-interval",
            "--timeout",
        }:
            option_index += 2
        else:
            return None
    return commands, dry_run, proxy


@dataclass
class InvocationPlan:
    tool_name: str
    execution_form: str
    subcommands: list[CommandView]
    dry_run: bool
    result_key_suffix: str = ""


def _plan_invocation(tool_name: str, arguments: dict[str, Any]) -> InvocationPlan | None:
    normalized = _normal_tool_name(tool_name)
    if normalized in NATIVE_BATCH_TOOL_NAMES:
        commands = _commands_from_native_arguments(arguments)
        if not commands:
            return None
        return InvocationPlan(
            normalized,
            "native_batch",
            [_parse_simple_command(command) for command in commands],
            False,
        )
    if normalized not in SHELL_TOOL_NAMES:
        return None
    command = _command_from_arguments(arguments)
    if command is None:
        return None
    try:
        tokens = _tokenize_simple_shell(command)
    except OpaqueShell:
        tokens = []
    delayed = _parse_delayed_tokens(tokens) if tokens else None
    if delayed is not None:
        commands, dry_run, proxy = delayed
        execution_form = "proxy_batch" if proxy else "shell_batch"
        return InvocationPlan(
            normalized,
            execution_form,
            [_parse_simple_command(item) for item in commands],
            dry_run,
        )
    return InvocationPlan(
        normalized,
        "direct",
        [_parse_simple_command(command)],
        False,
    )


def _add_invocation(
    state: ScanState,
    *,
    session_id: str,
    timestamp: str,
    call_id: str,
    result_key: str,
    plan: InvocationPlan,
    parent_mixed: bool = False,
) -> None:
    signature = (
        plan.tool_name,
        plan.execution_form,
        plan.dry_run,
        tuple(command.raw for command in plan.subcommands),
    )
    key = (session_id, call_id)
    existing = state.call_keys.get(key)
    if existing is not None:
        if existing.duplicate_signature == signature:
            state.duplicate_request_events += 1
        else:
            state.conflicting_request_events += 1
            existing.output_match = "ambiguous_request"
        return
    state.serial += 1
    invocation = ShellInvocation(
        session_id=session_id,
        project_category=_project_category(),
        timestamp=timestamp,
        serial=state.serial,
        call_id=call_id,
        result_key=result_key,
        tool_name=plan.tool_name,
        execution_form=plan.execution_form,
        subcommands=plan.subcommands,
        dry_run=plan.dry_run,
        parent_mixed=parent_mixed,
        duplicate_signature=signature,
    )
    state.call_keys[key] = invocation
    state.calls_by_result_key[(session_id, result_key)].append(invocation)
    state.calls.append(invocation)
    state.sessions_seen.add(session_id)


def _project_category() -> str:
    return "workspace"


def _process_call_payload(
    state: ScanState,
    *,
    session_id: str,
    timestamp: str,
    payload: dict[str, Any],
) -> None:
    call_type = payload.get("type")
    if call_type not in {"function_call", "custom_tool_call"}:
        return
    call_id = payload.get("call_id")
    if not isinstance(call_id, str) or not call_id:
        state.malformed_arguments += 1
        return
    name = _normal_tool_name(payload.get("name"))

    if call_type == "function_call":
        arguments, malformed = _raw_arguments(payload)
        if malformed or arguments is None:
            state.malformed_arguments += 1
            if name in SHELL_TOOL_NAMES | NATIVE_BATCH_TOOL_NAMES:
                return
        else:
            plan = _plan_invocation(name, arguments)
            if plan is not None:
                _add_invocation(
                    state,
                    session_id=session_id,
                    timestamp=timestamp,
                    call_id=call_id,
                    result_key=call_id,
                    plan=plan,
                )
                return
        state.non_shell_tools[name] += 1
        state.non_shell_call_keys.add((session_id, call_id))
        return

    raw_input = payload.get("input")
    if name == "exec" and isinstance(raw_input, str):
        state.custom_bundle_count += 1
        embedded, failures = _extract_embedded_tool_calls(raw_input)
        state.malformed_arguments += failures
        shell_calls: list[tuple[str, dict[str, Any]]] = []
        non_shell = 0
        for embedded_name, arguments in embedded:
            normalized = _normal_tool_name(embedded_name)
            if normalized in SHELL_TOOL_NAMES | NATIVE_BATCH_TOOL_NAMES:
                shell_calls.append((normalized, arguments))
            else:
                non_shell += 1
                state.non_shell_tools[normalized] += 1
        for index, (embedded_name, arguments) in enumerate(shell_calls):
            plan = _plan_invocation(embedded_name, arguments)
            if plan is None:
                state.malformed_arguments += 1
                continue
            _add_invocation(
                state,
                session_id=session_id,
                timestamp=timestamp,
                call_id=f"{call_id}#{index}",
                result_key=call_id,
                plan=plan,
                parent_mixed=non_shell > 0 or len(shell_calls) > 1,
            )
        if not shell_calls:
            state.non_shell_tools["exec"] += 1
            state.non_shell_call_keys.add((session_id, call_id))
        return

    if isinstance(raw_input, str):
        try:
            parsed = json.loads(raw_input)
        except (json.JSONDecodeError, ValueError):
            parsed = None
        if isinstance(parsed, dict):
            plan = _plan_invocation(name, parsed)
            if plan is not None:
                _add_invocation(
                    state,
                    session_id=session_id,
                    timestamp=timestamp,
                    call_id=call_id,
                    result_key=call_id,
                    plan=plan,
                )
                return
    state.non_shell_tools[name] += 1
    state.non_shell_call_keys.add((session_id, call_id))


def _detect_status(text: str) -> str:
    lower = text.lower()
    for pattern in (EXIT_CODE_RE, EXIT_CODE_FIELD_RE):
        match = pattern.search(text)
        if match:
            return "success" if int(match.group(1)) == 0 else "failed"
    if "[delayed-seq] completed:" in lower or "[delayed-seq] completed" in lower:
        return "success"
    if "failed with status" in lower or "timed out" in lower or "panicked at" in lower:
        return "failed"
    if _has_failure(text):
        return "failed"
    if any(marker in lower for marker in SUCCESS_MARKERS):
        return "success"
    return "unknown"


def _has_failure(text: str) -> bool:
    lower = text.lower()
    if any(marker in lower for marker in FAILURE_MARKERS):
        return True
    return bool(
        re.search(r"\b[1-9]\d*\s+failed\b", lower)
        or re.search(r'"status"\s*:\s*"failed"', lower)
        or re.search(r"\bfailed\s+with\s+status\b", lower)
    )


def _structural_features(text: str) -> dict[str, bool]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    counts = collections.Counter(lines)
    repeated = bool(lines) and max(counts.values()) >= 3 and max(counts.values()) / len(lines) >= 0.3
    lower = text.lower()
    json_like = False
    try:
        json.loads(text)
        json_like = True
    except (json.JSONDecodeError, ValueError):
        pass
    return {
        "ansi": bool(ANSI_RE.search(text)),
        "binary_control": "\x00" in text,
        "repetitive_lines": repeated,
        "success_lines": any(marker in lower for marker in SUCCESS_MARKERS),
        "warnings": "warning:" in lower or "warnings summary" in lower,
        "stack_trace": "traceback (most recent call last)" in lower or "panicked at" in lower,
        "assertion_location": bool(re.search(r"\bassert(?:ion)?\b", text, re.I)),
        "git_hunk": "@@" in text,
        "json_like": json_like,
        "timestamps": bool(
            re.search(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}", text)
        ),
        "truncated": any(marker in lower for marker in TRUNCATION_MARKERS),
    }


def _simulate_pytest_success(text: str) -> str | None:
    lower = text.lower()
    if not any(marker in lower for marker in SUCCESS_MARKERS):
        return None
    if _has_failure(text):
        return None
    keep: list[str] = []
    for line in text.splitlines():
        lower_line = line.lower()
        if (
            " warning" in lower_line
            or lower_line.startswith("warning")
            or "short test summary" in lower_line
            or re.search(r"\b\d+\s+(?:passed|skipped|xfailed|xpassed|deselected)\b", lower_line)
        ):
            keep.append(line)
    if not keep:
        return None
    result = "pytest: success\n" + "\n".join(dict.fromkeys(keep)) + "\n"
    return result if len(result.encode("utf-8")) < len(text.encode("utf-8")) else None


def _simulate_test_success(text: str) -> str | None:
    lower = text.lower()
    if not any(marker in lower for marker in ("test result: ok", "tests passed", "passed")):
        return None
    if _has_failure(text):
        return None
    keep = [
        line
        for line in text.splitlines()
        if re.search(r"\b(?:test result|passed|ok\s|warning|ignored|skipped)\b", line, re.I)
    ]
    if not keep:
        return None
    result = "test: success\n" + "\n".join(dict.fromkeys(keep)) + "\n"
    return result if len(result.encode("utf-8")) < len(text.encode("utf-8")) else None


def _parse_structured_output(value: Any) -> tuple[str, int | None, int | None]:
    stdout_bytes = stderr_bytes = None
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if isinstance(value, dict):
        stdout = value.get("stdout")
        stderr = value.get("stderr")
        if isinstance(stdout, str) or isinstance(stderr, str):
            text = (stdout if isinstance(stdout, str) else "") + (
                stderr if isinstance(stderr, str) else ""
            )
        if isinstance(stdout, str):
            stdout_bytes = len(stdout.encode("utf-8"))
        if isinstance(stderr, str):
            stderr_bytes = len(stderr.encode("utf-8"))
        exit_code = value.get("exit_code")
        if isinstance(exit_code, int):
            text += f"Process exited with code {exit_code}\n"
    return text, stdout_bytes, stderr_bytes


def _model_visible_text(value: Any) -> tuple[str, int | None, int | None]:
    if isinstance(value, str):
        stdout_bytes = stderr_bytes = None
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            parsed = None
        if isinstance(parsed, dict):
            stdout = parsed.get("stdout")
            stderr = parsed.get("stderr")
            if isinstance(stdout, str):
                stdout_bytes = len(stdout.encode("utf-8"))
            if isinstance(stderr, str):
                stderr_bytes = len(stderr.encode("utf-8"))
        return value, stdout_bytes, stderr_bytes
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "".join(parts), None, None
    if isinstance(value, dict):
        return _parse_structured_output(value)
    return str(value), None, None


def _metrics_for_text(
    text: str,
    *,
    stdout_bytes: int | None = None,
    stderr_bytes: int | None = None,
) -> OutputMetrics:
    return OutputMetrics(
        bytes=len(text.encode("utf-8")),
        chars=len(text),
        lines=len(text.splitlines()),
        status=_detect_status(text),
        features=_structural_features(text),
        stdout_bytes=stdout_bytes,
        stderr_bytes=stderr_bytes,
    )


def _make_output_observation(value: Any) -> OutputObservation:
    text, stdout_bytes, stderr_bytes = _model_visible_text(value)
    metrics = _metrics_for_text(text, stdout_bytes=stdout_bytes, stderr_bytes=stderr_bytes)
    simulations: dict[str, OutputMetrics] = {}
    clean = ANSI_RE.sub("", text)
    if clean != text:
        simulations["ansi"] = _metrics_for_text(clean)
    pytest_text = _simulate_pytest_success(text)
    if pytest_text is not None:
        simulations["pytest_success"] = _metrics_for_text(pytest_text)
    test_text = _simulate_test_success(text)
    if test_text is not None:
        simulations["test_success"] = _metrics_for_text(test_text)
    if metrics.status == "success" and not metrics.features["warnings"]:
        clean_success = "command succeeded\n"
        if len(clean_success) < len(text):
            simulations["clean_success"] = _metrics_for_text(clean_success)
    succeeded = len(re.findall(r"\[delayed-seq\] command \d+/\d+: succeeded", text))
    failed = len(re.findall(r"\[delayed-seq\] command \d+/\d+: failed", text))
    return OutputObservation(
        fingerprint=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        metrics=metrics,
        simulations=simulations,
        wrapper_succeeded=succeeded,
        wrapper_failed=failed,
    )


def _process_output_payload(
    state: ScanState,
    *,
    session_id: str,
    payload: dict[str, Any],
) -> None:
    if payload.get("type") not in {"function_call_output", "custom_tool_call_output"}:
        return
    call_id = payload.get("call_id")
    if not isinstance(call_id, str) or not call_id or "output" not in payload:
        state.malformed_arguments += 1
        return
    observation = _make_output_observation(payload["output"])
    key = (session_id, call_id)
    existing = state.outputs_by_key.get(key, [])
    if existing:
        if existing[0].fingerprint == observation.fingerprint:
            state.duplicate_output_events += 1
        else:
            state.ambiguous_outputs += 1
            existing.append(observation)
        return
    state.outputs_by_key[key].append(observation)


def _session_fallback(path: Path) -> str:
    return hashlib.sha256(path.name.encode("utf-8")).hexdigest()


def _process_record(
    state: ScanState,
    *,
    row: dict[str, Any],
    session_id: str,
    timestamp: str,
) -> str:
    if row.get("type") == "session_meta" and isinstance(row.get("payload"), dict):
        payload = row["payload"]
        discovered = payload.get("session_id") or payload.get("id")
        if isinstance(discovered, str) and discovered:
            session_id = discovered
    payload = row.get("payload")
    has_date_filter = state.options.since is not None or state.options.until is not None
    if has_date_filter and _date_from_timestamp(timestamp) is None:
        state.missing_timestamps += 1
    in_window = _within_window(timestamp, state.options)
    if isinstance(payload, dict) and in_window:
        if row.get("type") == "response_item":
            _process_call_payload(
                state,
                session_id=session_id,
                timestamp=timestamp,
                payload=payload,
            )
            _process_output_payload(state, session_id=session_id, payload=payload)
    return session_id


def _iter_rollout_files(root: Path, category: str, state: ScanState):
    if not root.exists():
        return
    if not root.is_dir():
        raise AnalysisError(f"{category} root is not a directory")
    for current, directories, files in os.walk(root, followlinks=False):
        directories.sort()
        files.sort()
        for directory in list(directories):
            if (Path(current) / directory).is_symlink():
                state.source.skipped_symlinks += 1
        for name in files:
            path = Path(current) / name
            if path.is_symlink():
                state.source.skipped_symlinks += 1
                continue
            if not re.fullmatch(r"rollout-.*\.jsonl", name):
                continue
            try:
                mode = path.stat(follow_symlinks=False).st_mode
            except OSError:
                state.source.unreadable_files += 1
                continue
            if stat.S_ISREG(mode):
                yield path, category


def _rollout_path_date(path: Path) -> dt.date | None:
    for index in range(len(path.parts) - 2):
        year, month, day = path.parts[index : index + 3]
        if re.fullmatch(r"\d{4}", year) and re.fullmatch(r"\d{2}", month) and re.fullmatch(r"\d{2}", day):
            try:
                return dt.date(int(year), int(month), int(day))
            except ValueError:
                pass
    match = re.match(r"rollout-(\d{4}-\d{2}-\d{2})", path.name)
    if match:
        try:
            return dt.date.fromisoformat(match.group(1))
        except ValueError:
            pass
    return None


def _path_outside_window(path: Path, options: AnalysisOptions) -> bool:
    if options.since is None and options.until is None:
        return False
    path_date = _rollout_path_date(path)
    if path_date is None:
        return False
    if options.since is not None and path_date < options.since:
        return True
    return options.until is not None and path_date > options.until


def _read_file(
    path: Path,
    category: str,
    state: ScanState,
    remaining_total: int,
) -> int:
    budget = min(state.options.max_file_bytes, remaining_total)
    if budget <= 0:
        state.source.byte_limit_reached = True
        return 0
    consumed = 0
    session_id = _session_fallback(path)
    try:
        handle = path.open("rb")
    except OSError:
        state.source.unreadable_files += 1
        return 0
    with handle:
        while consumed < budget:
            allowed = min(state.options.max_line_bytes + 1, budget - consumed)
            raw = handle.readline(allowed)
            if not raw:
                break
            consumed += len(raw)
            if len(raw) > state.options.max_line_bytes:
                state.source.oversized_lines += 1
                while not raw.endswith(b"\n") and consumed < budget:
                    extra = handle.readline(min(64 * 1024, budget - consumed))
                    if not extra:
                        break
                    consumed += len(extra)
                    raw = extra
                continue
            partial = not raw.endswith(b"\n")
            try:
                line = raw.decode("utf-8")
            except UnicodeDecodeError:
                state.source.invalid_utf8 += 1
                if partial:
                    state.source.partial_trailing_records += 1
                continue
            try:
                row = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                state.source.invalid_json += 1
                if partial:
                    state.source.partial_trailing_records += 1
                continue
            if not isinstance(row, dict):
                state.source.invalid_json += 1
                continue
            state.source.records += 1
            timestamp = row.get("timestamp")
            timestamp_text = timestamp if isinstance(timestamp, str) else ""
            session_id = _process_record(
                state,
                row=row,
                session_id=session_id,
                timestamp=timestamp_text,
            )
        if consumed >= budget:
            try:
                has_more = bool(handle.peek(1))
            except (AttributeError, OSError):
                current = handle.tell()
                has_more = handle.read(1) != b""
                handle.seek(min(current, budget))
            if has_more:
                total_limited = remaining_total <= state.options.max_file_bytes
                if total_limited:
                    state.source.byte_limit_reached = True
                else:
                    state.source.truncated_files += 1
    state.source.processed_files += 1
    state.source.source_categories[category] += 1
    return consumed


def scan_rollouts(options: AnalysisOptions) -> ScanState:
    if options.max_files <= 0 or options.max_file_bytes <= 0 or options.max_total_bytes <= 0:
        raise AnalysisError("file and byte limits must be positive")
    if options.max_line_bytes <= 0:
        raise AnalysisError("max line bytes must be positive")
    state = ScanState(options=options)
    roots: list[tuple[Path, str]] = []
    sessions_root = options.sessions_dir or options.codex_home / "sessions"
    roots.append((sessions_root, "sessions"))
    if options.include_archived:
        roots.append((options.codex_home / "archived_sessions", "archived_sessions"))

    seen_paths: set[Path] = set()
    consumed_total = 0
    for root, category in roots:
        for path, file_category in _iter_rollout_files(root, category, state):
            if _path_outside_window(path, options):
                continue
            resolved = path.resolve(strict=False)
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)
            state.source.discovered_files += 1
            if state.source.processed_files >= options.max_files:
                state.source.file_limit_reached = True
                break
            consumed = _read_file(
                path,
                file_category,
                state,
                options.max_total_bytes - consumed_total,
            )
            consumed_total += consumed
            if state.source.byte_limit_reached:
                break
        if state.source.file_limit_reached or state.source.byte_limit_reached:
            break
    return state


def _percentile(values: Sequence[int], fraction: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * fraction) - 1)
    return ordered[index]


def _token_range(byte_count: int) -> dict[str, Any]:
    if byte_count <= 0:
        return {"lower": 0, "point": 0, "upper": 0, "confidence": "heuristic_bytes_per_token"}
    return {
        "lower": math.ceil(byte_count / TOKEN_LOWER_DIVISOR),
        "point": math.ceil(byte_count / TOKEN_POINT_DIVISOR),
        "upper": math.ceil(byte_count / TOKEN_UPPER_DIVISOR),
        "confidence": "heuristic_bytes_per_token",
    }


def _summary_metrics(items: Sequence[OutputMetrics]) -> dict[str, Any]:
    sizes = [item.bytes for item in items]
    statuses = collections.Counter(item.status for item in items)
    feature_counts: collections.Counter[str] = collections.Counter()
    for item in items:
        feature_counts.update(name for name, present in item.features.items() if present)
    streams = [
        (item.stdout_bytes or 0) + (item.stderr_bytes or 0)
        for item in items
        if item.stdout_bytes is not None or item.stderr_bytes is not None
    ]
    return {
        "matched_output_count": len(items),
        "captured_model_visible_bytes": sum(sizes),
        "captured_lines": sum(item.lines for item in items),
        "median_bytes": _percentile(sizes, 0.5),
        "p90_bytes": _percentile(sizes, 0.9),
        "p95_bytes": _percentile(sizes, 0.95),
        "max_bytes": max(sizes, default=0),
        "estimated_observation_tokens": _token_range(sum(sizes)),
        "status_counts": dict(sorted(statuses.items())),
        "structural_feature_counts": dict(sorted(feature_counts.items())),
        "separate_stream_observations": len(streams),
        "separate_stream_bytes": sum(streams),
        "provider_measured_uncached_input_tokens": None,
    }


@dataclass
class Bucket:
    calls: int = 0
    sessions: set[str] = field(default_factory=set)
    direct: int = 0
    batched: int = 0
    outputs: list[OutputMetrics] = field(default_factory=list)
    output_sessions: set[str] = field(default_factory=set)
    success: int = 0
    failed: int = 0
    unknown: int = 0
    repeated_invocations: int = 0


@dataclass
class AttributionBucket:
    commands: int = 0
    sessions: set[str] = field(default_factory=set)
    matched_call_serials: set[int] = field(default_factory=set)
    exclusive_outputs: list[OutputMetrics] = field(default_factory=list)
    command_bytes: int = 0
    execution_forms: collections.Counter[str] = field(default_factory=collections.Counter)
    confidence: collections.Counter[str] = field(default_factory=collections.Counter)
    secondary_reasons: collections.Counter[str] = field(default_factory=collections.Counter)
    features: collections.Counter[str] = field(default_factory=collections.Counter)


def _bucket_dict(bucket: Bucket) -> dict[str, Any]:
    return {
        "calls": bucket.calls,
        "distinct_sessions": len(bucket.sessions),
        "direct_calls": bucket.direct,
        "batched_calls": bucket.batched,
        "status_counts": {
            "success": bucket.success,
            "failed": bucket.failed,
            "unknown": bucket.unknown,
        },
        "repeated_invocations": bucket.repeated_invocations,
        "output": _summary_metrics(bucket.outputs),
    }


def _attribution_reason_rows(
    buckets: dict[str, AttributionBucket],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for reason in OPAQUE_REASONS:
        bucket = buckets[reason]
        rows.append(
            {
                "reason": reason,
                "requested_commands": bucket.commands,
                "distinct_sessions": len(bucket.sessions),
                "matched_output_invocations": len(bucket.matched_call_serials),
                "exclusively_attributable_output": _summary_metrics(
                    bucket.exclusive_outputs
                ),
                "execution_forms": dict(sorted(bucket.execution_forms.items())),
                "confidence": dict(sorted(bucket.confidence.items())),
                "secondary_reason_counts": dict(
                    sorted(bucket.secondary_reasons.items())
                ),
                "feature_counts": dict(sorted(bucket.features.items())),
                "source_command_token_range": _token_range(bucket.command_bytes),
            }
        )
    return rows


def _candidate_id(family: str, shape: str) -> str | None:
    if family in {"rg", "grep"}:
        return "rg_grep"
    if family in {"pytest", "python -m pytest", "unittest", "python -m unittest"}:
        return "pytest_success"
    if family == "cargo test":
        return "rust_test_success"
    if family == "go test":
        return "go_test_success"
    if family in {"npm test", "pnpm test", "yarn test", "npx jest", "npx vitest"}:
        return "js_test_success"
    if family in {
        "cargo check",
        "cargo build",
        "cargo clippy",
        "go build",
        "tsc",
        "eslint",
        "ruff",
        "mypy",
        "python -m compileall",
    }:
        return "compiler_linter"
    if family == "git":
        parts = shape.split()
        subcommand = parts[1] if len(parts) > 1 else ""
        if subcommand == "status":
            return "git_status"
        if subcommand in {"log", "show"}:
            return "git_history"
        if subcommand == "diff":
            return "git_diff"
    if family.startswith(("npm ", "pnpm ", "yarn ", "pip ", "pip3 ", "uv ", "poetry ")):
        return "package_manager"
    if family in {"npm", "pip", "pip3", "uv", "poetry", "pnpm", "yarn"}:
        return "package_manager"
    if family in {"cat", "head", "tail", "sed", "find", "ls", "tree", "wc", "du"}:
        return "filesystem_read"
    return None


def _attach_outputs(state: ScanState) -> tuple[int, int]:
    matched_groups = 0
    composite_groups = 0
    for key, observations in state.outputs_by_key.items():
        calls = state.calls_by_result_key.get(key, [])
        if not calls:
            continue
        if len(observations) != 1:
            for call in calls:
                call.output_match = "ambiguous"
            matched_groups += 1
            continue
        if len(calls) != 1 or calls[0].parent_mixed:
            for call in calls:
                call.output_match = "composite_unattributed"
            composite_groups += 1
            continue
        call = calls[0]
        if call.output_match == "ambiguous_request":
            continue
        observation = observations[0]
        call.output = observation
        call.output_match = "matched"
        call.status = observation.metrics.status
        matched_groups += 1
    return matched_groups, composite_groups


def _add_to_bucket(
    bucket: Bucket,
    call: ShellInvocation,
    command: CommandView,
    raw_counts: collections.Counter[tuple[str, str]],
    raw_key: str,
) -> None:
    bucket.calls += 1
    bucket.sessions.add(call.session_id)
    if call.execution_form == "direct":
        bucket.direct += 1
    else:
        bucket.batched += 1
    raw_counts[(raw_key, command.raw)] += 1
    if (
        call.output is not None
        and call.execution_form == "direct"
        and len(call.subcommands) == 1
        and command.confidence == "high"
    ):
        bucket.outputs.append(call.output.metrics)
        bucket.output_sessions.add(call.session_id)
        if call.output.metrics.status == "success":
            bucket.success += 1
        elif call.output.metrics.status == "failed":
            bucket.failed += 1
        else:
            bucket.unknown += 1


def _count_execution(state: ScanState, call: ShellInvocation) -> dict[str, int]:
    values = {"succeeded": 0, "failed": 0, "unknown": 0}
    if call.dry_run:
        values["unknown"] = len(call.subcommands)
        return values
    if call.execution_form == "direct":
        if call.output is None:
            values["unknown"] = 1
        elif call.status == "success":
            values["succeeded"] = 1
        elif call.status == "failed":
            values["failed"] = 1
        else:
            values["unknown"] = 1
        return values
    if call.output is not None:
        values["succeeded"] += call.output.wrapper_succeeded
        values["failed"] += call.output.wrapper_failed
    known = values["succeeded"] + values["failed"]
    values["unknown"] += max(0, len(call.subcommands) - known)
    return values


def _consecutive_batches(calls: Sequence[ShellInvocation]) -> tuple[int, list[dict[str, Any]]]:
    by_session: dict[str, list[ShellInvocation]] = collections.defaultdict(list)
    for call in calls:
        if call.execution_form == "direct" and len(call.subcommands) == 1:
            by_session[call.session_id].append(call)
    pair_counts: collections.Counter[tuple[str, str]] = collections.Counter()
    total = 0
    for session_calls in by_session.values():
        ordered = sorted(session_calls, key=lambda item: (item.timestamp, item.serial))
        for first, second in zip(ordered, ordered[1:]):
            total += 1
            pair_counts[(first.subcommands[0].shape, second.subcommands[0].shape)] += 1
    top_pairs = [
        {"first_shape": first, "second_shape": second, "pairs": count}
        for (first, second), count in sorted(
            pair_counts.items(), key=lambda item: (-item[1], item[0])
        )[:10]
    ]
    return total, top_pairs


def _fingerprint(raw: str, salt: str | None) -> str | None:
    if not salt:
        return None
    return hmac.new(salt.encode("utf-8"), raw.encode("utf-8"), hashlib.sha256).hexdigest()[:16]


def build_report(state: ScanState) -> dict[str, Any]:
    matched_groups, composite_groups = _attach_outputs(state)
    family_buckets: dict[str, Bucket] = collections.defaultdict(Bucket)
    shape_buckets: dict[str, Bucket] = collections.defaultdict(Bucket)
    raw_family_counts: collections.Counter[tuple[str, str]] = collections.Counter()
    raw_shape_counts: collections.Counter[tuple[str, str]] = collections.Counter()
    candidate_buckets: dict[str, Bucket] = {
        spec.candidate_id: Bucket() for spec in CANDIDATES
    }
    candidate_raw_counts: dict[str, collections.Counter[tuple[str, str]]] = {
        spec.candidate_id: collections.Counter() for spec in CANDIDATES
    }
    execution = collections.Counter({"succeeded": 0, "failed": 0, "unknown": 0})
    execution_forms: collections.Counter[str] = collections.Counter()
    shell_tool_counts: collections.Counter[str] = collections.Counter()
    parsing_confidence: collections.Counter[str] = collections.Counter()
    attribution_confidence: collections.Counter[str] = collections.Counter()
    subcommand_indexes: collections.Counter[str] = collections.Counter()
    attribution_reasons: dict[str, AttributionBucket] = {
        reason: AttributionBucket() for reason in OPAQUE_REASONS
    }
    reason_by_execution_form: dict[str, collections.Counter[str]] = {
        reason: collections.Counter() for reason in OPAQUE_REASONS
    }
    syntactically_recovered_families: collections.Counter[tuple[str, str]] = (
        collections.Counter()
    )
    syntactic_control_positions: collections.Counter[str] = collections.Counter()
    wrappers_recovered: collections.Counter[str] = collections.Counter()
    candidate_observations: dict[str, list[tuple[OutputMetrics, OutputMetrics | None, bool]]] = (
        collections.defaultdict(list)
    )
    command_fingerprints: dict[str, list[dict[str, str]]] = collections.defaultdict(list)
    requested_subcommands = 0
    opaque_subcommands = 0
    strict_opaque_subcommands = 0
    partial_syntactic_subcommands = 0
    high_confidence_single_subcommands = 0
    legacy_opaque_subcommands = 0
    legacy_recovered_subcommands = 0
    dry_run_subcommands = 0
    batch_calls = 0
    deliberate_batch_calls = 0
    attached_result_keys: set[tuple[str, str]] = set()
    exclusively_attributed_outputs: list[OutputMetrics] = []
    legacy_opaque_invocations = 0
    unattributed_invocations = 0
    partial_invocations = 0
    strict_opaque_invocations = 0

    for call in state.calls:
        execution_forms[call.execution_form] += 1
        shell_tool_counts[call.tool_name] += 1
        if call.execution_form != "direct":
            batch_calls += 1
            if call.dry_run:
                deliberate_batch_calls += 1
        requested_subcommands += len(call.subcommands)
        counts = _count_execution(state, call)
        execution.update(counts)
        if call.dry_run:
            dry_run_subcommands += len(call.subcommands)
        if any(command.would_be_opaque_under_v1 for command in call.subcommands):
            legacy_opaque_invocations += 1
        if any(command.confidence != "high" for command in call.subcommands):
            unattributed_invocations += 1
        if any(command.confidence == "partial" for command in call.subcommands):
            partial_invocations += 1
        if any(command.confidence == "opaque" for command in call.subcommands):
            strict_opaque_invocations += 1
        for subcommand_index, command in enumerate(call.subcommands, start=1):
            subcommand_indexes[str(subcommand_index) if subcommand_index <= 3 else "4+"] += 1
            parsing_confidence[command.confidence] += 1
            if command.confidence in {"partial", "opaque"}:
                opaque_subcommands += 1
            if command.confidence == "partial":
                partial_syntactic_subcommands += 1
                attribution_confidence["partial_syntactic"] += 1
            elif command.confidence == "opaque":
                strict_opaque_subcommands += 1
                attribution_confidence["unresolved_opaque"] += 1
            else:
                high_confidence_single_subcommands += 1
                attribution_confidence["high_confidence_single"] += 1
            if command.would_be_opaque_under_v1:
                legacy_opaque_subcommands += 1
                if command.confidence == "high":
                    legacy_recovered_subcommands += 1
            if command.wrapper is not None and command.confidence == "high":
                wrappers_recovered[command.wrapper] += 1
            for segment in command.segments:
                syntactically_recovered_families[(segment.family, segment.shape)] += 1
                syntactic_control_positions[segment.control_position] += 1
            if command.opaque_reason is not None:
                reason_bucket = attribution_reasons[command.opaque_reason]
                reason_bucket.commands += 1
                reason_bucket.sessions.add(call.session_id)
                reason_bucket.command_bytes += len(command.raw.encode("utf-8"))
                reason_bucket.execution_forms[call.execution_form] += 1
                reason_bucket.confidence[command.confidence] += 1
                reason_bucket.secondary_reasons.update(command.secondary_reasons)
                reason_bucket.features.update(command.features)
                reason_by_execution_form[command.opaque_reason][
                    call.execution_form
                ] += 1
                if call.output is not None:
                    reason_bucket.matched_call_serials.add(call.serial)
                if (
                    call.output is not None
                    and call.execution_form == "direct"
                    and len(call.subcommands) == 1
                    and command.confidence == "high"
                ):
                    reason_bucket.exclusive_outputs.append(call.output.metrics)
            _add_to_bucket(
                family_buckets[command.family],
                call,
                command,
                raw_family_counts,
                command.family,
            )
            _add_to_bucket(
                shape_buckets[command.shape],
                call,
                command,
                raw_shape_counts,
                command.shape,
            )
            candidate_id = _candidate_id(command.family, command.shape)
            if candidate_id is not None:
                _add_to_bucket(
                    candidate_buckets[candidate_id],
                    call,
                    command,
                    candidate_raw_counts[candidate_id],
                    candidate_id,
                )
                if (
                    call.output is not None
                    and call.execution_form == "direct"
                    and len(call.subcommands) == 1
                    and command.confidence == "high"
                ):
                    transform = CANDIDATE_BY_ID[candidate_id].transform
                    simulation = call.output.simulations.get(transform) if transform else None
                    candidate_observations[candidate_id].append(
                        (call.output.metrics, simulation, call.dry_run)
                    )
            if (
                call.output is not None
                and call.execution_form == "direct"
                and len(call.subcommands) == 1
                and command.confidence == "high"
            ):
                exclusively_attributed_outputs.append(call.output.metrics)
            fingerprint = _fingerprint(command.raw, state.options.fingerprint_salt)
            if fingerprint is not None:
                command_fingerprints[command.shape].append(
                    {"fingerprint": fingerprint, "family": command.family}
                )
        if call.output is not None:
            attached_result_keys.add((call.session_id, call.result_key))

    for (family, _raw), count in raw_family_counts.items():
        family_buckets[family].repeated_invocations += max(0, count - 1)
    for bucket, counts in candidate_raw_counts.items():
        candidate_buckets[bucket].repeated_invocations += sum(
            max(0, count - 1) for count in counts.values()
        )
    shape_excess: collections.Counter[str] = collections.Counter()
    for (shape, _raw), count in raw_shape_counts.items():
        shape_excess[shape] += max(0, count - 1)
    for shape, count in shape_excess.items():
        shape_buckets[shape].repeated_invocations += count

    family_rows = [
        {"family": name, **_bucket_dict(bucket)}
        for name, bucket in sorted(
            family_buckets.items(), key=lambda item: (-item[1].calls, item[0])
        )
    ]
    shape_rows = [
        {"shape": name, **_bucket_dict(bucket)}
        for name, bucket in sorted(
            shape_buckets.items(), key=lambda item: (-item[1].calls, item[0])
        )
    ]
    all_outputs = [call.output.metrics for call in state.calls if call.output is not None]
    unmatched_results = sum(
        len(observations)
        for key, observations in state.outputs_by_key.items()
        if key not in state.calls_by_result_key and key not in state.non_shell_call_keys
    )
    non_shell_result_records = sum(
        len(observations)
        for key, observations in state.outputs_by_key.items()
        if key in state.non_shell_call_keys and key not in state.calls_by_result_key
    )
    candidate_rows: list[dict[str, Any]] = []
    for spec in CANDIDATES:
        bucket = candidate_buckets[spec.candidate_id]
        observations = candidate_observations[spec.candidate_id]
        removable = 0
        transformable = 0
        transformations: collections.Counter[str] = collections.Counter()
        for original, simulated, dry_run in observations:
            if simulated is None:
                continue
            reduction = max(0, original.bytes - simulated.bytes)
            if reduction:
                removable += reduction
                transformable += 1
                transformations[spec.transform or "none"] += 1
        matched = len(bucket.outputs)
        if spec.transform is None:
            opportunity_status = "unknown_passthrough_recommended"
        elif transformable:
            opportunity_status = "measured_on_observed_output"
        elif matched:
            opportunity_status = "no_reduction_observed_or_failure_passthrough"
        else:
            opportunity_status = "unknown_no_attributed_output"
        candidate_rows.append(
            {
                "candidate_id": spec.candidate_id,
                "title": spec.title,
                "safety_class": spec.safety_class,
                "implementation_complexity": spec.complexity,
                "calls": bucket.calls,
                "distinct_sessions": len(bucket.sessions),
                "delayed_seq_calls": bucket.batched,
                "matched_output_count": matched,
                "observed_output_bytes": sum(item.bytes for item in bucket.outputs),
                "observed_output": _summary_metrics(bucket.outputs),
                "simulation": {
                    "status": opportunity_status,
                    "transformable_output_count": transformable,
                    "transformations": dict(sorted(transformations.items())),
                    "removed_observed_bytes": removable,
                    "estimated_observation_token_reduction": _token_range(removable),
                    "per_transformable_invocation_token_reduction": _token_range(
                        math.ceil(removable / transformable) if transformable else 0
                    ),
                    "fresh_input_confidence": "unverified_cache_status",
                },
                "edge_cases": spec.edge_cases,
                "information_loss_risks": spec.risks,
                "fallback": spec.fallback,
            }
        )
        if command_fingerprints:
            for row in candidate_rows[-1:]:
                row["fingerprints_suppressed"] = True

    candidate_rows.sort(
        key=lambda row: (
            row["safety_class"] != "safe_to_aggregate",
            -row["simulation"]["removed_observed_bytes"],
            -row["observed_output_bytes"],
            -row["calls"],
            row["candidate_id"],
        )
    )
    total_repeat_groups = sum(
        max(0, count - 1) for count in raw_family_counts.values()
    )
    consecutive_pairs, top_pairs = _consecutive_batches(state.calls)
    scanned_results = sum(len(items) for items in state.outputs_by_key.values())
    call_output_bytes = sum(item.bytes for item in all_outputs)
    unknown_share = (opaque_subcommands / requested_subcommands) if requested_subcommands else 0.0
    strict_unknown_share = (
        strict_opaque_subcommands / requested_subcommands
        if requested_subcommands
        else 0.0
    )
    high_confidence_share = (
        high_confidence_single_subcommands / requested_subcommands
        if requested_subcommands
        else 0.0
    )
    partial_syntax_share = (
        partial_syntactic_subcommands / requested_subcommands
        if requested_subcommands
        else 0.0
    )
    exclusive_output_bytes = sum(
        item.bytes for item in exclusively_attributed_outputs
    )
    still_unattributable_output_bytes = max(
        0, call_output_bytes - exclusive_output_bytes
    )
    non_shell_total = sum(state.non_shell_tools.values())
    shell_invocations = len(state.calls)
    matched_outputs = sum(1 for call in state.calls if call.output is not None)
    result_coverage = matched_outputs / shell_invocations if shell_invocations else 0.0
    reason_rows = _attribution_reason_rows(attribution_reasons)
    syntactic_family_rows = [
        {
            "family": family,
            "shape": shape,
            "syntactic_occurrences": count,
            "candidate_id": _candidate_id(family, shape),
        }
        for (family, shape), count in sorted(
            syntactically_recovered_families.items(),
            key=lambda item: (-item[1], item[0][0], item[0][1]),
        )[:30]
    ]
    attribution_summary = {
        "requested_commands": requested_subcommands,
        "high_confidence_single": high_confidence_single_subcommands,
        "partial_syntactic": partial_syntactic_subcommands,
        "unresolved_opaque": strict_opaque_subcommands,
        "unattributed_commands": partial_syntactic_subcommands
        + strict_opaque_subcommands,
        "high_confidence_family_coverage": round(high_confidence_share, 6),
        "partial_syntax_coverage": round(partial_syntax_share, 6),
        "unresolved_opaque_share": round(strict_unknown_share, 6),
        "legacy_v1_opaque_commands": legacy_opaque_subcommands,
        "legacy_v1_opaque_recovered_high_confidence": legacy_recovered_subcommands,
        "legacy_v1_opaque_share": round(
            legacy_opaque_subcommands / requested_subcommands
            if requested_subcommands
            else 0.0,
            6,
        ),
        "shell_invocations": shell_invocations,
        "legacy_v1_opaque_invocations": legacy_opaque_invocations,
        "unattributed_invocations": unattributed_invocations,
        "partial_syntactic_invocations": partial_invocations,
        "strict_opaque_invocations": strict_opaque_invocations,
        "exclusively_attributed_output_bytes": exclusive_output_bytes,
        "still_unattributable_output_bytes": still_unattributable_output_bytes,
    }
    reason_classified_commands = sum(
        bucket.commands for bucket in attribution_reasons.values()
    )
    reason_partial_commands = sum(
        bucket.confidence["partial"] for bucket in attribution_reasons.values()
    )
    reason_opaque_commands = sum(
        bucket.confidence["opaque"] for bucket in attribution_reasons.values()
    )
    reason_high_confidence_commands = sum(
        bucket.confidence["high"] for bucket in attribution_reasons.values()
    )
    reconciliation = {
        "reason_classified_commands": reason_classified_commands,
        "reason_high_confidence_recovered": reason_high_confidence_commands,
        "reason_partial_syntactic": reason_partial_commands,
        "reason_unresolved_opaque": reason_opaque_commands,
        "reason_non_high_confidence": reason_partial_commands
        + reason_opaque_commands,
        "coverage_opaque_subcommands": opaque_subcommands,
        "reconciles_to_opaque_subcommands": (
            reason_partial_commands + reason_opaque_commands == opaque_subcommands
        ),
        "commands_without_primary_reason": max(
            0, requested_subcommands - reason_classified_commands
        ),
    }
    attribution = {
        "semantics_version": 1,
        "confidence_levels": [
            "high_confidence_single",
            "partial_syntactic",
            "unresolved_opaque",
        ],
        "reason_precedence": list(OPAQUE_REASONS),
        "summary": attribution_summary,
        "reconciliation": reconciliation,
        "confidence": [
            {
                "confidence": name,
                "requested_commands": count,
                "share": round(
                    count / requested_subcommands if requested_subcommands else 0.0,
                    6,
                ),
            }
            for name, count in sorted(attribution_confidence.items())
        ],
        "reasons": reason_rows,
        "reason_by_execution_form": {
            reason: dict(sorted(counts.items()))
            for reason, counts in reason_by_execution_form.items()
        },
        "syntactic_segments": {
            "occurrence_count": sum(
                syntactically_recovered_families.values()
            ),
            "warning": (
                "Syntactic segments are possibilities inside one originating shell "
                "invocation, not proof that each executable ran."
            ),
            "top_families": syntactic_family_rows,
            "control_positions": dict(sorted(syntactic_control_positions.items())),
        },
        "wrappers_recovered": dict(sorted(wrappers_recovered.items())),
        "output_ownership": {
            "exclusively_attributable_matched_outputs": _summary_metrics(
                exclusively_attributed_outputs
            ),
            "matched_invocation_output_bytes": call_output_bytes,
            "still_unattributable_output_bytes": still_unattributable_output_bytes,
            "rule": (
                "Composite, partial, ambiguous, unmatched, and wrapper-batch outputs "
                "remain owned by the originating invocation and are not multiplied "
                "across syntactic segments."
            ),
        },
    }
    workload = collections.Counter()
    for row in family_rows:
        family = row["family"]
        if family in {"rg", "grep"}:
            workload["search"] += row["calls"]
        elif family == "git":
            workload["git"] += row["calls"]
        elif family in {
            "pytest",
            "python -m pytest",
            "unittest",
            "python -m unittest",
            "cargo test",
            "go test",
            "npm test",
            "pnpm test",
            "yarn test",
        }:
            workload["validation"] += row["calls"]
        elif family in {"cat", "head", "tail", "sed", "find", "ls"}:
            workload["filesystem_read"] += row["calls"]
        elif family in {"cargo check", "cargo build", "cargo clippy", "go build", "tsc"}:
            workload["build_or_lint"] += row["calls"]
        else:
            workload["other"] += row["calls"]

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "title": "Codex command frequency and tool-output report",
        "privacy": {
            "raw_commands_included": False,
            "raw_outputs_included": False,
            "prompts_included": False,
            "exact_paths_included": False,
            "fingerprints_included": bool(state.options.fingerprint_salt),
        },
        "analysis_scope": {
            "date_window": {
                "since": state.options.since.isoformat() if state.options.since else None,
                "until": state.options.until.isoformat() if state.options.until else None,
                "inclusive": True,
            },
            "include_archived": state.options.include_archived,
            "source_categories": dict(sorted(state.source.source_categories.items())),
            "limits": {
                "max_files": state.options.max_files,
                "max_file_bytes": state.options.max_file_bytes,
                "max_total_bytes": state.options.max_total_bytes,
                "max_line_bytes": state.options.max_line_bytes,
            },
        },
        "coverage": {
            "discovered_files": state.source.discovered_files,
            "processed_files": state.source.processed_files,
            "sessions": len(state.sessions_seen),
            "records": state.source.records,
            "missing_timestamps": state.missing_timestamps,
            "shell_tool_invocations": shell_invocations,
            "requested_underlying_subcommands": requested_subcommands,
            "opaque_subcommands": opaque_subcommands,
            "strict_opaque_subcommands": strict_opaque_subcommands,
            "partial_syntactic_subcommands": partial_syntactic_subcommands,
            "high_confidence_single_subcommands": high_confidence_single_subcommands,
            "legacy_v1_opaque_subcommands": legacy_opaque_subcommands,
            "parsing_unknown_share": round(unknown_share, 6),
            "strict_opaque_share": round(strict_unknown_share, 6),
            "high_confidence_family_coverage": round(high_confidence_share, 6),
            "partial_syntax_coverage": round(partial_syntax_share, 6),
            "parsing_confidence": dict(sorted(parsing_confidence.items())),
            "subcommand_index_distribution": dict(sorted(subcommand_indexes.items())),
            "non_shell_tool_invocations": non_shell_total,
            "tool_result_records": scanned_results,
            "non_shell_result_records": non_shell_result_records,
            "matched_shell_invocations": matched_outputs,
            "matched_result_groups": matched_groups,
            "unmatched_result_records": unmatched_results,
            "composite_result_groups_unattributed": composite_groups,
            "duplicate_request_events": state.duplicate_request_events,
            "conflicting_request_events": state.conflicting_request_events,
            "duplicate_output_events": state.duplicate_output_events,
            "ambiguous_output_events": state.ambiguous_outputs,
            "malformed_argument_events": state.malformed_arguments,
            "result_match_coverage": round(result_coverage, 6),
            "skipped_symlinks": state.source.skipped_symlinks,
            "unreadable_files": state.source.unreadable_files,
            "invalid_utf8_records": state.source.invalid_utf8,
            "invalid_json_records": state.source.invalid_json,
            "oversized_records": state.source.oversized_lines,
            "partial_trailing_records": state.source.partial_trailing_records,
            "file_limit_reached": state.source.file_limit_reached,
            "byte_limit_reached": state.source.byte_limit_reached,
            "truncated_files": state.source.truncated_files,
        },
        "command_frequency": {
            "top_executable_families": family_rows[:20],
            "top_normalized_shapes": shape_rows[:30],
            "workload_categories": dict(sorted(workload.items())),
            "shell_tool_families": [
                {"tool": name, "invocations": count}
                for name, count in sorted(
                    shell_tool_counts.items(), key=lambda item: (-item[1], item[0])
                )
            ],
            "shape_frequency_distribution": {
                "singletons": sum(bucket.calls == 1 for bucket in shape_buckets.values()),
                "frequency_2_to_4": sum(2 <= bucket.calls <= 4 for bucket in shape_buckets.values()),
                "frequency_5_to_9": sum(5 <= bucket.calls <= 9 for bucket in shape_buckets.values()),
                "frequency_10_plus": sum(bucket.calls >= 10 for bucket in shape_buckets.values()),
            },
            "repeated_identical_invocation_excess": total_repeat_groups,
            "non_shell_tool_families": [
                {"tool": name, "calls": count}
                for name, count in sorted(
                    state.non_shell_tools.items(), key=lambda item: (-item[1], item[0])
                )[:20]
            ],
            "fingerprints": {
                shape: sorted(values, key=lambda item: item["fingerprint"])
                for shape, values in sorted(command_fingerprints.items())
            }
            if state.options.fingerprint_salt
            else {},
        },
        "output_measurement": {
            "provider_measured_uncached_input_tokens": None,
            "cache_status": "not_measured",
            "observed_model_visible_output": _summary_metrics(all_outputs),
            "total_attributed_output_bytes": call_output_bytes,
            "exclusive_command_output_bytes": exclusive_output_bytes,
            "still_unattributable_output_bytes": still_unattributable_output_bytes,
            "truncated_output_records": sum(
                item.features["truncated"] for item in all_outputs
            ),
            "binary_control_output_records": sum(
                item.features["binary_control"] for item in all_outputs
            ),
        },
        "batching": {
            "batch_tool_invocations": batch_calls,
            "dry_run_batch_invocations": deliberate_batch_calls,
            "execution_forms": dict(sorted(execution_forms.items())),
            "requested_subcommands": requested_subcommands,
            "observed_subcommand_outcomes": dict(execution),
            "dry_run_subcommands": dry_run_subcommands,
            "consecutive_direct_tool_pairs_heuristic": consecutive_pairs,
            "top_consecutive_shape_pairs_heuristic": top_pairs,
            "warning": (
                "Consecutive calls are an upper-bound heuristic only; they do not prove "
                "that a model decision was unnecessary between commands."
            ),
        },
        "opaque_attribution": attribution,
        "terse_adapters": candidate_rows,
        "smallest_safe_initial_set": [
            row["candidate_id"]
            for row in candidate_rows
            if row["safety_class"] == "safe_to_aggregate"
            and row["simulation"]["removed_observed_bytes"] > 0
        ][:3],
        "methodology": {
            "schema_migration": {
                "from_version": 1,
                "to_version": 2,
                "compatible_fields": [
                    "coverage.shell_tool_invocations",
                    "coverage.requested_underlying_subcommands",
                    "coverage.matched_shell_invocations",
                    "output_measurement.observed_model_visible_output",
                ],
                "changed_semantics": (
                    "coverage.opaque_subcommands remains the count without a "
                    "high-confidence executable attribution, but version 2 splits "
                    "that count into partial_syntactic and strict opaque forms. "
                    "Opaque diagnostics and attribution are additive sections."
                ),
            },
            "observation_token_estimate": {
                "lower_divisor_bytes_per_token": TOKEN_LOWER_DIVISOR,
                "point_divisor_bytes_per_token": TOKEN_POINT_DIVISOR,
                "upper_divisor_bytes_per_token": TOKEN_UPPER_DIVISOR,
                "warning": (
                    "These are heuristic size estimates, not tokenizer counts and not "
                    "provider-measured uncached input."
                ),
            },
            "output_attribution": (
                "Only exact session/call-id matches with one non-composite observation "
                "and one high-confidence executable are attributed. Partial syntactic "
                "segments and batch output are never multiplied across subcommands."
            ),
            "read_only": True,
        },
        "limitations": [
            "Session history size does not establish cache status or billed cost.",
            "Unmatched, composite, truncated, malformed, and unsupported records reduce confidence.",
            "Normalized shapes intentionally omit command arguments and exact paths.",
            "The analyzer does not execute, replay, upload, or inspect workspace contents.",
            "A syntactic segment is not evidence that the executable ran or produced output.",
            "The batching-pair count is not a claim that those calls could or should be batched.",
        ],
    }
    return report


def _format_int(value: int | float) -> str:
    return f"{int(value):,}"


def _markdown_table(headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> list[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(item) for item in row) + " |")
    return lines


def render_markdown(report: dict[str, Any]) -> str:
    coverage = report["coverage"]
    families = report["command_frequency"]["top_executable_families"]
    shapes = report["command_frequency"]["top_normalized_shapes"]
    adapters = report["terse_adapters"]
    attribution = report["opaque_attribution"]
    attribution_summary = attribution["summary"]
    reasons = [
        row for row in attribution["reasons"] if row["requested_commands"] > 0
    ]
    syntactic_rows = attribution["syntactic_segments"]["top_families"]
    window = report["analysis_scope"]["date_window"]
    lines = [
        "# Codex Command Frequency Report",
        "",
        "This is a privacy-safe observational summary. Raw commands, tool outputs, prompts, "
        "exact paths, and session identifiers are not included.",
        "",
        "## Scope and coverage",
        "",
        f"- Date window: `{window['since'] or 'unbounded'}` through "
        f"`{window['until'] or 'unbounded'}` (inclusive)",
        f"- Files processed: {_format_int(coverage['processed_files'])} "
        f"of {_format_int(coverage['discovered_files'])} discovered",
        f"- Sessions: {_format_int(coverage['sessions'])}; records: "
        f"{_format_int(coverage['records'])}",
        f"- Shell tool invocations: {_format_int(coverage['shell_tool_invocations'])}; "
        f"underlying subcommands: {_format_int(coverage['requested_underlying_subcommands'])}",
        f"- Result matching: {coverage['matched_shell_invocations']}/"
        f"{coverage['shell_tool_invocations']} shell invocations "
        f"({coverage['result_match_coverage']:.1%})",
        f"- Opaque command share: {coverage['parsing_unknown_share']:.1%}",
        f"- High-confidence single-command attribution: "
        f"{attribution_summary['high_confidence_family_coverage']:.1%}",
        f"- Partial syntactic-only attribution: "
        f"{attribution_summary['partial_syntax_coverage']:.1%}",
        "",
        "Skipped or incomplete records: "
        f"{coverage['invalid_json_records']} invalid JSON, "
        f"{coverage['invalid_utf8_records']} invalid UTF-8, "
        f"{coverage['oversized_records']} oversized, "
        f"{coverage['partial_trailing_records']} partial trailing, "
        f"{coverage['skipped_symlinks']} symlink, "
        f"{coverage['unreadable_files']} unreadable.",
        "",
        "## Top executable families",
        "",
    ]
    lines.extend(
        _markdown_table(
            ["Family", "Calls", "Sessions", "Direct", "Batched", "Matched", "Output bytes", "p95 bytes"],
            (
                [
                    f"`{row['family']}`",
                    _format_int(row["calls"]),
                    _format_int(row["distinct_sessions"]),
                    _format_int(row["direct_calls"]),
                    _format_int(row["batched_calls"]),
                    _format_int(row["output"]["matched_output_count"]),
                    _format_int(row["output"]["captured_model_visible_bytes"]),
                    _format_int(row["output"]["p95_bytes"]),
                ]
                for row in families
            ),
        )
    )
    lines.extend(["", "## Top normalized shapes", ""])
    lines.extend(
        _markdown_table(
            ["Shape", "Calls", "Sessions", "Matched", "Output bytes"],
            (
                [
                    f"`{row['shape']}`",
                    _format_int(row["calls"]),
                    _format_int(row["distinct_sessions"]),
                    _format_int(row["output"]["matched_output_count"]),
                    _format_int(row["output"]["captured_model_visible_bytes"]),
                ]
                for row in shapes
            ),
        )
    )
    lines.extend(
        [
            "",
            "## Opaque attribution",
            "",
            f"- Legacy v1 opaque commands: "
            f"{_format_int(attribution_summary['legacy_v1_opaque_commands'])}",
            f"- High-confidence single commands: "
            f"{_format_int(attribution_summary['high_confidence_single'])}",
            f"- Partial syntactic-only commands: "
            f"{_format_int(attribution_summary['partial_syntactic'])}",
            f"- Still unresolved opaque commands: "
            f"{_format_int(attribution_summary['unresolved_opaque'])}",
            f"- Still-unattributable matched output bytes: "
            f"{_format_int(attribution_summary['still_unattributable_output_bytes'])}",
            "",
            "A partial syntactic command identifies candidate executable families but does "
            "not prove those commands ran or produced output. Composite output remains "
            "owned by its originating invocation only.",
            "",
        ]
    )
    lines.extend(
        _markdown_table(
            [
                "Reason",
                "Commands",
                "Sessions",
                "Matched invocations",
                "Exclusive bytes",
            ],
            (
                [
                    f"`{row['reason']}`",
                    _format_int(row["requested_commands"]),
                    _format_int(row["distinct_sessions"]),
                    _format_int(row["matched_output_invocations"]),
                    _format_int(
                        row["exclusively_attributable_output"][
                            "captured_model_visible_bytes"
                        ]
                    ),
                ]
                for row in reasons
            ),
        )
    )
    lines.extend(["", "### Syntax-only segment families", ""])
    if syntactic_rows:
        lines.extend(
            _markdown_table(
                ["Family", "Shape", "Syntactic occurrences"],
                (
                    [
                        f"`{row['family']}`",
                        f"`{row['shape']}`",
                        _format_int(row["syntactic_occurrences"]),
                    ]
                    for row in syntactic_rows
                ),
            )
        )
    else:
        lines.append("No high-confidence syntactic segments were recovered.")
    lines.extend(
        [
            "",
            "## Batching observations",
            "",
            f"- Batch tool invocations: "
            f"{_format_int(report['batching']['batch_tool_invocations'])}",
            f"- Requested subcommands: "
            f"{_format_int(report['batching']['requested_subcommands'])}",
            f"- Consecutive direct-call pairs (heuristic upper bound only): "
            f"{_format_int(report['batching']['consecutive_direct_tool_pairs_heuristic'])}",
            "",
            "Consecutive calls may still require a model decision between them. Batch output "
            "is not multiplied across the commands it contains.",
            "",
            "## Terse adapter priorities",
            "",
        ]
    )
    lines.extend(
        _markdown_table(
            [
                "Adapter",
                "Safety",
                "Calls",
                "Matched",
                "Observed bytes",
                "Simulated saved bytes",
                "Likely token range",
            ],
            (
                [
                    f"`{row['candidate_id']}`",
                    row["safety_class"],
                    _format_int(row["calls"]),
                    _format_int(row["matched_output_count"]),
                    _format_int(row["observed_output_bytes"]),
                    _format_int(row["simulation"]["removed_observed_bytes"]),
                    (
                        f"{_format_int(row['simulation']['estimated_observation_token_reduction']['lower'])}"
                        f"–{_format_int(row['simulation']['estimated_observation_token_reduction']['upper'])}"
                    ),
                ]
                for row in adapters
            ),
        )
    )
    initial = report["smallest_safe_initial_set"]
    lines.extend(
        [
            "",
            "Smallest safe initial set with measured reductions: "
            + (", ".join(f"`{value}`" for value in initial) if initial else "none observed"),
            "",
            "`git diff`, source reads, package-manager diagnostics, and rich failures remain "
            "passthrough or high-risk. Terse output must preserve exit semantics and fall back "
            "byte-for-byte without rerunning a command.",
            "",
            "## Measurement limits",
            "",
            "- Tool-output bytes are the observed model-visible payload, not proof of cache status.",
            "- Token ranges are explicitly heuristic and are not provider-measured uncached input.",
            "- Composite and unmatched tool outputs are counted but not attributed to subcommands.",
            "- The analyzer is read-only and never executes extracted commands.",
            "",
        ]
    )
    return "\n".join(lines)


def build_opaque_diagnostics(report: dict[str, Any]) -> dict[str, Any]:
    attribution = report["opaque_attribution"]
    coverage = report["coverage"]
    return {
        "schema_version": report["schema_version"],
        "title": "Codex opaque command diagnostics",
        "privacy": report["privacy"],
        "analysis_scope": report["analysis_scope"],
        "coverage": {
            "processed_files": coverage["processed_files"],
            "sessions": coverage["sessions"],
            "records": coverage["records"],
            "shell_tool_invocations": coverage["shell_tool_invocations"],
            "requested_underlying_subcommands": coverage[
                "requested_underlying_subcommands"
            ],
            "matched_shell_invocations": coverage["matched_shell_invocations"],
            "legacy_v1_opaque_subcommands": coverage[
                "legacy_v1_opaque_subcommands"
            ],
            "strict_opaque_subcommands": coverage["strict_opaque_subcommands"],
            "partial_syntactic_subcommands": coverage[
                "partial_syntactic_subcommands"
            ],
        },
        "summary": attribution["summary"],
        "reconciliation": attribution["reconciliation"],
        "confidence_levels": attribution["confidence_levels"],
        "confidence": attribution["confidence"],
        "reason_precedence": attribution["reason_precedence"],
        "reasons": attribution["reasons"],
        "reason_by_execution_form": attribution["reason_by_execution_form"],
        "syntactic_segments": attribution["syntactic_segments"],
        "wrappers_recovered": attribution["wrappers_recovered"],
        "output_ownership": attribution["output_ownership"],
        "methodology": {
            "read_only": True,
            "shell_execution": False,
            "reason_taxonomy_only": True,
            "syntactic_segments_are_execution_evidence": False,
            "raw_commands_present": False,
            "raw_outputs_present": False,
        },
        "limitations": report["limitations"],
    }


def render_opaque_diagnostics_markdown(report: dict[str, Any]) -> str:
    diagnostics = build_opaque_diagnostics(report)
    summary = diagnostics["summary"]
    reasons = [
        row for row in diagnostics["reasons"] if row["requested_commands"] > 0
    ]
    confidence = diagnostics["confidence"]
    segments = diagnostics["syntactic_segments"]["top_families"]
    window = diagnostics["analysis_scope"]["date_window"]
    output = diagnostics["output_ownership"]
    lines = [
        "# Codex Opaque Command Diagnostics",
        "",
        "This is a privacy-safe, reason-only diagnostic report. It contains no raw "
        "commands, arguments, output excerpts, prompts, session IDs, environment values, "
        "or exact paths.",
        "",
        "## Scope",
        "",
        f"- Date window: `{window['since'] or 'unbounded'}` through "
        f"`{window['until'] or 'unbounded'}` (inclusive)",
        f"- Shell invocations: {_format_int(summary['shell_invocations'])}",
        f"- Requested commands: {_format_int(summary['requested_commands'])}",
        f"- Legacy v1 opaque commands: "
        f"{_format_int(summary['legacy_v1_opaque_commands'])}",
        f"- Recovered as high-confidence single commands: "
        f"{_format_int(summary['high_confidence_single'])}",
        f"- Partial syntactic-only commands: "
        f"{_format_int(summary['partial_syntactic'])}",
        f"- Strict unresolved opaque commands: "
        f"{_format_int(summary['unresolved_opaque'])}",
        f"- Reason/opaque reconciliation: "
        f"{'yes' if diagnostics['reconciliation']['reconciles_to_opaque_subcommands'] else 'no'}",
        "",
        "## Confidence",
        "",
    ]
    lines.extend(
        _markdown_table(
            ["Confidence", "Requested commands", "Share"],
            (
                [
                    f"`{row['confidence']}`",
                    _format_int(row["requested_commands"]),
                    f"{row['share']:.1%}",
                ]
                for row in confidence
            ),
        )
    )
    lines.extend(["", "## Primary reasons", ""])
    lines.extend(
        _markdown_table(
            [
                "Reason",
                "Commands",
                "Sessions",
                "Matched invocations",
                "Exclusive bytes",
                "Heuristic source tokens",
            ],
            (
                [
                    f"`{row['reason']}`",
                    _format_int(row["requested_commands"]),
                    _format_int(row["distinct_sessions"]),
                    _format_int(row["matched_output_invocations"]),
                    _format_int(
                        row["exclusively_attributable_output"][
                            "captured_model_visible_bytes"
                        ]
                    ),
                    (
                        f"{_format_int(row['source_command_token_range']['lower'])}"
                        f"–{_format_int(row['source_command_token_range']['upper'])}"
                    ),
                ]
                for row in reasons
            ),
        )
    )
    lines.extend(
        [
            "",
            "Reasons use deterministic precedence; secondary flags are included in the "
            "JSON report. Counts in this table reconcile to commands with diagnostics, "
            "not to claimed execution of every syntactic segment.",
            "",
            "## Syntax-only families",
            "",
        ]
    )
    if segments:
        lines.extend(
            _markdown_table(
                ["Family", "Shape", "Syntactic occurrences"],
                (
                    [
                        f"`{row['family']}`",
                        f"`{row['shape']}`",
                        _format_int(row["syntactic_occurrences"]),
                    ]
                    for row in segments
                ),
            )
        )
    else:
        lines.append("No unambiguous syntactic segments were recovered.")
    lines.extend(
        [
            "",
            "## Output ownership",
            "",
            f"- Matched invocation output bytes: "
            f"{_format_int(output['matched_invocation_output_bytes'])}",
            f"- Exclusively attributable bytes: "
            f"{_format_int(output['exclusively_attributable_matched_outputs']['captured_model_visible_bytes'])}",
            f"- Still-unattributable bytes: "
            f"{_format_int(output['still_unattributable_output_bytes'])}",
            "",
            output["rule"],
            "",
            "## Limits",
            "",
            "- Segment detection is lexical, not a complete POSIX/Bash parser.",
            "- The analyzer does not execute commands, evaluate expansions, or inspect files.",
            "- Token ranges are byte-derived heuristics, not provider-measured usage.",
            "",
        ]
    )
    return "\n".join(lines)


def _validate_output_dir(path: Path) -> None:
    if path.exists() and path.is_symlink():
        raise AnalysisError("output directory may not be a symlink")
    if path.exists() and not path.is_dir():
        raise AnalysisError("output path exists and is not a directory")


def write_reports(
    report: dict[str, Any], output_dir: Path
) -> tuple[Path, Path, Path, Path]:
    _validate_output_dir(output_dir)
    output_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        output_dir.chmod(0o700)
    except OSError as exc:
        raise AnalysisError(f"cannot restrict output directory permissions: {exc}") from exc
    markdown_path = output_dir / "command_frequency_report.md"
    json_path = output_dir / "command_frequency_report.json"
    diagnostics_markdown_path = output_dir / "opaque_command_diagnostics.md"
    diagnostics_json_path = output_dir / "opaque_command_diagnostics.json"
    markdown = render_markdown(report).encode("utf-8")
    machine = (json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    diagnostics = build_opaque_diagnostics(report)
    diagnostics_markdown = render_opaque_diagnostics_markdown(report).encode("utf-8")
    diagnostics_machine = (
        json.dumps(diagnostics, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    for target, content in (
        (markdown_path, markdown),
        (json_path, machine),
        (diagnostics_markdown_path, diagnostics_markdown),
        (diagnostics_json_path, diagnostics_machine),
    ):
        if target.is_symlink():
            raise AnalysisError("report target may not be a symlink")
        descriptor, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=output_dir)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
            target.chmod(0o600)
        except Exception:
            try:
                os.close(descriptor)
            except OSError:
                pass
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise
    return (
        markdown_path,
        json_path,
        diagnostics_markdown_path,
        diagnostics_json_path,
    )


def _inclusive_date(value: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--codex-home",
        type=Path,
        default=Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser(),
        help="Codex home containing sessions/ (default: CODEX_HOME or ~/.codex)",
    )
    parser.add_argument(
        "--sessions-dir",
        type=Path,
        help="override the sessions root; archived roots remain under --codex-home",
    )
    parser.add_argument("--since", type=_inclusive_date, help="inclusive YYYY-MM-DD")
    parser.add_argument("--until", type=_inclusive_date, help="inclusive YYYY-MM-DD")
    parser.add_argument(
        "--include-archived",
        action="store_true",
        help="also analyze rollout files under archived_sessions/",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-files", type=int, default=DEFAULT_MAX_FILES)
    parser.add_argument("--max-file-bytes", type=int, default=DEFAULT_MAX_FILE_BYTES)
    parser.add_argument("--max-total-bytes", type=int, default=DEFAULT_MAX_TOTAL_BYTES)
    parser.add_argument("--max-line-bytes", type=int, default=DEFAULT_MAX_LINE_BYTES)
    parser.add_argument(
        "--fingerprint-salt",
        help="optional per-run salt; enables truncated HMAC command fingerprints in JSON",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.since and args.until and args.since > args.until:
        print("analyze_codex_commands: --since cannot be after --until", file=sys.stderr)
        return 2
    options = AnalysisOptions(
        codex_home=args.codex_home.expanduser(),
        sessions_dir=args.sessions_dir.expanduser() if args.sessions_dir else None,
        output_dir=args.output_dir.expanduser(),
        since=args.since,
        until=args.until,
        include_archived=args.include_archived,
        max_files=args.max_files,
        max_file_bytes=args.max_file_bytes,
        max_total_bytes=args.max_total_bytes,
        max_line_bytes=args.max_line_bytes,
        fingerprint_salt=args.fingerprint_salt,
    )
    try:
        state = scan_rollouts(options)
        report = build_report(state)
        markdown_path, json_path, diagnostics_markdown_path, diagnostics_json_path = (
            write_reports(report, options.output_dir)
        )
    except (AnalysisError, OSError) as exc:
        print(f"analyze_codex_commands: {exc}", file=sys.stderr)
        return 2
    coverage = report["coverage"]
    print(
        "Analyzed "
        f"{coverage['shell_tool_invocations']} shell invocation(s) across "
        f"{coverage['sessions']} session(s); "
        f"{coverage['matched_shell_invocations']} matched output(s)."
    )
    print(f"Markdown: {markdown_path}")
    print(f"JSON: {json_path}")
    print(f"Diagnostics Markdown: {diagnostics_markdown_path}")
    print(f"Diagnostics JSON: {diagnostics_json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
