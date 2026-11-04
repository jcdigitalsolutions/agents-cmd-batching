"""Conservative, non-executing shell command analysis for local diagnostics."""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


OPAQUE_REASONS = (
    "null_byte_or_invalid",
    "shell_function_or_control_flow",
    "variable_or_command_expansion",
    "redirect_or_heredoc",
    "subshell_or_group",
    "command_sequence",
    "boolean_chain",
    "shell_pipeline",
    "multiline_script",
    "environment_assignment",
    "unsupported_quote_or_lexer",
    "unknown_or_other",
)

ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
SAFE_FAMILY_RE = re.compile(r"[A-Za-z0-9_.+-]{1,80}")
SAFE_OPTION_RE = re.compile(r"^--?[A-Za-z][A-Za-z0-9-]{0,40}$")
SAFE_SUBCOMMAND_RE = re.compile(r"[A-Za-z0-9:-]{1,40}")
TIMEOUT_DURATION_RE = re.compile(r"^\d+(?:\.\d+)?(?:[smhd])?$")
MAX_COMMAND_CHARS = 1024 * 1024
MAX_TOKENS = 4096
MAX_WRAPPER_DEPTH = 8

REDIRECT_OPERATORS = {"<", ">", "<<", ">>", "<<<", "<>", ">|", "&>", "&>>"}
PIPELINE_OPERATORS = {"|", "|&"}
BOOLEAN_OPERATORS = {"&&", "||"}
SEQUENCE_OPERATORS = {";", "&"}
GROUP_OPERATORS = {"(", ")", "{", "}"}
OPERATORS = tuple(
    sorted(
        REDIRECT_OPERATORS
        | PIPELINE_OPERATORS
        | BOOLEAN_OPERATORS
        | SEQUENCE_OPERATORS
        | GROUP_OPERATORS
        | {";;&", ";;", ";&"},
        key=len,
        reverse=True,
    )
)
CONTROL_WORDS = {
    "case",
    "coproc",
    "do",
    "done",
    "elif",
    "else",
    "esac",
    "fi",
    "for",
    "function",
    "if",
    "in",
    "select",
    "then",
    "time",
    "until",
    "while",
    "[[",
}
NON_EXECUTING_SHELL_BUILTINS = {"eval", "source", "."}

# Assignments to these names can change executable lookup, shell startup behavior,
# dynamic-loader behavior, or command parsing. They are never treated as benign.
CONTROL_ENVIRONMENT_NAMES = {
    "BASHOPTS",
    "BASH_ENV",
    "CDPATH",
    "ENV",
    "GLOBIGNORE",
    "HOME",
    "IFS",
    "LD_AUDIT",
    "LD_LIBRARY_PATH",
    "LD_PRELOAD",
    "NODE_OPTIONS",
    "PATH",
    "PERL5OPT",
    "PYTHONHOME",
    "PYTHONPATH",
    "RUBYOPT",
    "SHELLOPTS",
    "ZDOTDIR",
}


class ShellLexError(ValueError):
    """A bounded shell lexer rejection whose message never includes input text."""


@dataclass(frozen=True)
class LexToken:
    value: str
    kind: str
    origin: str = ""


@dataclass(frozen=True)
class ShellSegment:
    family: str
    shape: str
    control_position: str
    confidence: str = "partial"


@dataclass(frozen=True)
class ShellAnalysis:
    family: str
    shape: str
    confidence: str
    opaque_reason: str | None
    secondary_reasons: tuple[str, ...]
    segments: tuple[ShellSegment, ...]
    would_be_opaque_under_v1: bool
    leading_assignment: bool = False
    wrapper: str | None = None
    features: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Lexed:
    tokens: tuple[LexToken, ...]
    has_newline: bool
    has_expansion: bool
    has_heredoc: bool


@dataclass(frozen=True)
class _Executable:
    tokens: tuple[str, ...]
    leading_assignment: bool
    wrapper: str | None


def _safe_family(value: str) -> str:
    name = Path(value).name
    return name if SAFE_FAMILY_RE.fullmatch(name) else "<unknown>"


def _safe_option(token: str) -> str | None:
    candidate = token.split("=", 1)[0]
    if SAFE_OPTION_RE.fullmatch(candidate):
        return candidate
    if re.fullmatch(r"-\d+", token):
        return "-<n>"
    return None


def family_shape(tokens: Sequence[str]) -> tuple[str, str]:
    executable = _safe_family(tokens[0])
    options = [
        option
        for token in tokens[1:]
        if (option := _safe_option(token)) is not None
    ]

    if executable in {"python", "python3"} and len(tokens) >= 3 and tokens[1] == "-m":
        module = tokens[2] if SAFE_SUBCOMMAND_RE.fullmatch(tokens[2]) else "<module>"
        family = f"python -m {module}"
        args = [token for token in tokens[3:] if _safe_option(token) is None]
        return family, " ".join([family, *options, *("<selector>" for _ in args)])

    if executable == "git":
        subcommand = next(
            (token for token in tokens[1:] if not token.startswith("-")),
            "<subcommand>",
        )
        if not SAFE_SUBCOMMAND_RE.fullmatch(subcommand):
            subcommand = "<subcommand>"
        return "git", " ".join([executable, subcommand, *options])

    if executable in {"cargo", "go", "npm", "pnpm", "yarn"}:
        subcommand = next(
            (token for token in tokens[1:] if not token.startswith("-")),
            "<subcommand>",
        )
        if not SAFE_SUBCOMMAND_RE.fullmatch(subcommand):
            subcommand = "<subcommand>"
        return f"{executable} {subcommand}", " ".join(
            [executable, subcommand, *options]
        )

    if executable in {"rg", "grep"}:
        positional = sum(_safe_option(token) is None for token in tokens[1:])
        placeholders = ["<pattern>"]
        if positional > 1:
            placeholders.append("<paths>")
        return executable, " ".join([executable, *options, *placeholders])

    if executable in {"pytest", "unittest"}:
        positional = sum(_safe_option(token) is None for token in tokens[1:])
        return executable, " ".join(
            [executable, *options, *("<selector>" for _ in range(positional))]
        )

    positional = sum(_safe_option(token) is None for token in tokens[1:])
    return executable, " ".join(
        [executable, *options, *("<arg>" for _ in range(positional))]
    )


def _flush_word(
    tokens: list[LexToken],
    word: list[str],
    word_started: bool,
) -> bool:
    if not word_started:
        return False
    if len(tokens) >= MAX_TOKENS:
        raise ShellLexError("token limit reached")
    tokens.append(LexToken("".join(word), "word"))
    word.clear()
    return False


def _lex_shell(command: str) -> _Lexed:
    if "\x00" in command:
        raise ShellLexError("null byte")
    if len(command) > MAX_COMMAND_CHARS:
        raise ShellLexError("command limit reached")

    tokens: list[LexToken] = []
    word: list[str] = []
    word_started = False
    has_newline = False
    has_expansion = False
    has_heredoc = False
    index = 0

    def flush() -> None:
        nonlocal word_started
        word_started = _flush_word(tokens, word, word_started)

    while index < len(command):
        char = command[index]
        if char in " \t\f\v":
            flush()
            index += 1
            continue
        if char in "\r\n":
            flush()
            has_newline = True
            if char == "\r" and index + 1 < len(command) and command[index + 1] == "\n":
                index += 1
            if not tokens or tokens[-1].value not in SEQUENCE_OPERATORS:
                if len(tokens) >= MAX_TOKENS:
                    raise ShellLexError("token limit reached")
                tokens.append(LexToken(";", "op", "newline"))
            index += 1
            continue
        if char == "#" and not word_started:
            index += 1
            while index < len(command) and command[index] not in "\r\n":
                index += 1
            continue
        if char == "\\":
            if index + 1 >= len(command):
                raise ShellLexError("trailing escape")
            if command[index + 1] in "\r\n":
                has_newline = True
            word.append(command[index + 1])
            word_started = True
            index += 2
            continue
        if char == "'":
            word_started = True
            index += 1
            while index < len(command) and command[index] != "'":
                if command[index] in "\r\n":
                    has_newline = True
                word.append(command[index])
                index += 1
            if index >= len(command):
                raise ShellLexError("unterminated single quote")
            index += 1
            continue
        if char == '"':
            word_started = True
            index += 1
            while index < len(command) and command[index] != '"':
                current = command[index]
                if current in "\r\n":
                    has_newline = True
                if current == "\\":
                    if index + 1 >= len(command):
                        raise ShellLexError("trailing escape")
                    if command[index + 1] in "\r\n":
                        has_newline = True
                    word.append(command[index + 1])
                    index += 2
                    continue
                if current in "$`":
                    has_expansion = True
                word.append(current)
                index += 1
            if index >= len(command):
                raise ShellLexError("unterminated double quote")
            index += 1
            continue
        if char in "$`":
            has_expansion = True
            word.append(char)
            word_started = True
            index += 1
            continue

        operator = next(
            (value for value in OPERATORS if command.startswith(value, index)),
            None,
        )
        if operator is not None:
            flush()
            if (
                operator == "&"
                and tokens
                and tokens[-1].kind == "op"
                and tokens[-1].value in REDIRECT_OPERATORS
            ):
                origin = "redirection"
            else:
                origin = "operator"
            tokens.append(LexToken(operator, "op", origin))
            if operator in {"<<", "<<<"}:
                has_heredoc = True
            index += len(operator)
            continue

        word.append(char)
        word_started = True
        index += 1

    flush()
    while tokens and tokens[-1].kind == "op" and tokens[-1].value == ";":
        tokens.pop()
    return _Lexed(tuple(tokens), has_newline, has_expansion, has_heredoc)


def lex_simple_words(command: str) -> list[str]:
    """Tokenize a simple word-only command, preserving quoted operators as literals."""
    lexed = _lex_shell(command)
    if (
        not lexed.tokens
        or any(token.kind == "op" for token in lexed.tokens)
        or lexed.has_newline
        or lexed.has_expansion
        or lexed.has_heredoc
    ):
        raise ShellLexError("not a simple command")
    return [token.value for token in lexed.tokens]


def _would_be_opaque_under_v1(command: str) -> bool:
    if "\x00" in command or "\n" in command or "\r" in command:
        return True
    if len(command) > MAX_COMMAND_CHARS:
        return True
    lexer = shlex.shlex(command, posix=True, punctuation_chars="|&;<>()`")
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        words = list(lexer)
    except ValueError:
        return True
    if not words or any(word in {"|", "||", "&", "&&", ";", "(", ")", "<", ">", "<<", ">>"} for word in words):
        return True
    if any("$" in word or "`" in word for word in words):
        return True
    if ASSIGNMENT_RE.match(words[0]):
        return True
    return False


def _assignment_name(token: str) -> str | None:
    match = ASSIGNMENT_RE.match(token)
    return token[: match.end() - 1] if match else None


def _benign_assignment(token: str) -> bool:
    name = _assignment_name(token)
    return (
        name is not None
        and name.upper() not in CONTROL_ENVIRONMENT_NAMES
        and not any(char in token for char in "\x00\r\n")
    )


def _consume_env(
    tokens: Sequence[str],
    index: int,
) -> tuple[int, bool] | None:
    index += 1
    leading_assignment = False
    value_options = {"-u", "--unset", "-C", "--chdir"}
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            return index + 1, leading_assignment
        if _assignment_name(token) is not None:
            if not _benign_assignment(token):
                return None
            leading_assignment = True
            index += 1
            continue
        if token in {"-i", "--ignore-environment"}:
            index += 1
            continue
        if token in value_options:
            if index + 1 >= len(tokens):
                return None
            index += 2
            continue
        if token.startswith("--unset=") or token.startswith("--chdir="):
            index += 1
            continue
        if token.startswith("-"):
            return None
        return index, leading_assignment
    return None


def _consume_command(tokens: Sequence[str], index: int) -> int | None:
    index += 1
    while index < len(tokens):
        token = tokens[index]
        if token == "--" or token == "-p":
            index += 1
            continue
        if token.startswith("-"):
            return None
        return index
    return None


def _consume_timeout(tokens: Sequence[str], index: int) -> int | None:
    index += 1
    while index < len(tokens):
        token = tokens[index]
        if token in {"--preserve-status", "--foreground", "-v", "--verbose"}:
            index += 1
            continue
        if token in {"-s", "--signal", "-k", "--kill-after"}:
            if index + 1 >= len(tokens):
                return None
            index += 2
            continue
        if token.startswith("--signal=") or token.startswith("--kill-after="):
            index += 1
            continue
        if token.startswith("-"):
            return None
        if not TIMEOUT_DURATION_RE.fullmatch(token):
            return None
        index += 1
        return index if index < len(tokens) else None
    return None


def _resolve_executable(tokens: Sequence[str]) -> _Executable | None:
    if not tokens:
        return None
    values = tuple(token.value for token in tokens)

    def resolve(
        index: int,
        *,
        allow_assignments: bool,
        depth: int,
        leading_assignment: bool,
        wrapper: str | None,
    ) -> _Executable | None:
        if depth > MAX_WRAPPER_DEPTH:
            return None
        if allow_assignments:
            while index < len(values) and _assignment_name(values[index]) is not None:
                if not _benign_assignment(values[index]):
                    return None
                leading_assignment = True
                index += 1
        if index >= len(values):
            return None
        executable = _safe_family(values[index])
        if executable == "env":
            consumed = _consume_env(values, index)
            if consumed is None:
                return None
            next_index, wrapper_assignment = consumed
            return resolve(
                next_index,
                allow_assignments=False,
                depth=depth + 1,
                leading_assignment=leading_assignment or wrapper_assignment,
                wrapper=wrapper or executable,
            )
        if executable == "command":
            next_index = _consume_command(values, index)
            if next_index is None:
                return None
            return resolve(
                next_index,
                allow_assignments=False,
                depth=depth + 1,
                leading_assignment=leading_assignment,
                wrapper=wrapper or executable,
            )
        if executable == "timeout":
            next_index = _consume_timeout(values, index)
            if next_index is None:
                return None
            return resolve(
                next_index,
                allow_assignments=False,
                depth=depth + 1,
                leading_assignment=leading_assignment,
                wrapper=wrapper or executable,
            )
        if executable == "<unknown>" or _assignment_name(values[index]) is not None:
            return None
        return _Executable(values[index:], leading_assignment, wrapper)

    return resolve(
        0,
        allow_assignments=True,
        depth=0,
        leading_assignment=False,
        wrapper=None,
    )


def _control_flow_present(tokens: Sequence[LexToken]) -> bool:
    expect_command = True
    for position, token in enumerate(tokens):
        if token.kind == "op":
            if token.value in PIPELINE_OPERATORS | BOOLEAN_OPERATORS | SEQUENCE_OPERATORS:
                expect_command = True
            continue
        word = token.value.lower()
        if expect_command and word in NON_EXECUTING_SHELL_BUILTINS:
            return True
        if expect_command and word in CONTROL_WORDS:
            return True
        if (
            expect_command
            and "=" not in word
            and SAFE_FAMILY_RE.fullmatch(_safe_family(word))
            and len(tokens) >= 3
        ):
            if (
                position + 2 < len(tokens)
                and tokens[position + 1].kind == "op"
                and tokens[position + 1].value == "("
                and tokens[position + 2].kind == "op"
                and tokens[position + 2].value == ")"
            ):
                return True
        if not token.value.startswith("-") and _assignment_name(token.value) is None:
            expect_command = False
    return False


def _structural_reasons(command: str, lexed: _Lexed) -> tuple[list[str], set[str]]:
    reasons: list[str] = []
    features: set[str] = set()
    operator_values = [token.value for token in lexed.tokens if token.kind == "op"]
    word_values = [token.value.lower() for token in lexed.tokens if token.kind == "word"]

    if lexed.has_expansion:
        reasons.append("variable_or_command_expansion")
        features.add("contains_expansion")
    if lexed.has_heredoc or any(value in REDIRECT_OPERATORS for value in operator_values):
        reasons.append("redirect_or_heredoc")
        features.add("contains_heredoc" if lexed.has_heredoc else "contains_redirection")
    if any(value in GROUP_OPERATORS for value in operator_values):
        reasons.append("subshell_or_group")
        features.add("contains_grouping")
    if _control_flow_present(lexed.tokens):
        reasons.append("shell_function_or_control_flow")
        features.add("contains_control_flow")
    if any(
        token.value in SEQUENCE_OPERATORS
        and token.origin not in {"newline", "redirection"}
        for token in lexed.tokens
        if token.kind == "op"
    ):
        reasons.append("command_sequence")
        features.add("contains_command_sequence")
    if any(value in BOOLEAN_OPERATORS for value in operator_values):
        reasons.append("boolean_chain")
        features.add("contains_boolean_chain")
    if any(value in PIPELINE_OPERATORS for value in operator_values):
        reasons.append("shell_pipeline")
        features.add("contains_pipeline")
    if lexed.has_newline:
        reasons.append("multiline_script")
        features.add("contains_multiline")
    if word_values and _assignment_name(word_values[0]) is not None:
        reasons.append("environment_assignment")
        features.add("contains_leading_assignment")
    if not reasons:
        reasons.append("unknown_or_other")
        features.add("unknown_structure")
    return reasons, features


def _split_segments(tokens: Sequence[LexToken]) -> list[tuple[list[LexToken], str]] | None:
    if not tokens:
        return None
    segments: list[tuple[list[LexToken], str]] = []
    current: list[LexToken] = []
    position = "first"
    for token in tokens:
        if token.kind == "op" and (
            token.value in PIPELINE_OPERATORS
            or token.value in BOOLEAN_OPERATORS
            or (
                token.value in SEQUENCE_OPERATORS
                and token.origin != "redirection"
            )
            or token.origin == "newline"
        ):
            if not current:
                return None
            segments.append((current, position))
            current = []
            if token.value in PIPELINE_OPERATORS:
                position = "pipeline_stage"
            elif token.value in BOOLEAN_OPERATORS:
                position = "boolean_right"
            else:
                position = "sequence_next"
            continue
        current.append(token)
    if current:
        segments.append((current, position))
    return segments or None


def _strip_redirections(tokens: Sequence[LexToken]) -> list[LexToken] | None:
    result: list[LexToken] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        has_fd_prefix = (
            token.kind == "word"
            and token.value.isdigit()
            and index + 1 < len(tokens)
            and tokens[index + 1].kind == "op"
            and tokens[index + 1].value in REDIRECT_OPERATORS
        )
        if has_fd_prefix:
            index += 1
            token = tokens[index]
        if token.kind == "op" and token.value in REDIRECT_OPERATORS:
            index += 1
            if index >= len(tokens):
                return None
            if tokens[index].kind == "op" and tokens[index].value == "&":
                index += 1
                if index >= len(tokens) or tokens[index].kind != "word":
                    return None
                index += 1
                continue
            if tokens[index].kind != "word":
                return None
            index += 1
            continue
        if token.kind == "op":
            return None
        result.append(token)
        index += 1
    return result


def _syntactic_segments(lexed: _Lexed, reasons: Sequence[str]) -> tuple[ShellSegment, ...]:
    if lexed.has_heredoc:
        return ()
    unsafe_reasons = {
        "variable_or_command_expansion",
        "subshell_or_group",
        "shell_function_or_control_flow",
        "null_byte_or_invalid",
        "unsupported_quote_or_lexer",
    }
    if any(reason in unsafe_reasons for reason in reasons):
        return ()
    split = _split_segments(lexed.tokens)
    if split is None:
        return ()
    segments: list[ShellSegment] = []
    for raw_segment, position in split:
        stripped = _strip_redirections(raw_segment)
        if not stripped:
            return ()
        resolved = _resolve_executable(stripped)
        if resolved is None:
            return ()
        family, shape = family_shape(resolved.tokens)
        segments.append(ShellSegment(family, shape, position))
    return tuple(segments)


def analyze_shell_command(command: str) -> ShellAnalysis:
    """Return a privacy-safe analysis; malformed or uncertain forms remain opaque."""
    if "\x00" in command or len(command) > MAX_COMMAND_CHARS:
        return ShellAnalysis(
            "<opaque>",
            "<opaque shell form>",
            "opaque",
            "null_byte_or_invalid",
            (),
            (),
            True,
        )
    legacy_opaque = True
    try:
        legacy_opaque = _would_be_opaque_under_v1(command)
        lexed = _lex_shell(command)
        if not lexed.tokens:
            return ShellAnalysis(
                "<opaque>",
                "<opaque shell form>",
                "opaque",
                "unknown_or_other",
                (),
                (),
                legacy_opaque,
            )
    except (ShellLexError, ValueError, IndexError):
        return ShellAnalysis(
            "<opaque>",
            "<opaque shell form>",
            "opaque",
            "unsupported_quote_or_lexer",
            (),
            (),
            legacy_opaque,
        )

    try:
        reasons, features = _structural_reasons(command, lexed)
        explicit_reasons = [
            reason for reason in reasons if reason != "unknown_or_other"
        ]
        if not explicit_reasons:
            resolved = _resolve_executable(lexed.tokens)
            if resolved is not None:
                family, shape = family_shape(resolved.tokens)
                return ShellAnalysis(
                    family,
                    shape,
                    "high",
                    None,
                    (),
                    (),
                    legacy_opaque,
                    resolved.leading_assignment,
                    resolved.wrapper,
                    tuple(sorted(features - {"unknown_structure"})),
                )
            return ShellAnalysis(
                "<opaque>",
                "<opaque shell form>",
                "opaque",
                "unknown_or_other",
                (),
                (),
                legacy_opaque,
            )

        ordered = [reason for reason in OPAQUE_REASONS if reason in explicit_reasons]
        primary = ordered[0]
        secondary = tuple(ordered[1:])
        segments = _syntactic_segments(lexed, ordered)

        if primary == "environment_assignment" and not secondary:
            resolved = _resolve_executable(lexed.tokens)
            if resolved is not None:
                family, shape = family_shape(resolved.tokens)
                return ShellAnalysis(
                    family,
                    shape,
                    "high",
                    primary,
                    secondary,
                    (),
                    legacy_opaque,
                    resolved.leading_assignment,
                    resolved.wrapper,
                    tuple(sorted(features)),
                )

        confidence = "partial" if segments else "opaque"
        return ShellAnalysis(
            "<opaque>",
            "<opaque shell form>",
            confidence,
            primary,
            secondary,
            segments,
            legacy_opaque,
            features=tuple(sorted(features)),
        )
    except Exception:
        # A parser bug must not crash analysis or leak the private command.
        return ShellAnalysis(
            "<opaque>",
            "<opaque shell form>",
            "opaque",
            "unknown_or_other",
            (),
            (),
            legacy_opaque,
        )
