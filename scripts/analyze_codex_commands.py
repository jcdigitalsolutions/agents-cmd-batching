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
from codex_sequence_analysis import (
    SEQUENCE_SCHEMA_VERSION,
    TimelineEvent,
    build_sequence_analysis,
)
from codex_compilation_analysis import (
    OPERATIONS,
    SUCCESS_OUTPUT,
    TAXONOMY_VERSION,
    ValidationCommand,
    classify_validation_command,
    format_terse_failure,
)


SCHEMA_VERSION = 3
DEFAULT_MAX_FILES = 1_000
DEFAULT_MAX_FILE_BYTES = 32 * 1024 * 1024
DEFAULT_MAX_TOTAL_BYTES = 512 * 1024 * 1024
DEFAULT_MAX_LINE_BYTES = 8 * 1024 * 1024
FULL_HISTORY_MAX_FILES = 100_000
FULL_HISTORY_MAX_FILE_BYTES = 64 * 1024 * 1024
FULL_HISTORY_MAX_TOTAL_BYTES = 8 * 1024 * 1024 * 1024
FULL_HISTORY_MAX_LINE_BYTES = 16 * 1024 * 1024
DEFAULT_SIGNIFICANCE_MIN_BYTES = 100 * 1024
DEFAULT_SIGNIFICANCE_MIN_FRACTION = 0.20
TOKEN_POINT_DIVISOR = 4
TOKEN_LOWER_DIVISOR = 6
TOKEN_UPPER_DIVISOR = 3
SUCCESS_RESEARCH_CANDIDATES = ("aggressive_success", "conservative_success")
RESEARCH_CANDIDATES = (*SUCCESS_RESEARCH_CANDIDATES, "terse_failure")

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
COMMAND_ENVELOPE_RE = re.compile(
    r"\AChunk ID:[^\r\n]*\r?\n"
    r"Wall time:[^\r\n]*\r?\n"
    r"Process exited with code (-?\d+)\r?\n"
    r"Original token count: \d+\r?\n"
    r"(?:Final output|Output):\r?\n"
)
COMMAND_ENVELOPE_HEADER_RE = re.compile(r"(?m)^Chunk ID:")
COMMAND_STATUS_LINE_RE = re.compile(r"(?m)^Process exited with code -?\d+\r?$")
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
    full_history: bool = False
    max_files: int = DEFAULT_MAX_FILES
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES
    max_line_bytes: int = DEFAULT_MAX_LINE_BYTES
    significance_min_bytes: int = DEFAULT_SIGNIFICANCE_MIN_BYTES
    significance_min_fraction: float = DEFAULT_SIGNIFICANCE_MIN_FRACTION
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
    certainty: str = "unknown"
    exit_code: int | None = None
    complete: bool = True
    output_kind: str = "text"

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class OutputObservation:
    fingerprint: str
    metrics: OutputMetrics
    simulations: dict[str, OutputMetrics]
    wrapper_succeeded: int = 0
    wrapper_failed: int = 0
    text: str = field(default="", repr=False)


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
    source_key: str
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
    bundle_id: str = ""
    ordering_evidence: str = "ordered"
    output_match: str = "unmatched"
    output: OutputObservation | None = None
    status: str = "unknown"


@dataclass
class SourceStats:
    discovered_files: int = 0
    processed_files: int = 0
    eligible_files: int = 0
    inventory_files: int = 0
    inventory_bytes: int = 0
    skipped_symlinks: int = 0
    unreadable_files: int = 0
    changed_files: int = 0
    duplicate_rollout_files: int = 0
    duplicate_physical_files: int = 0
    date_excluded_files: int = 0
    archived_excluded_files: int = 0
    ignored_non_rollout_files: int = 0
    omitted_files: int = 0
    missing_roots: int = 0
    current_inventory_files: int = 0
    archived_inventory_files: int = 0
    records: int = 0
    invalid_utf8: int = 0
    invalid_json: int = 0
    oversized_lines: int = 0
    partial_trailing_records: int = 0
    file_limit_reached: bool = False
    byte_limit_reached: bool = False
    truncated_files: int = 0
    source_categories: collections.Counter[str] = field(default_factory=collections.Counter)
    omitted_by_reason: collections.Counter[str] = field(default_factory=collections.Counter)
    inventory_entries: list["InventoryFile"] = field(default_factory=list)
    missing_root_categories: list[str] = field(default_factory=list)


@dataclass
class InventoryFile:
    path: Path
    category: str
    relative_path: str
    file_id: str
    size: int
    mtime_ns: int
    device: int
    inode: int
    path_date: dt.date | None
    selected: bool = True
    processed: bool = False
    duplicate_of: str | None = None
    start_metadata: tuple[int, int, int, int] | None = None
    end_metadata: tuple[int, int, int, int] | None = None
    consumed_bytes: int = 0
    records: int = 0
    invalid_utf8: int = 0
    invalid_json: int = 0
    oversized_lines: int = 0
    partial_trailing_records: int = 0
    session_ids: set[str] = field(default_factory=set)
    omitted: bool = False
    omission_reasons: list[str] = field(default_factory=list)


@dataclass
class ScanState:
    options: AnalysisOptions
    source: SourceStats = field(default_factory=SourceStats)
    calls: list[ShellInvocation] = field(default_factory=list)
    calls_by_result_key: dict[tuple[str, str, str], list[ShellInvocation]] = field(
        default_factory=lambda: collections.defaultdict(list)
    )
    call_keys: dict[tuple[str, str, str], ShellInvocation] = field(default_factory=dict)
    outputs_by_key: dict[tuple[str, str, str], list[OutputObservation]] = field(
        default_factory=lambda: collections.defaultdict(list)
    )
    non_shell_tools: collections.Counter[str] = field(default_factory=collections.Counter)
    non_shell_call_keys: set[tuple[str, str, str]] = field(default_factory=set)
    duplicate_request_events: int = 0
    conflicting_request_events: int = 0
    malformed_arguments: int = 0
    duplicate_output_events: int = 0
    ambiguous_outputs: int = 0
    custom_bundle_count: int = 0
    serial: int = 0
    sessions_seen: set[str] = field(default_factory=set)
    source_sessions: set[tuple[str, str]] = field(default_factory=set)
    file_sessions: set[tuple[str, str]] = field(default_factory=set)
    missing_timestamps: int = 0
    timeline_events: list[TimelineEvent] = field(default_factory=list)
    timeline_sequence: int = 0


@dataclass
class ProcessedCall:
    invocations: list[ShellInvocation] = field(default_factory=list)
    non_shell_kinds: list[str] = field(default_factory=list)
    unknown: bool = False


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


def _embedded_shell_ordering(source: str) -> str:
    masked = _mask_js_strings_and_comments(source)
    if re.search(r"\bPromise\.(?:all|allSettled|race|any)\s*\(", masked):
        return "ambiguous"
    positions = [
        match.start()
        for match in re.finditer(r"\btools\.([A-Za-z_][A-Za-z0-9_]*)\s*\(", masked)
        if match.group(1) in SHELL_TOOL_NAMES | NATIVE_BATCH_TOOL_NAMES
    ]
    if len(positions) <= 1:
        return "ordered"
    if all(
        re.search(r"\bawait\s*$", masked[max(0, position - 80) : position])
        for position in positions
    ):
        return "ordered"
    return "ambiguous"


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
    source_key: str,
    session_id: str,
    timestamp: str,
    call_id: str,
    result_key: str,
    plan: InvocationPlan,
    parent_mixed: bool = False,
    bundle_id: str = "",
    ordering_evidence: str = "ordered",
) -> ShellInvocation | None:
    signature = (
        plan.tool_name,
        plan.execution_form,
        plan.dry_run,
        tuple(command.raw for command in plan.subcommands),
        bundle_id,
        ordering_evidence,
    )
    key = (source_key, session_id, call_id)
    existing = state.call_keys.get(key)
    if existing is not None:
        if existing.duplicate_signature == signature:
            state.duplicate_request_events += 1
        else:
            state.conflicting_request_events += 1
            existing.output_match = "ambiguous_request"
        return None
    state.serial += 1
    invocation = ShellInvocation(
        source_key=source_key,
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
        bundle_id=bundle_id,
        ordering_evidence=ordering_evidence,
    )
    state.call_keys[key] = invocation
    state.calls_by_result_key[key[:-1] + (result_key,)].append(invocation)
    state.calls.append(invocation)
    state.sessions_seen.add(session_id)
    state.source_sessions.add((source_key, session_id))
    return invocation


def _project_category() -> str:
    return "workspace"


def _process_call_payload(
    state: ScanState,
    *,
    source_key: str,
    session_id: str,
    timestamp: str,
    payload: dict[str, Any],
) -> ProcessedCall:
    processed = ProcessedCall()
    call_type = payload.get("type")
    if call_type not in {"function_call", "custom_tool_call"}:
        return processed
    call_id = payload.get("call_id")
    if not isinstance(call_id, str) or not call_id:
        state.malformed_arguments += 1
        processed.unknown = True
        return processed
    name = _normal_tool_name(payload.get("name"))

    if call_type == "function_call":
        arguments, malformed = _raw_arguments(payload)
        if malformed or arguments is None:
            state.malformed_arguments += 1
            if name in SHELL_TOOL_NAMES | NATIVE_BATCH_TOOL_NAMES:
                processed.unknown = True
                return processed
        else:
            plan = _plan_invocation(name, arguments)
            if plan is not None:
                invocation = _add_invocation(
                    state,
                    source_key=source_key,
                    session_id=session_id,
                    timestamp=timestamp,
                    call_id=call_id,
                    result_key=call_id,
                    plan=plan,
                )
                if invocation is not None:
                    processed.invocations.append(invocation)
                return processed
            if name in SHELL_TOOL_NAMES | NATIVE_BATCH_TOOL_NAMES:
                processed.unknown = True
                return processed
        state.non_shell_tools[name] += 1
        state.non_shell_call_keys.add((source_key, session_id, call_id))
        processed.non_shell_kinds.append(
            "edit" if name == "apply_patch" else "non_shell_call"
        )
        return processed

    raw_input = payload.get("input")
    if name == "exec" and isinstance(raw_input, str):
        state.custom_bundle_count += 1
        embedded, failures = _extract_embedded_tool_calls(raw_input)
        state.malformed_arguments += failures
        if failures:
            processed.unknown = True
        shell_calls: list[tuple[str, dict[str, Any]]] = []
        non_shell = 0
        for embedded_name, arguments in embedded:
            normalized = _normal_tool_name(embedded_name)
            if normalized in SHELL_TOOL_NAMES | NATIVE_BATCH_TOOL_NAMES:
                shell_calls.append((normalized, arguments))
            else:
                non_shell += 1
                state.non_shell_tools[normalized] += 1
                processed.non_shell_kinds.append(
                    "edit" if normalized == "apply_patch" else "non_shell_call"
                )
        bundle_ordering = _embedded_shell_ordering(raw_input)
        if bundle_ordering == "ambiguous":
            processed.unknown = True
        for index, (embedded_name, arguments) in enumerate(shell_calls):
            plan = _plan_invocation(embedded_name, arguments)
            if plan is None:
                state.malformed_arguments += 1
                processed.unknown = True
                continue
            invocation = _add_invocation(
                state,
                source_key=source_key,
                session_id=session_id,
                timestamp=timestamp,
                call_id=f"{call_id}#{index}",
                result_key=call_id,
                plan=plan,
                parent_mixed=non_shell > 0 or len(shell_calls) > 1,
                bundle_id=call_id,
                ordering_evidence=bundle_ordering,
            )
            if invocation is not None:
                processed.invocations.append(invocation)
        if not shell_calls:
            state.non_shell_tools["exec"] += 1
            state.non_shell_call_keys.add((source_key, session_id, call_id))
            if not processed.non_shell_kinds:
                processed.non_shell_kinds.append("non_shell_call")
        return processed

    if isinstance(raw_input, str):
        try:
            parsed = json.loads(raw_input)
        except (json.JSONDecodeError, ValueError):
            parsed = None
        if isinstance(parsed, dict):
            plan = _plan_invocation(name, parsed)
            if plan is not None:
                invocation = _add_invocation(
                    state,
                    source_key=source_key,
                    session_id=session_id,
                    timestamp=timestamp,
                    call_id=call_id,
                    result_key=call_id,
                    plan=plan,
                )
                if invocation is not None:
                    processed.invocations.append(invocation)
                return processed
            if name in SHELL_TOOL_NAMES | NATIVE_BATCH_TOOL_NAMES:
                processed.unknown = True
                return processed
    state.non_shell_tools[name] += 1
    state.non_shell_call_keys.add((source_key, session_id, call_id))
    processed.non_shell_kinds.append(
        "edit" if name == "apply_patch" else "non_shell_call"
    )
    return processed


def _detect_status(text: str) -> str:
    certainty = _status_certainty(text, _authoritative_exit_code(text), True)
    if certainty.startswith("success"):
        return "success"
    if certainty.startswith("failure") or certainty == "timeout":
        return "failed"
    return "unknown"


def _authoritative_exit_code(text: str) -> int | None:
    envelope = _command_envelope(text)
    if envelope is not None:
        return int(envelope.group(1))
    value = text.rstrip()
    matches = list(
        re.finditer(
            r"(?:^|\n)(?:Process\s+)?exited\s+with\s+code\s+(-?\d+)\s*$",
            value,
            re.I,
        )
    )
    if len(matches) == 1:
        return int(matches[0].group(1))
    return None


def _command_envelope(text: str) -> re.Match[str] | None:
    envelope = COMMAND_ENVELOPE_RE.match(text)
    if (
        envelope is None
        or len(COMMAND_ENVELOPE_HEADER_RE.findall(text)) != 1
        or len(COMMAND_STATUS_LINE_RE.findall(text)) != 1
    ):
        return None
    return envelope


def _command_envelope_content(text: str) -> str:
    envelope = _command_envelope(text)
    if envelope is None:
        return text
    return text[envelope.end() :]


def _status_certainty(
    text: str,
    exit_code: int | None,
    complete: bool,
) -> str:
    lower = text.lower()
    if (
        any(
            marker in lower
            for marker in (
                "cancelled before completion",
                "canceled before completion",
                "command cancelled",
                "operation cancelled",
            )
        )
        or re.search(
            r'"(?:status|state)"\s*:\s*"(?:cancelled|canceled)"',
            lower,
        )
        or re.search(r'"(?:cancelled|canceled)"\s*:\s*true', lower)
    ):
        return "cancelled"
    if (
        any(
            marker in lower
            for marker in ("timed out", "timeout exceeded", "deadline exceeded")
        )
        or re.search(
            r'"(?:status|state)"\s*:\s*"(?:timed_out|timeout|timedout)"',
            lower,
        )
        or re.search(r'"(?:timed_out|timeout)"\s*:\s*true', lower)
    ):
        return "timeout"
    if exit_code == 0:
        return "success_verified"
    if exit_code is not None:
        return "failed_verified"
    if not complete:
        return "unknown"
    if _has_failure(text):
        return "failure_text_inferred"
    if any(marker in lower for marker in SUCCESS_MARKERS):
        return "success_text_inferred"
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
        "errors": "error:" in lower or "error[" in lower or "npm err!" in lower,
        "diagnostic_notes": bool(re.search(r"(?:^|\n)\s*(?:note|help):", lower)),
        "stack_trace": "traceback (most recent call last)" in lower or "panicked at" in lower,
        "assertion_location": bool(re.search(r"\bassert(?:ion)?\b", text, re.I)),
        "skipped_tests": bool(re.search(r"\b\d+\s+(?:skipped|ignored)\b", lower)),
        "xfail": "xfail" in lower or "expected failure" in lower,
        "deprecated": "deprecated" in lower,
        "no_tests": bool(
            re.search(
                r"(?:"
                r"\brunning\s+0\s+tests?\b"
                r"|\bno\s+tests?\s+(?:ran|collected|found|to\s+run)\b"
                r"|\bno\s+test\s+files?(?:\s+found)?\b"
                r"|\[no\s+test\s+files?\]"
                r"|\b0\s+tests?\b"
                r")",
                lower,
            )
        ),
        "interactive_prompt": bool(
            re.search(r"(?:^|\n)\s*(?:yes/no|continue\?|press any key|password:)", lower)
        ),
        "uncertainty": any(
            marker in lower
            for marker in (
                "may have failed",
                "status unknown",
                "completion unknown",
                "partial output",
            )
        ),
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
        text += _structured_terminal_marker(value)
    return text, stdout_bytes, stderr_bytes


def _structured_terminal_marker(value: dict[str, Any]) -> str:
    candidates = [value]
    metadata = value.get("metadata")
    if isinstance(metadata, dict):
        candidates.append(metadata)
    for candidate in candidates:
        if candidate.get("cancelled") is True or candidate.get("canceled") is True:
            return "command cancelled\n"
        status = candidate.get("status") or candidate.get("state")
        if isinstance(status, str) and status.lower() in {"cancelled", "canceled"}:
            return "command cancelled\n"
    for candidate in candidates:
        if candidate.get("timed_out") is True or candidate.get("timeout") is True:
            return "command timed out\n"
        status = candidate.get("status") or candidate.get("state")
        if isinstance(status, str) and status.lower() in {
            "timed_out",
            "timeout",
            "timedout",
        }:
            return "command timed out\n"
    return ""


def _structured_is_incomplete(value: dict[str, Any]) -> bool:
    candidates = [value]
    metadata = value.get("metadata")
    if isinstance(metadata, dict):
        candidates.append(metadata)
    for candidate in candidates:
        for key in (
            "truncated",
            "is_truncated",
            "output_truncated",
            "partial",
            "is_partial",
        ):
            if candidate.get(key) is True:
                return True
        if candidate.get("complete") is False:
            return True
    return False


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
            elif isinstance(item, dict):
                if isinstance(item.get("text"), str):
                    parts.append(item["text"])
                marker = _structured_terminal_marker(item)
                if marker:
                    parts.append(marker)
        return "".join(parts), None, None
    if isinstance(value, dict):
        return _parse_structured_output(value)
    return str(value), None, None


def _model_visible_output(
    value: Any,
) -> tuple[str, int | None, int | None, int | None, str, bool]:
    text, stdout_bytes, stderr_bytes = _model_visible_text(value)
    exit_code: int | None = None
    output_kind = "text"
    complete = True
    if isinstance(value, dict):
        output_kind = "structured"
        candidate = value.get("exit_code")
        if isinstance(candidate, int) and not isinstance(candidate, bool):
            exit_code = candidate
        if _structured_is_incomplete(value):
            complete = False
    elif isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            parsed = None
        if isinstance(parsed, dict):
            output_kind = "serialized_structured"
            candidate = parsed.get("exit_code")
            if isinstance(candidate, int) and not isinstance(candidate, bool):
                exit_code = candidate
            terminal_marker = _structured_terminal_marker(parsed)
            if terminal_marker:
                text += "\n" + terminal_marker
            if _structured_is_incomplete(parsed):
                complete = False
    elif isinstance(value, list):
        output_kind = "content_list"
    else:
        output_kind = "other"
    if exit_code is None:
        exit_code = _authoritative_exit_code(text)
    features = _structural_features(text)
    if features["truncated"]:
        complete = False
    envelope = _command_envelope(text)
    if envelope is not None:
        output_kind = "command_tool_envelope"
        stdout_bytes = len(text[envelope.end() :].encode("utf-8"))
        stderr_bytes = None
        features["command_tool_envelope"] = True
    return text, stdout_bytes, stderr_bytes, exit_code, output_kind, complete


def _metrics_for_text(
    text: str,
    *,
    stdout_bytes: int | None = None,
    stderr_bytes: int | None = None,
    exit_code: int | None = None,
    complete: bool = True,
    output_kind: str = "text",
) -> OutputMetrics:
    certainty = _status_certainty(text, exit_code, complete)
    legacy_status = (
        "success"
        if certainty.startswith("success")
        else "failed"
        if certainty.startswith("failure") or certainty == "timeout"
        else "unknown"
    )
    features = _structural_features(text)
    if (stderr_bytes or 0) > 0:
        features["stderr_present"] = True
    if (stdout_bytes or 0) > 0 and (stderr_bytes or 0) > 0:
        features["separate_stdout_and_stderr"] = True
    return OutputMetrics(
        bytes=len(text.encode("utf-8")),
        chars=len(text),
        lines=len(text.splitlines()),
        status=legacy_status,
        features=features,
        stdout_bytes=stdout_bytes,
        stderr_bytes=stderr_bytes,
        certainty=certainty,
        exit_code=exit_code,
        complete=complete,
        output_kind=output_kind,
    )


def _make_output_observation(value: Any) -> OutputObservation:
    text, stdout_bytes, stderr_bytes, exit_code, output_kind, complete = (
        _model_visible_output(value)
    )
    analysis_text = _command_envelope_content(text)
    metrics = _metrics_for_text(
        text,
        stdout_bytes=stdout_bytes,
        stderr_bytes=stderr_bytes,
        exit_code=exit_code,
        complete=complete,
        output_kind=output_kind,
    )
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
    succeeded = len(re.findall(r"\[delayed-seq\] command \d+/\d+: succeeded", text))
    failed = len(re.findall(r"\[delayed-seq\] command \d+/\d+: failed", text))
    return OutputObservation(
        fingerprint=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        metrics=metrics,
        simulations=simulations,
        wrapper_succeeded=succeeded,
        wrapper_failed=failed,
        text=analysis_text,
    )


def _process_output_payload(
    state: ScanState,
    *,
    source_key: str,
    session_id: str,
    payload: dict[str, Any],
) -> str:
    if payload.get("type") not in {"function_call_output", "custom_tool_call_output"}:
        return "none"
    call_id = payload.get("call_id")
    if not isinstance(call_id, str) or not call_id or "output" not in payload:
        state.malformed_arguments += 1
        return "unknown"
    observation = _make_output_observation(payload["output"])
    key = (source_key, session_id, call_id)
    existing = state.outputs_by_key.get(key, [])
    if existing:
        if existing[0].fingerprint == observation.fingerprint:
            state.duplicate_output_events += 1
            return "duplicate"
        else:
            state.ambiguous_outputs += 1
            existing.append(observation)
            return "unknown"
    state.outputs_by_key[key].append(observation)
    if key in state.calls_by_result_key:
        return "shell_output"
    if key in state.non_shell_call_keys:
        return "non_shell_output"
    return "unknown"


def _session_fallback(path: Path) -> str:
    return hashlib.sha256(path.name.encode("utf-8")).hexdigest()


def _turn_id(payload: dict[str, Any]) -> str | None:
    value = payload.get("turn_id")
    return value if isinstance(value, str) and value else None


def _add_timeline_event(
    state: ScanState,
    *,
    source_key: str,
    session_id: str,
    record_index: int,
    timestamp: str,
    kind: str,
    call_id: str = "",
    invocation_serial: int | None = None,
    response_id: str | None = None,
    turn_id: str | None = None,
    bundle_id: str | None = None,
    ordering_evidence: str = "ordered",
) -> None:
    state.timeline_sequence += 1
    state.timeline_events.append(
        TimelineEvent(
            sequence_index=state.timeline_sequence,
            source_key=source_key,
            session_id=session_id,
            record_index=record_index,
            timestamp=timestamp,
            kind=kind,
            call_id=call_id,
            invocation_serial=invocation_serial,
            response_id=response_id,
            turn_id=turn_id,
            bundle_id=bundle_id,
            ordering_evidence=ordering_evidence,
        )
    )


def _timeline_item_completed_kind(payload: dict[str, Any]) -> str | None:
    item = payload.get("item")
    if not isinstance(item, dict):
        return "other"
    item_type = item.get("type")
    if item_type == "UserMessage":
        return "user_turn"
    if item_type in {"Reasoning", "AgentMessage"}:
        return "assistant_decision_or_message"
    if item_type == "FileChange":
        return "edit"
    if item_type == "CommandExecution":
        return "shell_output"
    if item_type == "PatchApply":
        return "edit"
    if item_type in {
        "McpToolCall",
        "CollabAgentToolCall",
        "SubAgentActivity",
        "Extension",
        "ImageView",
    }:
        return "non_shell_output"
    if item_type == "ContextCompaction":
        return "turn_boundary"
    return "other"


def _emit_record_timeline(
    state: ScanState,
    *,
    row: dict[str, Any],
    payload: dict[str, Any],
    source_key: str,
    session_id: str,
    record_index: int,
    timestamp: str,
) -> None:
    row_type = row.get("type")
    common = {
        "source_key": source_key,
        "session_id": session_id,
        "record_index": record_index,
        "timestamp": timestamp,
        "turn_id": _turn_id(payload),
    }
    if row_type == "token_usage_record":
        response_id = payload.get("response_id")
        if isinstance(response_id, str) and response_id:
            _add_timeline_event(
                state,
                kind="response_boundary",
                response_id=response_id,
                **common,
            )
        return
    if row_type == "turn_context":
        if _turn_id(payload) is not None:
            _add_timeline_event(state, kind="turn_boundary", **common)
        return
    if row_type == "event_msg":
        event_type = payload.get("type")
        if event_type in {"task_started", "task_complete", "turn_aborted"}:
            _add_timeline_event(state, kind="turn_boundary", **common)
        elif event_type == "item_completed":
            kind = _timeline_item_completed_kind(payload)
            if kind is not None:
                _add_timeline_event(state, kind=kind, **common)
        return
    if row_type != "response_item":
        return

    payload_type = payload.get("type")
    call_id = payload.get("call_id")
    safe_call_id = call_id if isinstance(call_id, str) else ""
    if payload_type in {"function_call", "custom_tool_call"}:
        processed = _process_call_payload(
            state,
            source_key=source_key,
            session_id=session_id,
            timestamp=timestamp,
            payload=payload,
        )
        for invocation in processed.invocations:
            _add_timeline_event(
                state,
                kind="shell_call",
                call_id=invocation.call_id,
                invocation_serial=invocation.serial,
                bundle_id=invocation.bundle_id or None,
                ordering_evidence=invocation.ordering_evidence,
                **common,
            )
        for kind in processed.non_shell_kinds:
            _add_timeline_event(state, kind=kind, call_id=safe_call_id, **common)
        if processed.unknown:
            _add_timeline_event(state, kind="unknown", call_id=safe_call_id, **common)
        return
    if payload_type in {"function_call_output", "custom_tool_call_output"}:
        kind = _process_output_payload(
            state,
            source_key=source_key,
            session_id=session_id,
            payload=payload,
        )
        if kind in {"none", "duplicate"}:
            return
        serial = None
        matching = state.calls_by_result_key.get(
            (source_key, session_id, safe_call_id),
            [],
        )
        if len(matching) == 1:
            serial = matching[0].serial
        _add_timeline_event(
            state,
            kind=kind,
            call_id=safe_call_id,
            invocation_serial=serial,
            **common,
        )
        return
    if payload_type == "reasoning":
        kind = "assistant_decision_or_message"
    elif payload_type == "message":
        role = payload.get("role")
        if role == "user":
            kind = "user_turn"
        elif role == "assistant":
            kind = "assistant_decision_or_message"
        else:
            kind = "other"
    elif payload_type in {"agent_message", "compaction"}:
        kind = "assistant_decision_or_message"
    else:
        kind = "other"
    _add_timeline_event(state, kind=kind, call_id=safe_call_id, **common)


def _process_record(
    state: ScanState,
    *,
    row: dict[str, Any],
    session_id: str,
    timestamp: str,
    source_key: str,
    record_index: int,
) -> str:
    if row.get("type") == "session_meta" and isinstance(row.get("payload"), dict):
        payload = row["payload"]
        discovered = payload.get("session_id") or payload.get("id")
        if isinstance(discovered, str) and discovered:
            session_id = discovered
            state.sessions_seen.add(session_id)
            state.source_sessions.add((source_key, session_id))
    payload = row.get("payload")
    has_date_filter = state.options.since is not None or state.options.until is not None
    if has_date_filter and _date_from_timestamp(timestamp) is None:
        state.missing_timestamps += 1
    in_window = _within_window(timestamp, state.options)
    if isinstance(payload, dict) and in_window:
        _emit_record_timeline(
            state,
            row=row,
            payload=payload,
            source_key=source_key,
            session_id=session_id,
            record_index=record_index,
            timestamp=timestamp,
        )
    return session_id


def _iter_rollout_files(root: Path, category: str, state: ScanState):
    for entry in _inventory_root(root, category, state, selected=True):
        if entry.selected:
            yield entry


def _file_id(category: str, relative_path: str) -> str:
    return hashlib.sha256(
        f"{category}\0{relative_path}".encode("utf-8")
    ).hexdigest()[:24]


def _file_metadata(path: Path) -> tuple[int, int, int, int]:
    metadata = path.stat(follow_symlinks=False)
    return metadata.st_size, metadata.st_mtime_ns, metadata.st_dev, metadata.st_ino


def _open_regular_file(path: Path) -> tuple[Any, tuple[int, int, int, int]]:
    flags = os.O_RDONLY
    for name in ("O_CLOEXEC", "O_NOFOLLOW", "O_NONBLOCK"):
        flags |= getattr(os, name, 0)
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise OSError("rollout path is not a regular file")
        snapshot = (
            metadata.st_size,
            metadata.st_mtime_ns,
            metadata.st_dev,
            metadata.st_ino,
        )
        return os.fdopen(descriptor, "rb"), snapshot
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise


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


def _inventory_root(
    root: Path,
    category: str,
    state: ScanState,
    *,
    selected: bool,
) -> list[InventoryFile]:
    try:
        root_metadata = root.lstat()
    except FileNotFoundError:
        if selected:
            state.source.missing_roots += 1
            state.source.missing_root_categories.append(category)
            state.source.omitted_by_reason["missing_root"] += 1
        return []
    except OSError:
        if selected:
            state.source.unreadable_files += 1
            state.source.omitted_by_reason["unreadable_root"] += 1
        return []
    if stat.S_ISLNK(root_metadata.st_mode):
        if selected:
            state.source.skipped_symlinks += 1
            state.source.omitted_by_reason["symlink_root"] += 1
        return []
    if not stat.S_ISDIR(root_metadata.st_mode):
        raise AnalysisError(f"{category} root is not a directory")
    resolved_root = root.resolve(strict=False)
    entries: list[InventoryFile] = []

    def onerror(_error: OSError) -> None:
        if selected:
            state.source.unreadable_files += 1
            state.source.omitted_by_reason["unreadable_directory"] += 1

    try:
        walker = os.walk(root, followlinks=False, onerror=onerror)
        for current, directories, files in walker:
            directories.sort()
            files.sort()
            for directory in list(directories):
                path = Path(current) / directory
                if path.is_symlink():
                    if selected:
                        state.source.skipped_symlinks += 1
                        state.source.omitted_by_reason["symlink_directory"] += 1
                    directories.remove(directory)
            for name in files:
                path = Path(current) / name
                if path.is_symlink():
                    if selected:
                        state.source.skipped_symlinks += 1
                        state.source.omitted_by_reason["symlink_file"] += 1
                    continue
                if not re.fullmatch(r"rollout-.*\.jsonl", name):
                    state.source.ignored_non_rollout_files += 1
                    continue
                try:
                    resolved = path.resolve(strict=False)
                    if not resolved.is_relative_to(resolved_root):
                        state.source.skipped_symlinks += 1
                        state.source.omitted_by_reason["root_escape"] += 1
                        continue
                    metadata = path.stat(follow_symlinks=False)
                except OSError:
                    if selected:
                        state.source.inventory_files += 1
                        state.source.omitted_files += 1
                        if category == "sessions":
                            state.source.current_inventory_files += 1
                        else:
                            state.source.archived_inventory_files += 1
                    if selected:
                        state.source.unreadable_files += 1
                        state.source.omitted_by_reason["unreadable_file"] += 1
                    continue
                if not stat.S_ISREG(metadata.st_mode):
                    state.source.ignored_non_rollout_files += 1
                    continue
                relative = path.relative_to(root).as_posix()
                entry = InventoryFile(
                    path=path,
                    category=category,
                    relative_path=relative,
                    file_id=_file_id(category, relative),
                    size=metadata.st_size,
                    mtime_ns=metadata.st_mtime_ns,
                    device=metadata.st_dev,
                    inode=metadata.st_ino,
                    path_date=_rollout_path_date(path),
                    selected=selected,
                )
                entries.append(entry)
    except OSError:
        if selected:
            state.source.unreadable_files += 1
            state.source.omitted_by_reason["unreadable_directory"] += 1
    return entries


def _inventory_rollouts(options: AnalysisOptions, state: ScanState) -> list[InventoryFile]:
    sessions_root = options.sessions_dir or options.codex_home / "sessions"
    roots = [
        (sessions_root, "sessions", True),
        (
            options.codex_home / "archived_sessions",
            "archived_sessions",
            options.include_archived or options.full_history,
        ),
    ]
    entries: list[InventoryFile] = []
    for root, category, selected_root in roots:
        entries.extend(
            _inventory_root(root, category, state, selected=selected_root)
        )

    candidates: list[InventoryFile] = []
    physical_seen: dict[tuple[int, int], str] = {}
    for entry in entries:
        state.source.inventory_files += 1
        state.source.inventory_bytes += entry.size
        if entry.category == "sessions":
            state.source.current_inventory_files += 1
        else:
            state.source.archived_inventory_files += 1
        if not entry.selected:
            if entry.category == "archived_sessions":
                state.source.archived_excluded_files += 1
                state.source.omitted_by_reason["archive_not_requested"] += 1
            continue
        if _path_outside_window(entry.path, options):
            entry.selected = False
            state.source.date_excluded_files += 1
            state.source.omitted_by_reason["date_filter"] += 1
            continue
        physical_key = (entry.device, entry.inode)
        previous = physical_seen.get(physical_key)
        if previous is not None:
            entry.selected = False
            entry.duplicate_of = previous
            state.source.duplicate_physical_files += 1
            _omit_file(state, entry, "duplicate_physical_file")
            continue
        physical_seen[physical_key] = entry.file_id
        candidates.append(entry)

    by_size: dict[int, list[InventoryFile]] = collections.defaultdict(list)
    for entry in candidates:
        by_size[entry.size].append(entry)
    for same_size in by_size.values():
        if len(same_size) < 2:
            continue
        first_by_digest: dict[str, InventoryFile] = {}
        for entry in same_size:
            digest = hashlib.sha256()
            try:
                handle, start_metadata = _open_regular_file(entry.path)
                with handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(chunk)
                    end_metadata = _file_metadata(entry.path)
            except OSError:
                entry.selected = False
                state.source.unreadable_files += 1
                _omit_file(state, entry, "unreadable_during_inventory")
                continue
            if start_metadata != end_metadata:
                entry.selected = False
                state.source.changed_files += 1
                _omit_file(state, entry, "file_changed_during_inventory")
                continue
            previous = first_by_digest.get(digest.hexdigest())
            if previous is None:
                first_by_digest[digest.hexdigest()] = entry
            else:
                entry.selected = False
                entry.duplicate_of = previous.file_id
                state.source.duplicate_rollout_files += 1
                state.source.omitted_by_reason["exact_duplicate_content"] += 1
                state.source.omitted_files += 1

    state.source.inventory_entries = entries
    state.source.eligible_files = sum(entry.selected for entry in entries)
    state.source.discovered_files = sum(entry.selected for entry in entries)
    return [entry for entry in entries if entry.selected]


def _omit_file(
    state: ScanState,
    entry: InventoryFile,
    reason: str,
) -> None:
    if not entry.omitted:
        state.source.omitted_files += 1
        entry.omitted = True
    if reason not in entry.omission_reasons:
        entry.omission_reasons.append(reason)
    state.source.omitted_by_reason[reason] += 1


def _read_file(
    entry: InventoryFile,
    state: ScanState,
    remaining_total: int,
) -> int:
    path = entry.path
    category = entry.category
    budget = min(state.options.max_file_bytes, remaining_total)
    if budget <= 0:
        state.source.byte_limit_reached = True
        _omit_file(state, entry, "total_byte_cap")
        return 0
    consumed = 0
    session_id = _session_fallback(path)
    source_key = hashlib.sha256(
        f"{category}\0{path.resolve(strict=False)}".encode("utf-8")
    ).hexdigest()
    record_index = -1
    try:
        handle, entry.start_metadata = _open_regular_file(path)
    except OSError:
        state.source.unreadable_files += 1
        _omit_file(state, entry, "unreadable_file")
        return 0
    entry.processed = True
    state.source.processed_files += 1
    state.source.source_categories[category] += 1
    with handle:
        while consumed < budget:
            allowed = min(state.options.max_line_bytes + 1, budget - consumed)
            raw = handle.readline(allowed)
            if not raw:
                break
            consumed += len(raw)
            record_index += 1
            record_bytes = len(raw) - 1 if raw.endswith(b"\n") else len(raw)
            if record_bytes > state.options.max_line_bytes:
                state.source.oversized_lines += 1
                entry.oversized_lines += 1
                while not raw.endswith(b"\n") and consumed < budget:
                    extra = handle.readline(min(64 * 1024, budget - consumed))
                    if not extra:
                        break
                    consumed += len(extra)
                    raw = extra
                _add_timeline_event(
                    state,
                    source_key=source_key,
                    session_id=session_id,
                    record_index=record_index,
                    timestamp="",
                    kind="unknown",
                )
                continue
            partial = not raw.endswith(b"\n")
            if partial:
                state.source.partial_trailing_records += 1
                entry.partial_trailing_records += 1
            try:
                line = raw.decode("utf-8")
            except UnicodeDecodeError:
                state.source.invalid_utf8 += 1
                entry.invalid_utf8 += 1
                _add_timeline_event(
                    state,
                    source_key=source_key,
                    session_id=session_id,
                    record_index=record_index,
                    timestamp="",
                    kind="unknown",
                )
                continue
            try:
                row = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                state.source.invalid_json += 1
                entry.invalid_json += 1
                _add_timeline_event(
                    state,
                    source_key=source_key,
                    session_id=session_id,
                    record_index=record_index,
                    timestamp="",
                    kind="unknown",
                )
                continue
            if not isinstance(row, dict):
                state.source.invalid_json += 1
                entry.invalid_json += 1
                _add_timeline_event(
                    state,
                    source_key=source_key,
                    session_id=session_id,
                    record_index=record_index,
                    timestamp="",
                    kind="unknown",
                )
                continue
            state.source.records += 1
            entry.records += 1
            timestamp = row.get("timestamp")
            timestamp_text = timestamp if isinstance(timestamp, str) else ""
            session_id = _process_record(
                state,
                row=row,
                session_id=session_id,
                timestamp=timestamp_text,
                source_key=source_key,
                record_index=record_index,
            )
            entry.session_ids.add(session_id)
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
                    _omit_file(state, entry, "total_byte_cap")
                else:
                    state.source.truncated_files += 1
                    _omit_file(state, entry, "per_file_byte_cap")
        elif budget < entry.size:
            state.source.truncated_files += 1
            _omit_file(state, entry, "per_file_byte_cap")
    entry.consumed_bytes = consumed
    try:
        entry.end_metadata = _file_metadata(path)
    except OSError:
        state.source.changed_files += 1
        _omit_file(state, entry, "metadata_changed_during_scan")
    else:
        if entry.start_metadata != entry.end_metadata:
            state.source.changed_files += 1
            _omit_file(state, entry, "file_changed_during_scan")
    return consumed


def scan_rollouts(options: AnalysisOptions) -> ScanState:
    if options.max_files <= 0 or options.max_file_bytes <= 0 or options.max_total_bytes <= 0:
        raise AnalysisError("file and byte limits must be positive")
    if options.max_line_bytes <= 0:
        raise AnalysisError("max line bytes must be positive")
    state = ScanState(options=options)
    entries = _inventory_rollouts(options, state)
    consumed_total = 0
    for index, entry in enumerate(entries):
        if state.source.processed_files >= options.max_files:
            state.source.file_limit_reached = True
            for omitted in entries[index:]:
                if omitted.selected and not omitted.processed:
                    _omit_file(state, omitted, "file_count_cap")
            break
        if consumed_total >= options.max_total_bytes:
            state.source.byte_limit_reached = True
            for omitted in entries[index:]:
                if omitted.selected and not omitted.processed:
                    _omit_file(state, omitted, "total_byte_cap")
            break
        consumed = _read_file(
            entry,
            state,
            options.max_total_bytes - consumed_total,
        )
        consumed_total += consumed
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
    output_kinds = collections.Counter(item.output_kind for item in items)
    feature_counts: collections.Counter[str] = collections.Counter()
    for item in items:
        feature_counts.update(name for name, present in item.features.items() if present)
    streams = [
        (item.stdout_bytes or 0) + (item.stderr_bytes or 0)
        for item in items
        if item.stdout_bytes is not None or item.stderr_bytes is not None
    ]
    envelope_bytes = sum(
        max(
            0,
            item.bytes
            - (item.stdout_bytes or 0)
            - (item.stderr_bytes or 0),
        )
        for item in items
        if item.output_kind == "command_tool_envelope"
    )
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
        "output_kind_counts": dict(sorted(output_kinds.items())),
        "status_certainty_counts": dict(
            sorted(
                collections.Counter(item.certainty for item in items).items()
            )
        ),
        "structural_feature_counts": dict(sorted(feature_counts.items())),
        "separate_stream_observations": len(streams),
        "separate_stream_bytes": sum(streams),
        "command_tool_envelope_bytes": envelope_bytes,
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


def _success_rejection_reason(
    command: ValidationCommand,
    metrics: OutputMetrics,
    text: str,
) -> str | None:
    if not command.formatter_eligible:
        return "no_reviewed_success_formatter"
    if metrics.certainty != "success_verified":
        return "not_authoritatively_verified"
    if not metrics.complete:
        return "incomplete_or_truncated"
    if _has_failure(text):
        return "failure_marker"
    blocked = (
        "binary_control",
        "warnings",
        "errors",
        "skipped_tests",
        "xfail",
        "deprecated",
        "interactive_prompt",
        "uncertainty",
        "no_tests",
        "stack_trace",
        "diagnostic_notes",
        "truncated",
        "stderr_present",
    )
    for feature in blocked:
        if metrics.features.get(feature):
            return feature
    if (
        metrics.bytes <= len(SUCCESS_OUTPUT.encode("utf-8"))
        or (
            metrics.stdout_bytes == 0
            and metrics.stderr_bytes in {None, 0}
        )
    ):
        return "zero_or_too_small"
    if not _success_output_shape_supported(command, metrics, text=text):
        return "unrecognized_success_stdout"
    return None


def _success_output_shape_supported(
    command: ValidationCommand,
    metrics: OutputMetrics,
    *,
    text: str | None,
) -> bool:
    if text is None:
        return True
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return True
    if command.operation == "test" and not re.search(
        r"(?:\b\d+\s+passed\b|test result:\s*ok\b|\bPASS\b|"
        r"^ok\s+\S+|Tests:\s+.*\bpassed\b)",
        text,
        re.M | re.I,
    ):
        return False
    allowed = re.compile(
        r"^(?:"
        r"Compiling|Checking|Finished|Fresh|Blocking|Locking|"
        r"Downloading|Downloaded|Updating|Adding|Removing|"
        r"test result:|running \d+ tests?|Doc-tests|Running |"
        r"test .+ \.\.\. ok$|"
        r"ok\s+\S+|-- PASS:|\?.*\[no test files\]|PASS$|"
        r"collected \d+ item|"
        r"[.sxFE]+\s+(?:\[\s*\d+%\])?|"
        r"=+\s+.*\s+=+$|"
        r"\d+\s+(?:passed|failed|skipped|ignored|xfailed|xpassed)\b"
        r")",
        re.I,
    )
    return all(
        allowed.search(line)
        or re.fullmatch(r"[.sxFE]+", line) is not None
        for line in lines
    )


def _compact_success_output(
    text: str,
    command: ValidationCommand,
) -> str:
    if command.operation != "test":
        return f"{command.family}: success\n"
    kept = [
        line.strip()
        for line in text.splitlines()
        if re.search(
            r"\b\d+\s+(?:passed|failed|skipped|ignored|xfailed|xpassed)\b",
            line,
            re.I,
        )
    ]
    if kept:
        return f"{command.family}: " + " | ".join(dict.fromkeys(kept[:4])) + "\n"
    return f"{command.family}: success\n"


def _research_simulations(
    command: ValidationCommand,
    metrics: OutputMetrics,
    text: str,
) -> tuple[dict[str, OutputMetrics], dict[str, str]]:
    simulations: dict[str, OutputMetrics] = {}
    rejection: dict[str, str] = {}
    if metrics.certainty.startswith("success"):
        reason = _success_rejection_reason(command, metrics, text)
        if reason is None:
            simulations["aggressive_success"] = _metrics_for_text(
                SUCCESS_OUTPUT,
                exit_code=0,
                complete=True,
                output_kind="simulation",
            )
            compact = _compact_success_output(text, command)
            if 0 < len(compact.encode("utf-8")) < metrics.bytes:
                simulations["conservative_success"] = _metrics_for_text(
                    compact,
                    exit_code=0,
                    complete=True,
                    output_kind="simulation",
                )
            else:
                rejection["conservative_success"] = "no_byte_savings"
        else:
            rejection["aggressive_success"] = reason
            rejection["conservative_success"] = reason
    if metrics.certainty in {"failed_verified", "failure_text_inferred"}:
        if metrics.certainty != "failed_verified":
            rejection["terse_failure"] = "not_authoritatively_verified"
        else:
            terse = format_terse_failure(
                text,
                ecosystem=command.ecosystem,
                certainty=metrics.certainty,
                complete=metrics.complete,
                features=metrics.features,
            )
            if terse is not None:
                simulations["terse_failure"] = _metrics_for_text(
                    terse,
                    exit_code=metrics.exit_code,
                    complete=True,
                    output_kind="simulation",
                )
            elif not resources_failure_passthrough(metrics):
                rejection["terse_failure"] = "no_safe_parser_match"
            elif not metrics.complete:
                rejection["terse_failure"] = "incomplete_or_truncated"
            elif metrics.features.get("binary_control"):
                rejection["terse_failure"] = "binary_control"
            elif metrics.features.get("stack_trace"):
                rejection["terse_failure"] = "panic_or_stack_trace"
            elif metrics.features.get("separate_stdout_and_stderr"):
                rejection["terse_failure"] = "separate_stream_interleaving_unknown"
            else:
                rejection["terse_failure"] = "no_safe_parser_match"
    if metrics.certainty in {"timeout", "cancelled", "unknown"}:
        rejection["terse_failure"] = f"unsafe_status:{metrics.certainty}"
    return simulations, rejection


def resources_failure_passthrough(metrics: OutputMetrics) -> bool:
    return (
        not metrics.complete
        or metrics.features.get("binary_control", False)
        or metrics.features.get("stack_trace", False)
        or metrics.certainty in {"timeout", "cancelled", "unknown"}
    )


def _research_attempted_candidates(certainty: str) -> tuple[str, ...]:
    if certainty.startswith("success"):
        return SUCCESS_RESEARCH_CANDIDATES
    if certainty.startswith("fail") or certainty in {
        "timeout",
        "cancelled",
        "unknown",
    }:
        return ("terse_failure",)
    return ()


def _research_row_dict(bucket: "ResearchBucket") -> dict[str, Any]:
    outputs = bucket.outputs
    simulations = {}
    candidate_names = sorted(
        set(bucket.simulation_counts)
        | set(bucket.simulation_attempted_counts)
        | set(bucket.candidate_rejections)
    )
    for name in candidate_names:
        transformed = bucket.simulation_counts.get(name, 0)
        skipped = sum(bucket.candidate_rejections.get(name, {}).values())
        simulations[name] = {
            "attempted_outputs": bucket.simulation_attempted_counts.get(
                name, transformed + skipped
            ),
            "transformed_outputs": transformed,
            "skipped_outputs": skipped,
            "original_bytes": bucket.simulation_attempted_bytes.get(
                name, bucket.simulation_original_bytes[name]
            ),
            "transformed_original_bytes": bucket.simulation_original_bytes[name],
            "transformed_bytes": bucket.simulation_transformed_bytes[name],
            "saved_bytes": max(
                0,
                bucket.simulation_original_bytes[name]
                - bucket.simulation_transformed_bytes[name],
            ),
            "saved_bytes_p50": _percentile(
                bucket.simulation_savings.get(name, []),
                0.5,
            ),
            "saved_bytes_p90": _percentile(
                bucket.simulation_savings.get(name, []),
                0.9,
            ),
            "saved_bytes_p95": _percentile(
                bucket.simulation_savings.get(name, []),
                0.95,
            ),
            "skip_reasons": dict(
                sorted(bucket.candidate_rejections.get(name, {}).items())
            ),
        }
    features: collections.Counter[str] = collections.Counter()
    for item in outputs:
        features.update(name for name, present in item.features.items() if present)
    return {
        "calls": bucket.calls,
        "distinct_sessions": len(bucket.sessions),
        "distinct_source_files": len(bucket.files),
        "packaging_counts": dict(sorted(bucket.packaging.items())),
        "confidence": dict(sorted(bucket.confidence.items())),
        "requested_only_syntax": bucket.requested_only_syntax,
        "matched_outputs": len(outputs),
        "unmatched_or_composite_calls": max(0, bucket.calls - len(outputs)),
        "zero_output_rate": round(
            sum(item.bytes == 0 for item in outputs) / len(outputs)
            if outputs
            else 0.0,
            6,
        ),
        "output": _summary_metrics(outputs),
        "status_certainty": dict(sorted(bucket.certainty.items())),
        "feature_counts": dict(sorted(features.items())),
        "clean_verified_success_outputs": simulations.get(
            "aggressive_success", {}
        ).get("transformed_outputs", 0),
        "clean_verified_success_rate": round(
            simulations.get("aggressive_success", {}).get("transformed_outputs", 0)
            / len(outputs)
            if outputs
            else 0.0,
            6,
        ),
        "simulations": simulations,
        "simulation_rejections": {
            name: dict(sorted(rejections.items()))
            for name, rejections in sorted(bucket.candidate_rejections.items())
        },
        "success_rejections": dict(sorted(bucket.success_rejections.items())),
        "terse_rejections": dict(sorted(bucket.terse_rejections.items())),
    }


@dataclass
class ResearchBucket:
    calls: int = 0
    sessions: set[str] = field(default_factory=set)
    files: set[str] = field(default_factory=set)
    packaging: collections.Counter[str] = field(default_factory=collections.Counter)
    confidence: collections.Counter[str] = field(default_factory=collections.Counter)
    requested_only_syntax: int = 0
    outputs: list[OutputMetrics] = field(default_factory=list)
    certainty: collections.Counter[str] = field(default_factory=collections.Counter)
    simulation_counts: collections.Counter[str] = field(default_factory=collections.Counter)
    simulation_original_bytes: collections.Counter[str] = field(
        default_factory=collections.Counter
    )
    simulation_transformed_bytes: collections.Counter[str] = field(
        default_factory=collections.Counter
    )
    simulation_savings: dict[str, list[int]] = field(
        default_factory=lambda: collections.defaultdict(list)
    )
    simulation_attempted_counts: collections.Counter[str] = field(
        default_factory=collections.Counter
    )
    simulation_attempted_bytes: collections.Counter[str] = field(
        default_factory=collections.Counter
    )
    candidate_rejections: dict[str, collections.Counter[str]] = field(
        default_factory=lambda: collections.defaultdict(collections.Counter)
    )
    success_rejections: collections.Counter[str] = field(default_factory=collections.Counter)
    terse_rejections: collections.Counter[str] = field(default_factory=collections.Counter)


def _add_research_bucket(
    bucket: ResearchBucket,
    *,
    call: ShellInvocation | None,
    command: ValidationCommand,
    output: OutputObservation | None = None,
    output_text: str = "",
) -> None:
    bucket.calls += 1
    bucket.packaging[command.packaging] += 1
    bucket.confidence[command.confidence] += 1
    if call is not None:
        bucket.sessions.add(call.session_id)
        bucket.files.add(call.source_key)
    if command.confidence != "high":
        bucket.requested_only_syntax += 1
    if output is None:
        return
    metrics = output.metrics
    bucket.outputs.append(metrics)
    bucket.certainty[metrics.certainty] += 1
    for candidate in _research_attempted_candidates(metrics.certainty):
        bucket.simulation_attempted_counts[candidate] += 1
        bucket.simulation_attempted_bytes[candidate] += metrics.bytes
    simulations, rejection = _research_simulations(command, metrics, output_text)
    for name, simulated in simulations.items():
        bucket.simulation_counts[name] += 1
        bucket.simulation_original_bytes[name] += metrics.bytes
        bucket.simulation_transformed_bytes[name] += simulated.bytes
        bucket.simulation_savings[name].append(max(0, metrics.bytes - simulated.bytes))
    for candidate, reason in rejection.items():
        bucket.candidate_rejections[candidate][reason] += 1
        if reason.startswith(
            (
                "not_",
                "incomplete",
                "binary",
                "warnings",
                "errors",
                "skipped",
                "xfail",
                "deprecated",
                "failure",
                "interactive",
                "uncertainty",
                "no_tests",
                "stack",
                "truncated",
                "stderr",
                "zero",
                "no_reviewed",
                "unrecognized",
                "no_byte",
            )
        ):
            bucket.success_rejections[reason] += 1
        else:
            bucket.terse_rejections[reason] += 1


def _privacy_hash(kind: str, value: str) -> str:
    return hashlib.sha256(f"{kind}\0{value}".encode("utf-8")).hexdigest()[:20]


def _coverage_reasons(state: ScanState) -> list[str]:
    reasons: list[str] = []
    source = state.source
    if state.options.full_history and source.inventory_files == 0:
        reasons.append("no_rollout_files")
    if state.options.full_history and (
        state.options.since is not None or state.options.until is not None
    ):
        reasons.append("date_filters_applied")
    if source.file_limit_reached:
        reasons.append("file_count_cap_reached")
    if source.byte_limit_reached:
        reasons.append("total_byte_cap_reached")
    if source.truncated_files:
        reasons.append("per_file_byte_cap_reached")
    if source.unreadable_files:
        reasons.append("unreadable_inputs")
    if source.missing_roots:
        reasons.append("missing_history_roots")
    if source.changed_files:
        reasons.append("inputs_changed_during_scan")
    if source.invalid_utf8:
        reasons.append("invalid_utf8_records")
    if source.invalid_json:
        reasons.append("invalid_json_records")
    if source.oversized_lines:
        reasons.append("oversized_records")
    if source.partial_trailing_records:
        reasons.append("partial_trailing_records")
    if source.skipped_symlinks:
        reasons.append("symlink_inputs_skipped")
    harmless_omissions = {"duplicate_physical_file", "exact_duplicate_content"}
    if (
        source.omitted_files
        and any(
            reason not in harmless_omissions
            for reason in source.omitted_by_reason
        )
        and not reasons
    ):
        reasons.append("eligible_inputs_omitted")
    return reasons


def build_census_manifest(state: ScanState) -> dict[str, Any]:
    source = state.source
    reasons = _coverage_reasons(state)
    complete = state.options.full_history and not reasons
    if state.options.full_history:
        coverage_status = (
            "unmeasured"
            if source.inventory_files == 0
            else "complete"
            if complete
            else "partial"
        )
    elif state.options.since is not None or state.options.until is not None:
        coverage_status = "sampled"
    else:
        coverage_status = "bounded_or_filtered"
    files: list[dict[str, Any]] = []
    for entry in sorted(
        source.inventory_entries,
        key=lambda item: (item.category, item.file_id),
    ):
        files.append(
            {
                "file_id": entry.file_id,
                "category": entry.category,
                "size_bytes": entry.size,
                "path_date": entry.path_date.isoformat() if entry.path_date else None,
                "selected": entry.selected,
                "processed": entry.processed,
                "duplicate_of_file_id": entry.duplicate_of,
                "consumed_bytes": entry.consumed_bytes,
                "records": entry.records,
                "invalid_utf8": entry.invalid_utf8,
                "invalid_json": entry.invalid_json,
                "oversized_records": entry.oversized_lines,
                "partial_trailing_records": entry.partial_trailing_records,
                "metadata_changed": (
                    entry.start_metadata is not None
                    and entry.end_metadata is not None
                    and entry.start_metadata != entry.end_metadata
                ),
                "omitted": entry.omitted,
                "omission_reasons": sorted(entry.omission_reasons),
                "session_ids": sorted(
                    _privacy_hash("session", value)
                    for value in entry.session_ids
                    if value
                ),
            }
        )
    session_instances = {
        _privacy_hash("session-instance", f"{source_key}\0{session_id}")
        for source_key, session_id in state.source_sessions
    }
    budget_exhausted = (
        source.file_limit_reached
        or source.byte_limit_reached
        or source.truncated_files > 0
    )
    cohort_material = "\n".join(
        f"{entry.category}\0{entry.file_id}\0{entry.size}\0{entry.mtime_ns}"
        for entry in sorted(
            source.inventory_entries,
            key=lambda item: (item.category, item.file_id),
        )
    )
    return {
        "manifest_version": 1,
        "title": "Codex rollout history census manifest",
        "cohort_id": hashlib.sha256(cohort_material.encode("utf-8")).hexdigest()[:24],
        "privacy": {
            "absolute_paths_included": False,
            "relative_paths_included": False,
            "session_ids_included": False,
            "raw_commands_included": False,
            "raw_outputs_included": False,
            "identifiers": "truncated_sha256",
        },
        "mode": {
            "full_history": state.options.full_history,
            "include_archived": (
                state.options.include_archived or state.options.full_history
            ),
            "since": state.options.since.isoformat() if state.options.since else None,
            "until": state.options.until.isoformat() if state.options.until else None,
        },
        "completeness": {
            "status": coverage_status,
            "exhaustive": complete,
            "full_coverage_failed": state.options.full_history and not complete,
            "reasons": reasons,
            "omitted_by_reason": dict(sorted(source.omitted_by_reason.items())),
            "budget_exhausted": budget_exhausted,
        },
        "summary": {
            "files_found": source.inventory_files,
            "files_eligible": source.eligible_files,
            "files_scanned": source.processed_files,
            "files_omitted": source.omitted_files,
            "current_files_found": source.current_inventory_files,
            "archived_files_found": source.archived_inventory_files,
            "current_files_scanned": source.source_categories.get("sessions", 0),
            "archived_files_scanned": source.source_categories.get(
                "archived_sessions", 0
            ),
            "total_inventory_bytes": source.inventory_bytes,
            "records": source.records,
            "distinct_sessions": len(state.sessions_seen),
            "session_source_instances": len(session_instances),
            "reused_session_ids_across_sources": max(
                0, len(session_instances) - len(state.sessions_seen)
            ),
            "duplicate_rollout_files": source.duplicate_rollout_files,
            "duplicate_physical_files": source.duplicate_physical_files,
            "date_excluded_files": source.date_excluded_files,
            "archived_excluded_files": source.archived_excluded_files,
            "skipped_symlinks": source.skipped_symlinks,
            "missing_roots": source.missing_roots,
            "missing_root_categories": sorted(source.missing_root_categories),
            "ignored_non_rollout_files": source.ignored_non_rollout_files,
            "unreadable_files": source.unreadable_files,
            "changed_files": source.changed_files,
            "invalid_utf8_records": source.invalid_utf8,
            "invalid_json_records": source.invalid_json,
            "oversized_records": source.oversized_lines,
            "partial_trailing_records": source.partial_trailing_records,
        },
        "budgets": {
            "max_files": state.options.max_files,
            "max_file_bytes": state.options.max_file_bytes,
            "max_total_bytes": state.options.max_total_bytes,
            "max_line_bytes": state.options.max_line_bytes,
        },
        "files": files,
    }


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
    sequence_analysis = build_sequence_analysis(
        state.timeline_events,
        state.calls,
    )
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
    research_rows: dict[tuple[str, str, str, str, str], ResearchBucket] = {}
    research_ecosystem_operations: dict[tuple[str, str], ResearchBucket] = {}
    research_packaging: dict[str, ResearchBucket] = collections.defaultdict(ResearchBucket)
    research_syntax_rows: dict[
        tuple[str, str, str, str, str], ResearchBucket
    ] = {}
    research_command_count = 0
    research_syntax_only_count = 0
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
                segment_classification = classify_validation_command(
                    family=segment.family,
                    shape=segment.shape,
                    raw=segment.shape,
                    confidence="partial",
                    execution_form="shell_batch",
                    parent_mixed=True,
                )
                if segment_classification is not None:
                    research_syntax_only_count += 1
                    syntax_key = (
                        segment_classification.ecosystem,
                        segment_classification.operation,
                        segment_classification.family,
                        segment_classification.shape,
                        "syntax_only",
                    )
                    syntax_bucket = research_syntax_rows.setdefault(
                        syntax_key,
                        ResearchBucket(),
                    )
                    _add_research_bucket(
                        syntax_bucket,
                        call=None,
                        command=segment_classification,
                    )
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
            classification = classify_validation_command(
                family=command.family,
                shape=command.shape,
                raw=command.raw,
                confidence=command.confidence,
                execution_form=call.execution_form,
                parent_mixed=call.parent_mixed,
            )
            if classification is not None:
                research_command_count += 1
                exclusive_output = (
                    call.output
                    if (
                        call.output is not None
                        and call.execution_form == "direct"
                        and len(call.subcommands) == 1
                        and command.confidence == "high"
                        and not call.dry_run
                    )
                    else None
                )
                research_key = (
                    classification.ecosystem,
                    classification.operation,
                    classification.family,
                    classification.shape,
                    classification.packaging,
                )
                _add_research_bucket(
                    research_rows.setdefault(research_key, ResearchBucket()),
                    call=call,
                    command=classification,
                    output=exclusive_output,
                    output_text=exclusive_output.text if exclusive_output else "",
                )
                _add_research_bucket(
                    research_ecosystem_operations.setdefault(
                        (classification.ecosystem, classification.operation),
                        ResearchBucket(),
                    ),
                    call=call,
                    command=classification,
                    output=exclusive_output,
                    output_text=exclusive_output.text if exclusive_output else "",
                )
                _add_research_bucket(
                    research_packaging[classification.packaging],
                    call=call,
                    command=classification,
                    output=exclusive_output,
                    output_text=exclusive_output.text if exclusive_output else "",
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

    census = build_census_manifest(state)
    taxonomy_rows = []
    for key, bucket in research_rows.items():
        ecosystem, operation, family, shape, packaging = key
        taxonomy_rows.append(
            {
                "ecosystem": ecosystem,
                "operation": operation,
                "family": family,
                "shape": shape,
                "packaging": packaging,
                **_research_row_dict(bucket),
            }
        )
    taxonomy_rows.sort(
        key=lambda row: (
            row["ecosystem"],
            OPERATIONS.index(row["operation"])
            if row["operation"] in OPERATIONS
            else len(OPERATIONS),
            -row["calls"],
            row["family"],
            row["shape"],
            row["packaging"],
        )
    )
    ecosystem_operation_rows = []
    for (ecosystem, operation), bucket in research_ecosystem_operations.items():
        ecosystem_operation_rows.append(
            {
                "ecosystem": ecosystem,
                "operation": operation,
                **_research_row_dict(bucket),
            }
        )
    ecosystem_operation_rows.sort(
        key=lambda row: (
            row["ecosystem"],
            OPERATIONS.index(row["operation"])
            if row["operation"] in OPERATIONS
            else len(OPERATIONS),
            -row["calls"],
        )
    )
    packaging_rows = [
        {"packaging": packaging, **_research_row_dict(bucket)}
        for packaging, bucket in sorted(research_packaging.items())
    ]
    syntax_rows = []
    for key, bucket in research_syntax_rows.items():
        ecosystem, operation, family, shape, _unused = key
        syntax_rows.append(
            {
                "ecosystem": ecosystem,
                "operation": operation,
                "family": family,
                "shape": shape,
                **_research_row_dict(bucket),
            }
        )
    syntax_rows.sort(
        key=lambda row: (
            row["ecosystem"],
            row["operation"],
            -row["calls"],
            row["family"],
            row["shape"],
        )
    )
    candidate_definitions = {
        "aggressive_success": {
            "title": "Aggressive exact Success! success output",
            "candidate_output": SUCCESS_OUTPUT,
            "risk": (
                "May hide warning, skip, deprecation, no-test, or nonstandard "
                "diagnostic information despite a zero exit."
            ),
            "fallback": (
                "Original output unless exit is authoritative, output is complete, "
                "the command formatter is reviewed, and all guard features are absent."
            ),
        },
        "conservative_success": {
            "title": "Conservative compact success summary",
            "risk": "May hide warning or package detail not represented in the compact summary.",
            "fallback": "Original output unless the same strict verified-success gate passes.",
        },
        "terse_failure": {
            "title": "Terse actionable failure diagnostic",
            "risk": "Parsers can omit unique secondary failures or context needed to repair code.",
            "fallback": (
                "Original output for non-authoritative/unknown formats, panics, "
                "linker/runtime errors, binary output, truncation, timeout, "
                "cancellation, or parser uncertainty."
            ),
        },
    }
    research_candidate_rows: list[dict[str, Any]] = []
    for candidate_id, definition in candidate_definitions.items():
        transformed = 0
        transformed_original_bytes = 0
        attempted_bytes = 0
        transformed_bytes = 0
        savings: list[int] = []
        rejections: collections.Counter[str] = collections.Counter()
        for bucket in research_rows.values():
            candidate_transformed = bucket.simulation_counts.get(candidate_id, 0)
            candidate_rejections = bucket.candidate_rejections.get(candidate_id, {})
            transformed += candidate_transformed
            transformed_original_bytes += bucket.simulation_original_bytes.get(
                candidate_id, 0
            )
            attempted_bytes += bucket.simulation_attempted_bytes.get(candidate_id, 0)
            transformed_bytes += bucket.simulation_transformed_bytes.get(
                candidate_id, 0
            )
            savings.extend(bucket.simulation_savings.get(candidate_id, []))
            rejections.update(candidate_rejections)
        saved_bytes = max(0, transformed_original_bytes - transformed_bytes)
        rejected = sum(rejections.values())
        research_candidate_rows.append(
            {
                "candidate_id": candidate_id,
                **definition,
                "eligible_outputs": transformed + rejected,
                "transformed_outputs": transformed,
                "skipped_outputs": rejected,
                "skip_reasons": dict(sorted(rejections.items())),
                "original_targeted_bytes": attempted_bytes,
                "transformed_original_bytes": transformed_original_bytes,
                "transformed_bytes": transformed_bytes,
                "saved_bytes": saved_bytes,
                "savings_fraction_of_targeted": round(
                    saved_bytes / attempted_bytes if attempted_bytes else 0.0,
                    6,
                ),
                "fraction_of_all_matched_output_bytes": round(
                    attempted_bytes / call_output_bytes if call_output_bytes else 0.0,
                    6,
                ),
                "saved_bytes_p50": _percentile(savings, 0.5),
                "saved_bytes_p90": _percentile(savings, 0.9),
                "saved_bytes_p95": _percentile(savings, 0.95),
                "estimated_observation_token_reduction": _token_range(saved_bytes),
            }
        )
    threshold_bytes = state.options.significance_min_bytes
    threshold_fraction = state.options.significance_min_fraction
    gated_rows = []
    for row in ecosystem_operation_rows:
        for candidate_id in RESEARCH_CANDIDATES:
            simulation = row["simulations"].get(candidate_id)
            if simulation is None:
                continue
            saved = simulation["saved_bytes"]
            target = simulation["original_bytes"]
            fraction = saved / target if target else 0.0
            gated_rows.append(
                {
                    "ecosystem": row["ecosystem"],
                    "operation": row["operation"],
                    "candidate_id": candidate_id,
                    "targeted_bytes": target,
                    "saved_bytes": saved,
                    "savings_fraction_of_targeted": round(fraction, 6),
                    "meets_bytes_gate": saved >= threshold_bytes,
                    "meets_fraction_gate": fraction >= threshold_fraction,
                    "significant": (
                        saved >= threshold_bytes and fraction >= threshold_fraction
                    ),
                }
            )
    gated_rows.sort(
        key=lambda row: (
            not row["significant"],
            -row["saved_bytes"],
            row["ecosystem"],
            row["operation"],
            row["candidate_id"],
        )
    )
    certainty_counts: collections.Counter[str] = collections.Counter()
    for call in state.calls:
        if call.output is not None:
            certainty_counts[call.output.metrics.certainty] += 1
    gate_passed = any(row["significant"] for row in gated_rows)
    coverage_status = census["completeness"]["status"]
    if coverage_status == "unmeasured":
        gate_conclusion = (
            "Unmeasured: no eligible rollout files were available, so no savings "
            "finding is asserted."
        )
    elif gate_passed and census["completeness"]["exhaustive"]:
        gate_conclusion = (
            "Significant savings demonstrated for at least one targeted "
            "ecosystem/operation in an exhaustive cohort."
        )
    elif gate_passed:
        gate_conclusion = (
            "Significant savings observed for at least one targeted "
            "ecosystem/operation, but the cohort is not exhaustive."
        )
    elif census["completeness"]["exhaustive"]:
        gate_conclusion = (
            "No significant savings demonstrated under both configured gates."
        )
    else:
        gate_conclusion = (
            "No significant savings demonstrated in the measured subset; the "
            "full-history cohort is incomplete."
        )
    research = {
        "research_schema_version": 1,
        "taxonomy_version": TAXONOMY_VERSION,
        "title": "Compilation and validation output compression research",
        "cohort_id": census["cohort_id"],
        "scan_budgets": census["budgets"],
        "privacy": {
            "raw_commands_included": False,
            "raw_outputs_included": False,
            "paths_included": False,
            "session_ids_included": False,
            "reporting_only": True,
        },
        "coverage": census["completeness"],
        "baseline_no_compression": {
            "matched_output_bytes": call_output_bytes,
            "transformed_outputs": 0,
            "saved_bytes": 0,
            "prompt_or_tool_wrapper_overhead_bytes": None,
            "wrapper_overhead_status": "not_separately_measured",
        },
        "candidate_outputs": research_candidate_rows,
        "significance_gates": {
            "minimum_saved_bytes_per_ecosystem_operation": threshold_bytes,
            "minimum_savings_fraction_of_targeted_bytes": threshold_fraction,
            "all_matched_output_bytes": call_output_bytes,
            "cohort_exhaustive": census["completeness"]["exhaustive"],
            "any_ecosystem_operation_meets_both": gate_passed,
            "conclusion": gate_conclusion,
        },
        "coverage_counts": {
            "classification_taxonomy_commands": research_command_count,
            "syntactic_only_classifications": research_syntax_only_count,
            "matched_outputs": matched_outputs,
            "status_certainty": dict(sorted(certainty_counts.items())),
        },
        "ecosystem_operations": ecosystem_operation_rows,
        "packaging": packaging_rows,
        "commands": taxonomy_rows,
        "syntax_only": syntax_rows,
        "gated_opportunities": gated_rows,
        "counterexamples": [
            {
                "case": "warning_bearing_exit_zero",
                "required_behavior": "Retain warning; aggressive success is rejected.",
            },
            {
                "case": "ignored_or_skipped_tests",
                "required_behavior": "Retain test disposition; aggressive success is rejected.",
            },
            {
                "case": "mixed_batch_output",
                "required_behavior": "Keep one outer batch output; do not infer per-member success.",
            },
            {
                "case": "failed_nested_invocation",
                "required_behavior": "Never convert non-authoritative success text into success.",
            },
            {
                "case": "truncated_or_partial_output",
                "required_behavior": "Passthrough; neither candidate is safe.",
            },
            {
                "case": "unknown_exit_status",
                "required_behavior": "Passthrough; text markers alone are insufficient.",
            },
            {
                "case": "panic_linker_race_or_runtime_failure",
                "required_behavior": "Passthrough terse-failure parser output.",
            },
        ],
        "limitations": [
            "Token ranges are byte heuristics, not tokenizer or provider usage.",
            "The report measures captured model-visible payload bytes, not cache misses or dollars.",
            (
                "Token and byte accounting covers captured payload text; provider "
                "prompt/tool-schema wrapper overhead is not reconstructed."
            ),
            "Output was transformed only in memory and was never executed, replayed, or serialized.",
            "A future controlled coding-agent A/B study is required before runtime adoption.",
        ],
    }

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "title": "Codex command frequency and tool-output report",
        "codex_history_census": census,
        "compilation_output_research": research,
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
            "full_history": state.options.full_history,
            "coverage_status": census["completeness"]["status"],
            "exhaustive": census["completeness"]["exhaustive"],
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
            "inventory_files": state.source.inventory_files,
            "eligible_files": state.source.eligible_files,
            "omitted_files": state.source.omitted_files,
            "current_inventory_files": state.source.current_inventory_files,
            "archived_inventory_files": state.source.archived_inventory_files,
            "inventory_bytes": state.source.inventory_bytes,
            "sessions": len(state.sessions_seen),
            "session_source_instances": len(state.source_sessions),
            "reused_session_ids_across_sources": max(
                0, len(state.source_sessions) - len(state.sessions_seen)
            ),
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
            "duplicate_rollout_files": state.source.duplicate_rollout_files,
            "duplicate_physical_files": state.source.duplicate_physical_files,
            "ambiguous_output_events": state.ambiguous_outputs,
            "malformed_argument_events": state.malformed_arguments,
            "result_match_coverage": round(result_coverage, 6),
            "skipped_symlinks": state.source.skipped_symlinks,
            "unreadable_files": state.source.unreadable_files,
            "changed_files": state.source.changed_files,
            "date_excluded_files": state.source.date_excluded_files,
            "archived_excluded_files": state.source.archived_excluded_files,
            "invalid_utf8_records": state.source.invalid_utf8,
            "invalid_json_records": state.source.invalid_json,
            "oversized_records": state.source.oversized_lines,
            "partial_trailing_records": state.source.partial_trailing_records,
            "file_limit_reached": state.source.file_limit_reached,
            "byte_limit_reached": state.source.byte_limit_reached,
            "truncated_files": state.source.truncated_files,
            "completeness_reasons": census["completeness"]["reasons"],
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
            "status_certainty_counts": dict(sorted(certainty_counts.items())),
            "verified_exit_observations": sum(
                item.certainty in {"success_verified", "failed_verified"}
                for item in all_outputs
            ),
            "text_inferred_status_observations": sum(
                item.certainty
                in {"success_text_inferred", "failure_text_inferred"}
                for item in all_outputs
            ),
            "timeout_or_cancelled_observations": sum(
                item.certainty in {"timeout", "cancelled"} for item in all_outputs
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
        "sequence_analysis": sequence_analysis,
        "terse_adapters": candidate_rows,
        "smallest_safe_initial_set": [
            row["candidate_id"]
            for row in candidate_rows
            if row["safety_class"] == "safe_to_aggregate"
            and row["simulation"]["removed_observed_bytes"] > 0
        ][:3],
        "methodology": {
            "schema_migration": {
                "from_version": 2,
                "to_version": 3,
                "compatible_fields": [
                    "coverage.shell_tool_invocations",
                    "coverage.requested_underlying_subcommands",
                    "coverage.matched_shell_invocations",
                    "output_measurement.observed_model_visible_output",
                    "opaque_attribution",
                ],
                "changed_semantics": (
                    "Version 3 adds versioned sequence_analysis, "
                    "codex_history_census, and compilation_output_research sections "
                    "with separate report artifacts. Existing schema-v2 metrics "
                    "retain their established meanings."
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
            "Sequence packaging and observed adjacency do not establish hidden model decisions.",
            "Same-response evidence requires an explicit rollout response_id.",
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


def build_sequence_report(report: dict[str, Any]) -> dict[str, Any]:
    sequence = report["sequence_analysis"]
    return {
        "schema_version": sequence["sequence_schema_version"],
        "parent_schema_version": report["schema_version"],
        "title": "Codex ordered command-sequence analysis",
        "privacy": report["privacy"],
        "analysis_scope": report["analysis_scope"],
        "sequence_analysis": sequence,
    }


def _sequence_label(row: dict[str, Any]) -> str:
    return " → ".join(
        f"`{item['identity']}`" for item in row["sequence"]
    )


def _sequence_mode_sessions(row: dict[str, Any]) -> str:
    sessions = row["distinct_sessions_by_mode"]
    return "/".join(
        _format_int(sessions[name])
        for name in (
            "explicit_batch",
            "separate_direct_calls",
            "mixed_batch_and_direct",
            "unknown",
        )
    )


def _sequence_batched_fraction(row: dict[str, Any]) -> str:
    denominator = row["batched_fraction_denominator"]
    if row["batched_fraction"] is None:
        return f"n/a ({_format_int(denominator)})"
    return f"{row['batched_fraction']:.1%} ({_format_int(denominator)})"


def _sequence_same_response_fraction(row: dict[str, Any]) -> str:
    count = row["unbatched_same_response_count"]
    denominator = row["unbatched_same_response_denominator"]
    if row["unbatched_same_response_fraction"] is None:
        return f"{_format_int(count)} (n/a/{_format_int(denominator)})"
    return (
        f"{_format_int(count)} "
        f"({row['unbatched_same_response_fraction']:.1%}/"
        f"{_format_int(denominator)})"
    )


def _sequence_subcommands(row: dict[str, Any]) -> str:
    return "/".join(
        _format_int(row[name])
        for name in (
            "requested_subcommands",
            "confirmed_executed_subcommands",
            "unknown_subcommand_statuses",
        )
    )


def _sequence_shape_example(row: dict[str, Any]) -> str:
    examples = row.get("shape_examples", [])
    if not examples:
        return "n/a"
    return " → ".join(
        f"`{identity}`"
        for identity in examples[0]["shape_sequence"]
    )


def _sequence_failure_rate(row: dict[str, Any]) -> str:
    failed = row["observed_status"]["failed"]
    denominator = failed + row["observed_status"]["success"]
    if row["failure_rate"] is None:
        return f"{_format_int(failed)} (n/a/{_format_int(denominator)})"
    return (
        f"{_format_int(failed)} "
        f"({row['failure_rate']:.1%}/{_format_int(denominator)})"
    )


def render_sequence_markdown(report: dict[str, Any]) -> str:
    sequence = report["sequence_analysis"]
    coverage = sequence["coverage"]
    window = report["analysis_scope"]["date_window"]
    lines = [
        "# Codex Command Sequence Report",
        "",
        "This is a privacy-safe observational summary. Canonical sequence identity "
        "excludes packaging. Raw commands, arguments, outputs, prompts, paths, and "
        "session identifiers are not included.",
        "",
        "## Scope and evidence",
        "",
        f"- Sequence schema: `{sequence['sequence_schema_version']}`; parent report "
        f"schema: `{report['schema_version']}`",
        f"- Date window: `{window['since'] or 'unbounded'}` through "
        f"`{window['until'] or 'unbounded'}` (inclusive)",
        f"- Source files: {_format_int(coverage['source_files'])}; sessions: "
        f"{_format_int(coverage['sessions'])}",
        f"- Timeline events classified: {_format_int(coverage['timeline_events'])}",
        f"- Response groups observed: "
        f"{_format_int(coverage['response_groups_observed'])}",
        f"- Shell invocations linked to timeline: "
        f"{_format_int(coverage['shell_invocations_with_timeline'])}",
        f"- Matched shell outputs: "
        f"{_format_int(coverage['matched_shell_invocations'])}",
        f"- Invocations excluded from sequences: "
        f"{_format_int(coverage['shell_invocations_excluded_from_sequences'])} "
        f"({_format_int(coverage['ambiguous_ordering_invocations_excluded'])} "
        "ambiguous ordering)",
        f"- Requested batch subcommands: "
        f"{_format_int(coverage['requested_batch_subcommands'])}; confirmed executed: "
        f"{_format_int(coverage['confirmed_executed_batch_subcommands'])}; unknown: "
        f"{_format_int(coverage['unknown_batch_subcommand_statuses'])}",
        f"- Direct edges classified: "
        f"{_format_int(coverage['direct_edges_classified'])}; hard boundaries: "
        f"{_format_int(coverage['hard_boundaries'])}",
        f"- Reused session IDs across source files: "
        f"{_format_int(coverage['reused_session_ids_across_sources'])}",
        "",
        "All sequence counts below are overlapping windows. Packaging is shown separately "
        "and is not part of the canonical identity.",
        "",
    ]
    for granularity in ("family", "shape"):
        title = "command families" if granularity == "family" else "normalized shapes"
        lines.extend([f"## Repeated {title}", ""])
        for length in (2, 3, 4):
            rows = sequence["ranking"].get(f"{granularity}_{length}", [])
            lines.extend([f"### Length {length}", ""])
            if not rows:
                lines.extend(["No repeated sequence observed.", ""])
                continue
            lines.extend(
                _markdown_table(
                    [
                        "Sequence",
                        "Total",
                        "Sessions",
                        "Sessions E/D/M/U",
                        "Explicit",
                        "Direct",
                        "Mixed",
                        "Unknown",
                        "Same response (denom)",
                        "Confirmed occurrences",
                        "Requested-only occurrences",
                        "Subcommands req/conf/unknown",
                        "Matched invocations",
                        "Batched fraction (denom)",
                        "Success",
                        "Failed (rate/known)",
                        "Unknown status",
                        "Output bytes",
                    ],
                    (
                        [
                            _sequence_label(row),
                            _format_int(row["total"]),
                            _format_int(row["distinct_sessions"]),
                            _sequence_mode_sessions(row),
                            _format_int(row["explicit_batch"]),
                            _format_int(row["separate_direct_calls"]),
                            _format_int(row["mixed"]),
                            _format_int(row["unknown"]),
                            _sequence_same_response_fraction(row),
                            _format_int(row["confirmed_executed_occurrences"]),
                            _format_int(row["requested_only_occurrences"]),
                            _sequence_subcommands(row),
                            f"{_format_int(row['matched_invocations'])}/"
                            f"{_format_int(row['invocation_occurrences'])}",
                            _sequence_batched_fraction(row),
                            _format_int(row["observed_status"]["success"]),
                            _sequence_failure_rate(row),
                            _format_int(row["observed_status"]["unknown"]),
                            _format_int(row["exclusive_output_bytes"]),
                        ]
                        for row in rows
                    ),
                )
            )
            lines.append("")

    lines.extend(["## Explicit batch sequences", ""])
    explicit_rows: list[dict[str, Any]] = []
    for length in (2, 3, 4):
        explicit_rows.extend(
            sequence["explicit_batch_sequences"].get(f"family_{length}", [])
        )
    if explicit_rows:
        lines.extend(
            _markdown_table(
                [
                    "Sequence",
                    "Explicit",
                    "Total",
                    "Sessions",
                    "Confirmed occurrences",
                    "Requested-only occurrences",
                    "Subcommands req/conf/unknown",
                    "Failed",
                    "Unknown status",
                ],
                (
                    [
                        _sequence_label(row),
                        _format_int(row["explicit_batch"]),
                        _format_int(row["total"]),
                        _format_int(row["distinct_sessions"]),
                        _format_int(row["confirmed_executed_occurrences"]),
                        _format_int(row["requested_only_occurrences"]),
                        _sequence_subcommands(row),
                        _format_int(row["observed_status"]["failed"]),
                        _format_int(row["observed_status"]["unknown"]),
                    ]
                    for row in explicit_rows
                ),
            )
        )
    else:
        lines.append("No repeated explicit-batch sequence observed.")

    lines.extend(["", "## Direct-call sequences", ""])
    direct_rows: list[dict[str, Any]] = []
    for length in (2, 3, 4):
        direct_rows.extend(
            sequence["direct_sequences"].get(f"family_{length}", [])
        )
    if direct_rows:
        lines.extend(
            _markdown_table(
                [
                    "Sequence",
                    "Direct",
                    "Total",
                    "Sessions",
                    "Same response",
                    "Matched invocations",
                    "Subcommands req/conf/unknown",
                    "Failed",
                    "Unknown status",
                ],
                (
                    [
                        _sequence_label(row),
                        _format_int(row["separate_direct_calls"]),
                        _format_int(row["total"]),
                        _format_int(row["distinct_sessions"]),
                        _format_int(row["same_response_inferred"]),
                        f"{_format_int(row['matched_invocations'])}/"
                        f"{_format_int(row['invocation_occurrences'])}",
                        _sequence_subcommands(row),
                        _format_int(row["observed_status"]["failed"]),
                        _format_int(row["observed_status"]["unknown"]),
                    ]
                    for row in direct_rows
                ),
            )
        )
    else:
        lines.append("No repeated direct-call sequence observed.")

    lines.extend(["## Edge evidence", ""])
    lines.extend(
        _markdown_table(
            ["Intervening class", "Edges"],
            (
                [f"`{name}`", _format_int(count)]
                for name, count in sequence["intervening_event_histogram"].items()
            ),
        )
    )
    lines.extend(["", "### Response-boundary evidence", ""])
    lines.extend(
        _markdown_table(
            ["Evidence class", "Edges"],
            (
                [f"`{name}`", _format_int(count)]
                for name, count in sequence["response_boundary_evidence"].items()
            ),
        )
    )
    lines.extend(["", "### Elapsed-time buckets", ""])
    lines.extend(
        _markdown_table(
            ["Bucket", "Edges"],
            (
                [f"`{name}`", _format_int(count)]
                for name, count in sequence["elapsed_time_histogram"].items()
            ),
        )
    )
    lines.extend(["## Cross-mode repeats", ""])
    cross_rows: list[dict[str, Any]] = []
    for length in (2, 3, 4):
        cross_rows.extend(sequence["cross_mode_repeats"].get(f"family_{length}", []))
    if cross_rows:
        lines.extend(
            _markdown_table(
                [
                    "Sequence",
                    "Total",
                    "Explicit",
                    "Direct",
                    "Mixed",
                    "Unknown boundaries",
                    "Session E&D overlap",
                    "Review category",
                ],
                (
                    [
                        _sequence_label(row),
                        _format_int(row["total"]),
                        _format_int(row["explicit_batch"]),
                        _format_int(row["separate_direct_calls"]),
                        _format_int(row["mixed"]),
                        _format_int(row["unknown"]),
                        _format_int(
                            row["within_session_mode_overlap"][
                                "explicit_and_direct_session_instances"
                            ]
                        ),
                        f"`{row['candidate_category']}`",
                    ]
                    for row in cross_rows
                ),
            )
        )
    else:
        lines.append("No repeated family sequence occurred in both explicit and direct modes.")
    lines.extend(
        [
            "",
            "Cross-mode evidence does not show that an unbatched occurrence was safe to batch.",
            "",
        ]
    )

    lines.extend(["## Same-response cross-mode repeats", ""])
    same_response_rows: list[dict[str, Any]] = []
    for length in (2, 3, 4):
        same_response_rows.extend(
            sequence["cross_mode_same_response_repeats"].get(
                f"family_{length}", []
            )
        )
    if same_response_rows:
        lines.extend(
            _markdown_table(
                [
                    "Sequence",
                    "Total",
                    "Explicit",
                    "Same response direct",
                    "Subcommands req/conf/unknown",
                    "Session E&D overlap",
                ],
                (
                    [
                        _sequence_label(row),
                        _format_int(row["total"]),
                        _format_int(row["explicit_batch"]),
                        _format_int(row["unbatched_same_response_count"]),
                        _sequence_subcommands(row),
                        _format_int(
                            row["within_session_mode_overlap"][
                                "explicit_and_direct_session_instances"
                            ]
                        ),
                    ]
                    for row in same_response_rows
                ),
            )
        )
    else:
        lines.append(
            "No repeated family sequence occurred in both explicit and "
            "same-response direct contexts."
        )

    lines.extend(["", "## Observed command transitions", ""])
    transition_rows = sequence["transitions"]["rows"][:15]
    if transition_rows:
        lines.extend(
            _markdown_table(
                [
                    "First",
                    "Next",
                    "Count",
                    "Follow rate (denom)",
                    "Sessions",
                    "Next output bytes",
                ],
                (
                    [
                        f"`{row['first']}`",
                        f"`{row['second']}`",
                        _format_int(row["count"]),
                        f"{row['conditional_follow_rate']:.1%} "
                        f"({_format_int(row['denominator'])})",
                        _format_int(row["distinct_sessions"]),
                        _format_int(row["next_command_exclusive_output_bytes"]),
                    ]
                    for row in transition_rows
                ),
            )
        )
    else:
        lines.append("No observed command transition.")

    high_output_rows = sequence["transitions"]["low_frequency_high_output_rows"]
    if high_output_rows:
        lines.extend(["", "### Low-frequency high-output transitions", ""])
        lines.extend(
            _markdown_table(
                [
                    "First",
                    "Next",
                    "Count",
                    "Next output bytes",
                    "Mean next output bytes",
                ],
                (
                    [
                        f"`{row['first']}`",
                        f"`{row['second']}`",
                        _format_int(row["count"]),
                        _format_int(row["next_command_exclusive_output_bytes"]),
                        _format_int(row["mean_next_command_output_bytes"]),
                    ]
                    for row in high_output_rows
                ),
            )
        )
    lines.append(
        "Follow rates describe observed physical transitions only and do not "
        "establish batch safety."
    )
    lines.extend(
        [
            "",
            "## Conservative batching candidates",
            "",
        ]
    )
    candidates = sequence["batching_candidates"]
    if candidates:
        lines.extend(
            _markdown_table(
                [
                    "Sequence",
                    "Sanitized shape sample",
                    "Category",
                    "Total",
                    "Explicit",
                    "Direct",
                    "Failed",
                    "Unknown status",
                ],
                (
                    [
                        " → ".join(f"`{value}`" for value in row["sequence"]),
                        _sequence_shape_example(row),
                        f"`{row['category']}`",
                        _format_int(row["total_occurrences"]),
                        _format_int(row["explicit_batch"]),
                        _format_int(row["separate_direct_calls"]),
                        _format_int(row["failure_count"]),
                        _format_int(row["unknown_status_count"]),
                    ]
                    for row in candidates
                ),
            )
        )
    else:
        lines.append("No repeated candidate sequence observed.")
    lines.extend(
        [
            "",
            "## Boundaries and limitations",
            "",
            "- Physical JSONL order separates sources; files are never joined by timestamp.",
            "- Same-response evidence uses a following `token_usage_record.response_id`.",
            "- Output-only interruptions remain eligible but are labeled separately.",
            "- Assistant reasoning or messages, edits, other tools, and user/turn boundaries "
            "are preserved as intervening evidence.",
            "- Custom exec bundles with multiple shell calls are excluded as ambiguously ordered.",
            "- Compound shell expressions remain one invocation; syntactic segments are not "
            "promoted to sequence atoms.",
            "- Overlapping n-grams are windows, not independent observations.",
            "- Batch output is not attributed to individual subcommands.",
            "",
        ]
    )
    return "\n".join(lines)


def render_census_markdown(manifest: dict[str, Any]) -> str:
    summary = manifest["summary"]
    completeness = manifest["completeness"]
    budgets = manifest["budgets"]
    lines = [
        "# Codex Rollout Census Reconciliation",
        "",
        "Privacy-safe local snapshot metadata only. The manifest contains truncated "
        "hashes instead of absolute paths or session IDs.",
        "",
        "## Completeness",
        "",
        f"- Verdict: **{completeness['status']}**",
        f"- Exhaustive: {'yes' if completeness['exhaustive'] else 'no'}",
        f"- Full coverage failed: "
        f"{'yes' if completeness['full_coverage_failed'] else 'no'}",
        f"- Files found / eligible / scanned / omitted (not disjoint): "
        f"{_format_int(summary['files_found'])} / "
        f"{_format_int(summary['files_eligible'])} / "
        f"{_format_int(summary['files_scanned'])} / "
        f"{_format_int(summary['files_omitted'])}",
        f"- Current / archived files found: "
        f"{_format_int(summary['current_files_found'])} / "
        f"{_format_int(summary['archived_files_found'])}",
        f"- Current / archived files scanned: "
        f"{_format_int(summary['current_files_scanned'])} / "
        f"{_format_int(summary['archived_files_scanned'])}",
        f"- Distinct sessions / source-session instances: "
        f"{_format_int(summary['distinct_sessions'])} / "
        f"{_format_int(summary['session_source_instances'])}",
        f"- Total inventory bytes: {_format_int(summary['total_inventory_bytes'])}; "
        f"records: {_format_int(summary['records'])}",
        "",
        "Coverage failures: "
        + (
            ", ".join(f"`{reason}`" for reason in completeness["reasons"])
            if completeness["reasons"]
            else "none"
        ),
        "",
        "## Omissions and mutation evidence",
        "",
    ]
    lines.extend(
        _markdown_table(
            ["Reason", "Files/events"],
            (
                [f"`{reason}`", _format_int(count)]
                for reason, count in completeness["omitted_by_reason"].items()
            ),
        )
    )
    lines.extend(
        [
            "",
            f"- Duplicate rollout content: "
            f"{_format_int(summary['duplicate_rollout_files'])}",
            f"- Duplicate physical files: "
            f"{_format_int(summary['duplicate_physical_files'])}",
            f"- Reused session IDs across sources: "
            f"{_format_int(summary['reused_session_ids_across_sources'])}",
            f"- Changed during scan: {_format_int(summary['changed_files'])}",
            f"- Invalid UTF-8 / JSON records: "
            f"{_format_int(summary['invalid_utf8_records'])} / "
            f"{_format_int(summary['invalid_json_records'])}",
            f"- Oversized / partial trailing records: "
            f"{_format_int(summary['oversized_records'])} / "
            f"{_format_int(summary['partial_trailing_records'])}",
            "",
            "## Scan budgets",
            "",
        ]
    )
    lines.extend(
        _markdown_table(
            ["Budget", "Value"],
            (
                [f"`{name}`", _format_int(value)]
                for name, value in budgets.items()
            ),
        )
    )
    lines.extend(
        [
            "",
            "Duplicate physical files and exact duplicate rollout content are "
            "reconciled to the first deterministic path in the manifest and are not "
            "analyzed twice. Legitimately separate files with a reused session ID "
            "remain separate source histories.",
            "",
        ]
    )
    return "\n".join(lines)


def render_compilation_research_markdown(report: dict[str, Any]) -> str:
    research = report["compilation_output_research"]
    coverage = research["coverage"]
    gates = research["significance_gates"]
    counts = research["coverage_counts"]
    lines = [
        "# Compilation and Validation Output Research",
        "",
        "Research-only simulation. Raw commands, paths, diagnostics, outputs, prompts, "
        "and session IDs are not serialized.",
        "",
        "## Coverage",
        "",
        f"- Cohort: `{research['cohort_id']}`",
        f"- Coverage verdict: **{coverage['status']}**",
        f"- Exhaustive: {'yes' if coverage['exhaustive'] else 'no'}",
        f"- Classified validation commands: "
        f"{_format_int(counts['classification_taxonomy_commands'])}",
        f"- Matched outputs: {_format_int(counts['matched_outputs'])}",
        f"- Status certainty: "
        + (
            ", ".join(
                f"`{name}`={_format_int(value)}"
                for name, value in counts["status_certainty"].items()
            )
            or "unmeasured"
        ),
        "",
        "## Candidate simulations",
        "",
    ]
    lines.extend(
        _markdown_table(
            [
                "Candidate",
                "Eligible",
                "Transformed",
                "Skipped",
                "Original bytes",
                "Saved bytes",
                "Targeted savings",
                "All matched output",
                "Likely token range",
            ],
            (
                [
                    f"`{row['candidate_id']}`",
                    _format_int(row["eligible_outputs"]),
                    _format_int(row["transformed_outputs"]),
                    _format_int(row["skipped_outputs"]),
                    _format_int(row["original_targeted_bytes"]),
                    _format_int(row["saved_bytes"]),
                    f"{row['savings_fraction_of_targeted']:.1%}",
                    f"{row['fraction_of_all_matched_output_bytes']:.1%}",
                    (
                        f"{_format_int(row['estimated_observation_token_reduction']['lower'])}"
                        f"–{_format_int(row['estimated_observation_token_reduction']['upper'])}"
                    ),
                ]
                for row in research["candidate_outputs"]
            ),
        )
    )
    lines.extend(
        [
            "",
            f"Significance gates: "
            f"{_format_int(gates['minimum_saved_bytes_per_ecosystem_operation'])} "
            "saved bytes and "
            f"{gates['minimum_savings_fraction_of_targeted_bytes']:.0%} of targeted "
            "bytes for an ecosystem/operation.",
            "",
            f"**Conclusion:** {gates['conclusion']}",
            "",
            "## Ecosystem and operation comparison",
            "",
        ]
    )
    lines.extend(
        _markdown_table(
            [
                "Ecosystem",
                "Operation",
                "Calls",
                "Sessions",
                "Matched",
                "Original bytes",
                "Clean verified success",
                "Aggressive saved",
                "Conservative saved",
                "Terse failure saved",
                "Certainty",
            ],
            (
                [
                    f"`{row['ecosystem']}`",
                    f"`{row['operation']}`",
                    _format_int(row["calls"]),
                    _format_int(row["distinct_sessions"]),
                    _format_int(row["matched_outputs"]),
                    _format_int(row["output"]["captured_model_visible_bytes"]),
                    f"{row['clean_verified_success_rate']:.1%}",
                    _format_int(
                        row["simulations"].get("aggressive_success", {}).get(
                            "saved_bytes", 0
                        )
                    ),
                    _format_int(
                        row["simulations"].get("conservative_success", {}).get(
                            "saved_bytes", 0
                        )
                    ),
                    _format_int(
                        row["simulations"].get("terse_failure", {}).get(
                            "saved_bytes", 0
                        )
                    ),
                    ", ".join(
                        f"{name}={value}"
                        for name, value in row["status_certainty"].items()
                    )
                    or "unknown",
                ]
                for row in research["ecosystem_operations"]
            ),
        )
    )
    lines.extend(["", "## Packaging", ""])
    lines.extend(
        _markdown_table(
            ["Packaging", "Calls", "Matched", "Output bytes"],
            (
                [
                    f"`{row['packaging']}`",
                    _format_int(row["calls"]),
                    _format_int(row["matched_outputs"]),
                    _format_int(row["output"]["captured_model_visible_bytes"]),
                ]
                for row in research["packaging"]
            ),
        )
    )
    lines.extend(["", "## Normalized commands and shapes", ""])
    lines.extend(
        _markdown_table(
            [
                "Ecosystem",
                "Operation",
                "Family",
                "Shape",
                "Packaging",
                "Calls",
                "Sessions",
                "Matched",
                "Output bytes",
                "Aggressive saved",
                "Terse saved",
            ],
            (
                [
                    f"`{row['ecosystem']}`",
                    f"`{row['operation']}`",
                    f"`{row['family']}`",
                    f"`{row['shape']}`",
                    f"`{row['packaging']}`",
                    _format_int(row["calls"]),
                    _format_int(row["distinct_sessions"]),
                    _format_int(row["matched_outputs"]),
                    _format_int(row["output"]["captured_model_visible_bytes"]),
                    _format_int(
                        row["simulations"].get("aggressive_success", {}).get(
                            "saved_bytes", 0
                        )
                    ),
                    _format_int(
                        row["simulations"].get("terse_failure", {}).get(
                            "saved_bytes", 0
                        )
                    ),
                ]
                for row in research["commands"]
            ),
        )
    )
    lines.extend(["", "## Gated opportunities", ""])
    if research["gated_opportunities"]:
        lines.extend(
            _markdown_table(
                [
                    "Ecosystem",
                    "Operation",
                    "Candidate",
                    "Saved bytes",
                    "Targeted fraction",
                    "Both gates",
                ],
                (
                    [
                        f"`{row['ecosystem']}`",
                        f"`{row['operation']}`",
                        f"`{row['candidate_id']}`",
                        _format_int(row["saved_bytes"]),
                        f"{row['savings_fraction_of_targeted']:.1%}",
                        "yes" if row["significant"] else "no",
                    ]
                    for row in research["gated_opportunities"]
                ),
            )
        )
    else:
        lines.append("No measured simulation reached the gate inputs.")
    lines.extend(["", "## Syntax-only appearances", ""])
    if research["syntax_only"]:
        lines.extend(
            _markdown_table(
                ["Ecosystem", "Operation", "Family", "Shape", "Appearances"],
                (
                    [
                        f"`{row['ecosystem']}`",
                        f"`{row['operation']}`",
                        f"`{row['family']}`",
                        f"`{row['shape']}`",
                        _format_int(row["calls"]),
                    ]
                    for row in research["syntax_only"]
                ),
            )
        )
    else:
        lines.append("No validation syntax was found only in a compound shell form.")
    lines.extend(["", "## Required counterexamples", ""])
    lines.extend(
        _markdown_table(
            ["Case", "Required behavior"],
            (
                [f"`{row['case']}`", row["required_behavior"]]
                for row in research["counterexamples"]
            ),
        )
    )
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in research["limitations"])
    lines.append("")
    return "\n".join(lines)


def _validate_output_dir(path: Path) -> None:
    if path.exists() and path.is_symlink():
        raise AnalysisError("output directory may not be a symlink")
    if path.exists() and not path.is_dir():
        raise AnalysisError("output path exists and is not a directory")


def write_reports(
    report: dict[str, Any], output_dir: Path
) -> tuple[Path, Path, Path, Path, Path, Path]:
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
    sequence_markdown_path = output_dir / "command_sequence_report.md"
    sequence_json_path = output_dir / "command_sequence_report.json"
    markdown = render_markdown(report).encode("utf-8")
    machine = (json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    diagnostics = build_opaque_diagnostics(report)
    diagnostics_markdown = render_opaque_diagnostics_markdown(report).encode("utf-8")
    diagnostics_machine = (
        json.dumps(diagnostics, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    sequence = build_sequence_report(report)
    sequence_markdown = render_sequence_markdown(report).encode("utf-8")
    sequence_machine = (
        json.dumps(sequence, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    research_markdown_path = output_dir / "compilation_output_research.md"
    research_json_path = output_dir / "compilation_output_research.json"
    census_manifest_path = output_dir / "codex_history_census_manifest.json"
    census_summary_path = output_dir / "codex_history_census_summary.md"
    research_machine = (
        json.dumps(
            {
                "schema_version": report["schema_version"],
                "research_schema_version": report["compilation_output_research"][
                    "research_schema_version"
                ],
                **report["compilation_output_research"],
            },
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")
    census = report["codex_history_census"]
    census_machine = (
        json.dumps(census, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    research_markdown = render_compilation_research_markdown(report).encode("utf-8")
    census_markdown = render_census_markdown(census).encode("utf-8")
    for target, content in (
        (markdown_path, markdown),
        (json_path, machine),
        (diagnostics_markdown_path, diagnostics_markdown),
        (diagnostics_json_path, diagnostics_machine),
        (sequence_markdown_path, sequence_markdown),
        (sequence_json_path, sequence_machine),
        (research_markdown_path, research_markdown),
        (research_json_path, research_machine),
        (census_manifest_path, census_machine),
        (census_summary_path, census_markdown),
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
        sequence_markdown_path,
        sequence_json_path,
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
    parser.add_argument(
        "--full-history",
        action="store_true",
        help=(
            "scan current and archived rollouts without default date filtering; "
            "exit nonzero unless every eligible input is accounted for"
        ),
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--max-files",
        type=int,
        help=f"default: {DEFAULT_MAX_FILES}, or {FULL_HISTORY_MAX_FILES} for --full-history",
    )
    parser.add_argument(
        "--max-file-bytes",
        type=int,
        help=(
            f"default: {DEFAULT_MAX_FILE_BYTES}, or "
            f"{FULL_HISTORY_MAX_FILE_BYTES} for --full-history"
        ),
    )
    parser.add_argument(
        "--max-total-bytes",
        type=int,
        help=(
            f"default: {DEFAULT_MAX_TOTAL_BYTES}, or "
            f"{FULL_HISTORY_MAX_TOTAL_BYTES} for --full-history"
        ),
    )
    parser.add_argument(
        "--max-line-bytes",
        type=int,
        help=(
            f"default: {DEFAULT_MAX_LINE_BYTES}, or "
            f"{FULL_HISTORY_MAX_LINE_BYTES} for --full-history"
        ),
    )
    parser.add_argument(
        "--significance-min-bytes",
        type=int,
        default=DEFAULT_SIGNIFICANCE_MIN_BYTES,
        help="minimum saved bytes per ecosystem/operation (default: 102400)",
    )
    parser.add_argument(
        "--significance-min-fraction",
        type=float,
        default=DEFAULT_SIGNIFICANCE_MIN_FRACTION,
        help="minimum targeted-byte savings fraction from 0 to 1 (default: 0.20)",
    )
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
    if args.significance_min_bytes < 0:
        print(
            "analyze_codex_commands: --significance-min-bytes must be nonnegative",
            file=sys.stderr,
        )
        return 2
    if not 0 <= args.significance_min_fraction <= 1:
        print(
            "analyze_codex_commands: --significance-min-fraction must be between 0 and 1",
            file=sys.stderr,
        )
        return 2
    options = AnalysisOptions(
        codex_home=args.codex_home.expanduser(),
        sessions_dir=args.sessions_dir.expanduser() if args.sessions_dir else None,
        output_dir=args.output_dir.expanduser(),
        since=args.since,
        until=args.until,
        include_archived=args.include_archived,
        full_history=args.full_history,
        max_files=(
            args.max_files
            if args.max_files is not None
            else FULL_HISTORY_MAX_FILES
            if args.full_history
            else DEFAULT_MAX_FILES
        ),
        max_file_bytes=(
            args.max_file_bytes
            if args.max_file_bytes is not None
            else FULL_HISTORY_MAX_FILE_BYTES
            if args.full_history
            else DEFAULT_MAX_FILE_BYTES
        ),
        max_total_bytes=(
            args.max_total_bytes
            if args.max_total_bytes is not None
            else FULL_HISTORY_MAX_TOTAL_BYTES
            if args.full_history
            else DEFAULT_MAX_TOTAL_BYTES
        ),
        max_line_bytes=(
            args.max_line_bytes
            if args.max_line_bytes is not None
            else FULL_HISTORY_MAX_LINE_BYTES
            if args.full_history
            else DEFAULT_MAX_LINE_BYTES
        ),
        significance_min_bytes=args.significance_min_bytes,
        significance_min_fraction=args.significance_min_fraction,
        fingerprint_salt=args.fingerprint_salt,
    )
    try:
        state = scan_rollouts(options)
        report = build_report(state)
        (
            markdown_path,
            json_path,
            diagnostics_markdown_path,
            diagnostics_json_path,
            sequence_markdown_path,
            sequence_json_path,
        ) = write_reports(report, options.output_dir)
    except (AnalysisError, OSError) as exc:
        print(f"analyze_codex_commands: {exc}", file=sys.stderr)
        return 2
    coverage = report["coverage"]
    census = report["codex_history_census"]
    census_summary = census["summary"]
    completeness = census["completeness"]
    print(
        f"Coverage: {completeness['status']}"
        f"{' (exhaustive)' if completeness['exhaustive'] else ''}; "
        f"files found/scanned/omitted "
        f"{census_summary['files_found']}/"
        f"{census_summary['files_scanned']}/"
        f"{census_summary['files_omitted']} (omissions may be partial); "
        f"sessions {coverage['sessions']}; "
        f"current/archive scanned "
        f"{census_summary['current_files_scanned']}/"
        f"{census_summary['archived_files_scanned']}; "
        f"bytes {census_summary['total_inventory_bytes']}."
    )
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
    print(f"Sequence Markdown: {sequence_markdown_path}")
    print(f"Sequence JSON: {sequence_json_path}")
    print(
        "Compilation Research Markdown: "
        f"{options.output_dir / 'compilation_output_research.md'}"
    )
    print(
        "Compilation Research JSON: "
        f"{options.output_dir / 'compilation_output_research.json'}"
    )
    print(
        "Census Manifest: "
        f"{options.output_dir / 'codex_history_census_manifest.json'}"
    )
    print(
        "Census Summary: "
        f"{options.output_dir / 'codex_history_census_summary.md'}"
    )
    if completeness["full_coverage_failed"]:
        print(
            "analyze_codex_commands: full-history coverage failed: "
            + ", ".join(completeness["reasons"]),
            file=sys.stderr,
        )
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
