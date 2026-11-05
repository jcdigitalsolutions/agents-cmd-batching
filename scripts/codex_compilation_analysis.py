"""Conservative taxonomy and output simulations for local build/test research."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from codex_shell_analysis import ASSIGNMENT_RE, TIMEOUT_DURATION_RE, lex_simple_words


TAXONOMY_VERSION = 1
SUCCESS_OUTPUT = "Success!\n"

ECOSYSTEMS = ("rust", "go", "node-ts", "python", "c-cpp", "jvm", "dotnet", "other")
OPERATIONS = (
    "compile/build",
    "type/check",
    "lint",
    "test",
    "format",
    "package-script-unknown",
    "unknown",
)
FORMATTER_ECOSYSTEMS = {"rust", "go", "node-ts", "python"}
SUCCESS_OPERATIONS = {
    "compile/build",
    "type/check",
    "lint",
    "test",
}

PACKAGE_SCRIPTS = {
    "build": "compile/build",
    "compile": "compile/build",
    "check": "type/check",
    "typecheck": "type/check",
    "type-check": "type/check",
    "lint": "lint",
    "test": "test",
    "format": "format",
    "fmt": "format",
}
SAFE_SCRIPT_RE = re.compile(r"[A-Za-z][A-Za-z0-9:_-]{0,39}")
SAFE_FLAG_RE = re.compile(r"--[A-Za-z][A-Za-z0-9-]{0,40}")

UNSAFE_FAILURE_MARKERS = (
    "internal compiler error",
    "panicked at",
    "linker command failed",
    "undefined reference",
    "collect2:",
    "out of memory",
    "oom killed",
    "segmentation fault",
    "data race",
    "fatal runtime error",
)
CANCELLED_MARKERS = (
    "cancelled before completion",
    "canceled before completion",
    "command cancelled",
    "operation cancelled",
)
TIMEOUT_MARKERS = (
    "timed out",
    "timeout exceeded",
    "deadline exceeded",
)
TRUNCATION_MARKERS = (
    "output truncated",
    "truncated output",
    "max_output_tokens",
    "was truncated",
    "[... omitted",
)
SUCCESS_MARKERS = (
    "all tests passed",
    "test result: ok",
    "tests passed",
    "passed",
    "build succeeded",
    "compiled successfully",
    "completed: ",
    "[delayed-seq] completed",
    "finished ",
    "up to date",
)
FAILURE_TEXT_RE = re.compile(
    r"(?:\b[1-9]\d*\s+(?:tests?\s+)?failed\b|\bfailed\s+with\s+status\b)",
    re.I,
)


@dataclass(frozen=True)
class ValidationCommand:
    ecosystem: str
    operation: str
    family: str
    shape: str
    packaging: str
    formatter_eligible: bool
    confidence: str

    def as_dict(self) -> dict[str, object]:
        return {
            "ecosystem": self.ecosystem,
            "operation": self.operation,
            "family": self.family,
            "shape": self.shape,
            "packaging": self.packaging,
            "formatter_eligible": self.formatter_eligible,
            "confidence": self.confidence,
        }


def _executable_name(value: str) -> str:
    return value.rsplit("/", 1)[-1].lower()


def _unwrap_words(raw: str) -> list[str] | None:
    try:
        words = lex_simple_words(raw)
    except (ValueError, IndexError):
        return None
    index = 0
    while index < len(words) and ASSIGNMENT_RE.match(words[index]):
        index += 1
    while index < len(words):
        executable = _executable_name(words[index])
        if executable == "env":
            index += 1
            while index < len(words):
                token = words[index]
                if ASSIGNMENT_RE.match(token) or token in {"-i", "--ignore-environment"}:
                    index += 1
                    continue
                if token in {"-u", "--unset", "-C", "--chdir"}:
                    index += 2
                    continue
                if token.startswith(("--unset=", "--chdir=")):
                    index += 1
                    continue
                if token == "--":
                    index += 1
                break
            continue
        if executable == "command":
            index += 1
            while index < len(words) and words[index] in {"--", "-p"}:
                index += 1
            continue
        if executable == "timeout":
            index += 1
            while index < len(words):
                token = words[index]
                if token in {"--preserve-status", "--foreground", "-v", "--verbose"}:
                    index += 1
                    continue
                if token in {"-s", "--signal", "-k", "--kill-after"}:
                    index += 2
                    continue
                if token.startswith(("--signal=", "--kill-after=")):
                    index += 1
                    continue
                if token.startswith("-") or not TIMEOUT_DURATION_RE.fullmatch(token):
                    return None
                index += 1
                break
            continue
        break
    if index >= len(words):
        return None
    return words[index:]


def _subcommand(words: Sequence[str]) -> str:
    return next((word.lower() for word in words[1:] if not word.startswith("-")), "")


def _shape(executable: str, parts: Sequence[str], words: Sequence[str]) -> str:
    flags = [
        token.split("=", 1)[0]
        for token in words[1:]
        if SAFE_FLAG_RE.fullmatch(token.split("=", 1)[0])
    ]
    return " ".join([executable, *parts, *flags])


def _packaging(execution_form: str, parent_mixed: bool) -> str:
    if parent_mixed:
        return "mixed_unknown"
    if execution_form in {"shell_batch", "native_batch", "proxy_batch"}:
        return execution_form
    if execution_form == "direct":
        return "direct"
    return "mixed_unknown"


def _base(
    *,
    ecosystem: str,
    operation: str,
    family: str,
    shape: str,
    execution_form: str,
    parent_mixed: bool,
    confidence: str,
) -> ValidationCommand:
    return ValidationCommand(
        ecosystem=ecosystem,
        operation=operation,
        family=family,
        shape=shape,
        packaging=_packaging(execution_form, parent_mixed),
        formatter_eligible=(
            confidence == "high"
            and ecosystem in FORMATTER_ECOSYSTEMS
            and operation in SUCCESS_OPERATIONS
        ),
        confidence=confidence,
    )


def classify_validation_command(
    *,
    family: str,
    shape: str,
    raw: str,
    confidence: str,
    execution_form: str,
    parent_mixed: bool = False,
) -> ValidationCommand | None:
    """Return a versioned validation classification, or ``None`` for non-validation work."""
    words = _unwrap_words(raw) if confidence == "high" else None
    family_words = family.split()
    executable = (
        _executable_name(words[0])
        if words
        else _executable_name(family_words[0])
        if family_words
        else "<unknown>"
    )
    subcommand = (
        _subcommand(words)
        if words
        else family_words[1].lower()
        if len(family_words) > 1
        else ""
    )

    if executable in {"cargo", "rustc", "rustfmt", "cargo-nextest"}:
        if executable == "cargo":
            if subcommand == "nextest":
                variant = next(
                    (item.lower() for item in words[2:] if not item.startswith("-")),
                    "",
                )
                if variant == "run":
                    return _base(
                        ecosystem="rust",
                        operation="test",
                        family="cargo nextest run",
                        shape=_shape("cargo", ("nextest", "run"), words or ()),
                        execution_form=execution_form,
                        parent_mixed=parent_mixed,
                        confidence=confidence,
                    )
                return None
            mapping = {
                "build": "compile/build",
                "check": "type/check",
                "clippy": "lint",
                "test": "test",
                "fmt": "format",
            }
            operation = mapping.get(subcommand)
            if operation is None:
                return None
            return _base(
                ecosystem="rust",
                operation=operation,
                family=f"cargo {subcommand}",
                shape=_shape("cargo", (subcommand,), words or ()),
                execution_form=execution_form,
                parent_mixed=parent_mixed,
                confidence=confidence,
            )
        if executable == "cargo-nextest":
            if "run" not in (word.lower() for word in (words or ())[1:]):
                return None
            return _base(
                ecosystem="rust",
                operation="test",
                family="cargo nextest run",
                shape=_shape("cargo-nextest", ("nextest", "run"), words or ()),
                execution_form=execution_form,
                parent_mixed=parent_mixed,
                confidence=confidence,
            )
        operation = "format" if executable == "rustfmt" else "compile/build"
        return _base(
            ecosystem="rust",
            operation=operation,
            family=executable,
            shape=_shape(executable, (), words or ()),
            execution_form=execution_form,
            parent_mixed=parent_mixed,
            confidence=confidence,
        )

    if executable in {"go", "gofmt"}:
        if executable == "gofmt":
            operation = "format"
            family = "gofmt"
            parts: tuple[str, ...] = ()
        else:
            mapping = {
                "build": "compile/build",
                "test": "test",
                "vet": "type/check",
                "fmt": "format",
                "generate": "unknown",
            }
            operation = mapping.get(subcommand)
            if operation is None:
                return None
            family = f"go {subcommand}"
            parts = (subcommand,)
        return _base(
            ecosystem="go",
            operation=operation,
            family=family,
            shape=_shape(executable, parts, words or ()),
            execution_form=execution_form,
            parent_mixed=parent_mixed,
            confidence=confidence,
        )

    if executable in {"npm", "pnpm", "yarn", "bun"}:
        if not words:
            return None
        if subcommand in {"test", "build"}:
            operation = "test" if subcommand == "test" else "compile/build"
            return _base(
                ecosystem="node-ts",
                operation=operation,
                family=f"{executable} {subcommand}",
                shape=_shape(executable, (subcommand,), words),
                execution_form=execution_form,
                parent_mixed=parent_mixed,
                confidence=confidence,
            )
        if subcommand == "run":
            script = next(
                (
                    token
                    for token in words[2:]
                    if not token.startswith("-") and SAFE_SCRIPT_RE.fullmatch(token)
                ),
                "",
            )
            operation = PACKAGE_SCRIPTS.get(script)
            if operation is None:
                operation = "package-script-unknown"
                shaped_script = "<script>"
            else:
                shaped_script = script
            return _base(
                ecosystem="node-ts",
                operation=operation,
                family="package-script-unknown"
                if operation == "package-script-unknown"
                else f"{executable} run",
                shape=_shape(executable, ("run", shaped_script), words),
                execution_form=execution_form,
                parent_mixed=parent_mixed,
                confidence=confidence,
            )
        return _base(
            ecosystem="node-ts",
            operation="package-script-unknown",
            family=f"{executable} {subcommand or '<subcommand>'}",
            shape=_shape(executable, (subcommand or "<subcommand>",), words),
            execution_form=execution_form,
            parent_mixed=parent_mixed,
            confidence=confidence,
        )

    if executable == "npx" and words:
        index = 1
        boolean_options = {
            "--yes",
            "-y",
            "--no-install",
            "--ignore-existing",
            "--quiet",
            "--offline",
        }
        value_options = {"--package", "-p"}
        while index < len(words) and words[index].startswith("-"):
            if words[index] == "--":
                index += 1
                break
            if words[index] in value_options:
                index += 2
                continue
            if words[index].startswith("--package="):
                index += 1
                continue
            if words[index] not in boolean_options:
                return None
            index += 1
        if index < len(words):
            nested = _executable_name(words[index])
            return classify_validation_command(
                family=nested,
                shape=shape,
                raw=" ".join(words[index:]),
                confidence=confidence,
                execution_form=execution_form,
                parent_mixed=parent_mixed,
            )

    node_tools = {
        "tsc": ("type/check", "tsc"),
        "eslint": ("lint", "eslint"),
        "biome": ("lint", "biome"),
        "prettier": ("format", "prettier"),
        "vitest": ("test", "vitest"),
        "jest": ("test", "jest"),
        "deno": (None, "deno"),
    }
    if executable in node_tools:
        operation, canonical = node_tools[executable]
        if executable == "deno":
            operation = {"test": "test", "check": "type/check"}.get(subcommand)
            if operation is None:
                return None
            canonical = f"deno {subcommand}"
        return _base(
            ecosystem="node-ts",
            operation=operation,
            family=canonical,
            shape=_shape(
                executable,
                (subcommand,) if executable == "deno" else (),
                words or (),
            ),
            execution_form=execution_form,
            parent_mixed=parent_mixed,
            confidence=confidence,
        )

    if executable == "node":
        if "--test" in (words or ()):
            operation = "test"
            canonical = "node --test"
        elif "--check" in (words or ()):
            operation = "type/check"
            canonical = "node --check"
        else:
            return _base(
                ecosystem="node-ts",
                operation="unknown",
                family="node",
                shape=_shape("node", (), words or ()),
                execution_form=execution_form,
                parent_mixed=parent_mixed,
                confidence=confidence,
            )
        return _base(
            ecosystem="node-ts",
            operation=operation,
            family=canonical,
            shape=_shape("node", (), words or ()),
            execution_form=execution_form,
            parent_mixed=parent_mixed,
            confidence=confidence,
        )

    if executable == "uv" and words and len(words) >= 3:
        if words[1].lower() == "run":
            index = 2
            value_options = {
                "--with",
                "--python",
                "--project",
                "--directory",
                "--env-file",
                "--extra",
                "--group",
                "--index",
                "--index-url",
                "--refresh-package",
            }
            boolean_options = {
                "--no-sync",
                "--isolated",
                "--all-extras",
                "--all-groups",
                "--offline",
                "--frozen",
                "--locked",
                "--no-project",
                "--no-config",
                "--no-env-file",
                "--refresh",
            }
            while index < len(words):
                token = words[index]
                if token == "--":
                    index += 1
                    break
                if token in value_options:
                    index += 2
                    continue
                if any(
                    token.startswith(option + "=")
                    for option in value_options
                    if option.startswith("--")
                ):
                    index += 1
                    continue
                if token in boolean_options:
                    index += 1
                    continue
                if token.startswith("-"):
                    return None
                break
            if index >= len(words):
                return None
            nested = _executable_name(words[index])
            return classify_validation_command(
                family=f"{nested}",
                shape=shape,
                raw=" ".join(words[index:]),
                confidence=confidence,
                execution_form=execution_form,
                parent_mixed=parent_mixed,
            )

    python_tools = {
        "pytest": ("test", "pytest"),
        "unittest": ("test", "unittest"),
        "py_compile": ("compile/build", "py_compile"),
        "ruff": ("lint", "ruff check"),
        "mypy": ("type/check", "mypy"),
        "pyright": ("type/check", "pyright"),
    }
    if executable in {"python", "python3", "py"} and len(words or ()) >= 3:
        if words[1] == "-m":
            module = _executable_name(words[2])
            if module == "compileall":
                operation = "compile/build"
                canonical = "python -m compileall"
            elif module in {"pytest", "unittest"}:
                operation = "test"
                canonical = f"python -m {module}"
            elif module in {"py_compile", "mypy", "pyright"}:
                operation = "compile/build" if module == "py_compile" else "type/check"
                canonical = f"python -m {module}"
            elif module == "ruff":
                if len(words) < 4 or words[3] != "check":
                    return None
                operation = "lint"
                canonical = "ruff check"
            else:
                return None
            return _base(
                ecosystem="python",
                operation=operation,
                family=canonical,
                shape=(
                    " ".join(
                        [
                            canonical,
                            *[
                                token.split("=", 1)[0]
                                for token in words[3:]
                                if SAFE_FLAG_RE.fullmatch(
                                    token.split("=", 1)[0]
                                )
                            ],
                        ]
                    )
                ),
                execution_form=execution_form,
                parent_mixed=parent_mixed,
                confidence=confidence,
            )
    if executable in python_tools:
        operation, canonical = python_tools[executable]
        if executable == "ruff" and subcommand != "check":
            return None
        return _base(
            ecosystem="python",
            operation=operation,
            family=canonical,
            shape=_shape(executable, (subcommand,) if executable == "ruff" else (), words or ()),
            execution_form=execution_form,
            parent_mixed=parent_mixed,
            confidence=confidence,
        )

    c_cpp = {"gcc", "g++", "clang", "clang++", "cc", "c++"}
    if executable in c_cpp:
        return _base(
            ecosystem="c-cpp",
            operation="compile/build",
            family=executable,
            shape=_shape(executable, (), words or ()),
            execution_form=execution_form,
            parent_mixed=parent_mixed,
            confidence=confidence,
        )
    if executable in {"cmake", "meson"}:
        if executable == "cmake":
            if "--build" not in (words or ()):
                return None
            family = "cmake --build"
            parts = ("--build",)
        else:
            if subcommand != "compile":
                return None
            family = "meson compile"
            parts = ("compile",)
        return _base(
            ecosystem="c-cpp" if executable == "cmake" else "other",
            operation="compile/build",
            family=family,
            shape=_shape(executable, parts, words or ()),
            execution_form=execution_form,
            parent_mixed=parent_mixed,
            confidence=confidence,
        )
    if executable in {"make", "ninja"}:
        return _base(
            ecosystem="c-cpp",
            operation="compile/build",
            family=executable,
            shape=_shape(executable, (), words or ()),
            execution_form=execution_form,
            parent_mixed=parent_mixed,
            confidence=confidence,
        )

    if executable == "dotnet" and subcommand in {"build", "test"}:
        return _base(
            ecosystem="dotnet",
            operation="compile/build" if subcommand == "build" else "test",
            family=f"dotnet {subcommand}",
            shape=_shape("dotnet", (subcommand,), words or ()),
            execution_form=execution_form,
            parent_mixed=parent_mixed,
            confidence=confidence,
        )
    if executable in {"mvn", "mvnw", "gradle", "gradlew"}:
        if "test" not in (word.lower() for word in (words or ())[1:]):
            return None
        return _base(
            ecosystem="jvm",
            operation="test",
            family=f"{executable} test",
            shape=_shape(executable, ("test",), words or ()),
            execution_form=execution_form,
            parent_mixed=parent_mixed,
            confidence=confidence,
        )
    if executable == "forge" and subcommand in {"build", "test"}:
        return _base(
            ecosystem="other",
            operation="compile/build" if subcommand == "build" else "test",
            family=f"forge {subcommand}",
            shape=_shape("forge", (subcommand,), words or ()),
            execution_form=execution_form,
            parent_mixed=parent_mixed,
            confidence=confidence,
        )
    return None
def format_terse_failure(
    text: str,
    *,
    ecosystem: str,
    certainty: str,
    complete: bool,
    features: dict[str, bool],
) -> str | None:
    """Return a shorter actionable failure summary, or ``None`` for safe passthrough."""
    lower = text.lower()
    if (
        not complete
        or certainty not in {"failed_verified", "failure_text_inferred"}
        or ecosystem not in FORMATTER_ECOSYSTEMS
        or "\x00" in text
        or any(marker in lower for marker in UNSAFE_FAILURE_MARKERS)
        or any(marker in lower for marker in CANCELLED_MARKERS + TIMEOUT_MARKERS)
        or any(marker in lower for marker in TRUNCATION_MARKERS)
        or features.get("truncated", False)
        or features.get("separate_stdout_and_stderr", False)
    ):
        return None
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    kept: list[str] = []
    patterns: dict[str, tuple[re.Pattern[str], ...]] = {
        "rust": (
            re.compile(r"^(?:error(?:\[[A-Za-z0-9]+\])?|warning):"),
            re.compile(r"^\s*-->\s+\S+:\d+(?::\d+)?"),
            re.compile(r"^\s*= note:"),
        ),
        "go": (
            re.compile(r"^(?:#\s+\S+|FAIL(?:\s+|$)|--- FAIL:|warning:)"),
            re.compile(r"^\s*\S+\.go:\d+(?::\d+)?:"),
            re.compile(r"^\s*(?:panic|expected|actual|got|want):", re.I),
        ),
        "node-ts": (
            re.compile(r"^(?:npm ERR!|error TS\d+|warning\b|.*\berror\b.*)"),
            re.compile(r"^\s*(?:at\s+\S+|AssertionError(?::|$)|Expected|Received|FAIL\s+)"),
        ),
        "python": (
            re.compile(r"^(?:E{1,2}\s+|FAILED\s+|ERROR\s+|warning:)"),
            re.compile(r"^\s*File\s+\".+\",\s+line\s+\d+"),
            re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception)(?::|$)"),
            re.compile(r"^\s*\^+\s*$"),
        ),
    }
    for index, line in enumerate(lines):
        if any(pattern.search(line) for pattern in patterns[ecosystem]):
            kept.append(line)
            if (
                ecosystem == "rust"
                and re.match(r"^error(?:\[[A-Za-z0-9]+\])?:", line)
                and index + 1 < len(lines)
                and lines[index + 1].lstrip().startswith("-->")
            ):
                kept.append(lines[index + 1])
        elif (
            ecosystem == "rust"
            and kept
            and re.match(r"^\s*(?:help:|note:)", line)
        ):
            kept.append(line)

    if not kept:
        return None
    summary = "failure:\n" + "\n".join(dict.fromkeys(kept)) + "\n"
    original_bytes = len(text.encode("utf-8"))
    summary_bytes = len(summary.encode("utf-8"))
    return summary if summary_bytes < original_bytes else None
