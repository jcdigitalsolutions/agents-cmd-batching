"""Privacy-safe ordered command-sequence aggregation from Codex timeline events."""

from __future__ import annotations

import bisect
import collections
import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Sequence


SEQUENCE_SCHEMA_VERSION = 1
SEQUENCE_LENGTHS = (2, 3, 4)
EVENT_KINDS = (
    "user_turn",
    "assistant_decision_or_message",
    "shell_call",
    "shell_output",
    "non_shell_call",
    "non_shell_output",
    "edit",
    "other",
    "unknown",
    "response_boundary",
    "turn_boundary",
)
INTERVENING_CLASSES = (
    "none_observed",
    "tool_output_only",
    "assistant_decision_observed",
    "edit_or_other_tool",
    "user_turn_or_session_boundary",
    "unknown",
)
MODE_NAMES = (
    "explicit_batch",
    "separate_direct_calls",
    "mixed_batch_and_direct",
    "unknown",
)
DEFAULT_TOP_COUNTS = {2: 20, 3: 15, 4: 10}
MAX_TEXT_BUCKET = "10m_plus"


@dataclass(frozen=True)
class TimelineEvent:
    sequence_index: int
    source_key: str
    session_id: str
    record_index: int
    timestamp: str
    kind: str
    call_id: str = ""
    invocation_serial: int | None = None
    response_id: str | None = None
    turn_id: str | None = None
    bundle_id: str | None = None
    ordering_evidence: str = "ordered"


@dataclass
class _Node:
    source_key: str
    session_id: str
    record_index: int
    event_index: int
    invocation: Any
    response_id: str | None

    @property
    def serial(self) -> int:
        return int(self.invocation.serial)


@dataclass
class _Atom:
    node: _Node
    command: Any
    command_index: int


@dataclass
class _ModeStats:
    occurrences: int = 0
    sessions: set[str] = field(default_factory=set)
    session_instances: set[tuple[str, str]] = field(default_factory=set)
    same_response: int = 0
    confirmed: int = 0
    requested_only: int = 0
    invocation_occurrences: int = 0
    matched_calls: int = 0
    requested_atoms: int = 0
    confirmed_atoms: int = 0
    succeeded_atoms: int = 0
    failed_atoms: int = 0
    unknown_atoms: int = 0
    failed: int = 0
    succeeded: int = 0
    unknown_status: int = 0
    exclusive_output_bytes: int = 0
    intervening: collections.Counter[str] = field(default_factory=collections.Counter)


@dataclass
class _SequenceStats:
    mode: dict[str, _ModeStats] = field(
        default_factory=lambda: {name: _ModeStats() for name in MODE_NAMES}
    )
    sessions: set[str] = field(default_factory=set)
    confidence: tuple[str, ...] = ()
    unknown_reasons: collections.Counter[str] = field(
        default_factory=collections.Counter
    )
    shape_variants: collections.Counter[tuple[str, ...]] = field(
        default_factory=collections.Counter
    )

    @property
    def total(self) -> int:
        return sum(value.occurrences for value in self.mode.values())


@dataclass(frozen=True)
class _Occurrence:
    atoms: tuple[_Atom, ...]
    mode: str
    same_response: bool
    invocation_count: int
    matched_calls: int
    confirmed_atoms: int
    atom_statuses: tuple[str, ...]
    status: str
    exclusive_output_bytes: int
    intervening: tuple[str, ...]
    unknown_reason: str | None


def _ordered_events(events: Sequence[TimelineEvent]) -> list[TimelineEvent]:
    return sorted(
        events,
        key=lambda event: (
            event.source_key,
            event.record_index,
            event.sequence_index,
        ),
    )


def _assign_response_ids(
    events: Sequence[TimelineEvent],
) -> tuple[dict[int, str], int]:
    by_source: dict[str, list[TimelineEvent]] = collections.defaultdict(list)
    for event in events:
        by_source[event.source_key].append(event)
    response_by_serial: dict[int, str] = {}
    response_groups: set[str] = set()
    for source_events in by_source.values():
        pending: list[int] = []
        for event in source_events:
            if event.kind == "response_boundary":
                response_id = event.response_id or f"boundary:{event.sequence_index}"
                response_groups.add(f"{event.source_key}\0{response_id}")
                for serial in pending:
                    response_by_serial.setdefault(
                        serial, f"{event.source_key}\0{response_id}"
                    )
                pending.clear()
            elif event.kind in {
                "assistant_decision_or_message",
                "user_turn",
                "turn_boundary",
                "unknown",
            }:
                pending.clear()
            elif (
                event.kind == "shell_call"
                and event.invocation_serial is not None
                and event.ordering_evidence == "ordered"
                and event.bundle_id is None
            ):
                if event.invocation_serial not in pending:
                    pending.append(event.invocation_serial)
    return response_by_serial, len(response_groups)


def _first_call_events(events: Sequence[TimelineEvent]) -> dict[int, TimelineEvent]:
    result: dict[int, TimelineEvent] = {}
    for event in events:
        if event.kind != "shell_call" or event.invocation_serial is None:
            continue
        result.setdefault(event.invocation_serial, event)
    return result


def _status_for_invocation(invocation: Any) -> str:
    if invocation.dry_run or invocation.output is None:
        return "unknown"
    return invocation.status if invocation.status in {"success", "failed"} else "unknown"


def _atom_execution(invocation: Any, command_index: int) -> str:
    if invocation.dry_run:
        return "unknown"
    if invocation.execution_form == "direct":
        return _status_for_invocation(invocation)
    if invocation.output is None:
        return "unknown"
    succeeded = invocation.output.wrapper_succeeded
    failed = invocation.output.wrapper_failed
    if succeeded == len(invocation.subcommands) and failed == 0:
        return "success"
    if failed == 1 and command_index < succeeded:
        return "success"
    if failed == 1 and command_index == succeeded:
        return "failed"
    return "unknown"


def _parse_timestamp(value: str) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _elapsed_bucket(first: str, second: str) -> str:
    start = _parse_timestamp(first)
    end = _parse_timestamp(second)
    if start is None or end is None or end < start:
        return "unknown"
    seconds = (end - start).total_seconds()
    if seconds < 1:
        return "lt_1s"
    if seconds < 5:
        return "1s_to_5s"
    if seconds < 30:
        return "5s_to_30s"
    if seconds < 120:
        return "30s_to_2m"
    if seconds < 600:
        return "2m_to_10m"
    return MAX_TEXT_BUCKET


def _between(
    events: Sequence[TimelineEvent],
    record_indexes: Sequence[int],
    first: TimelineEvent,
    second: TimelineEvent,
) -> list[TimelineEvent]:
    start = bisect.bisect_right(record_indexes, first.record_index)
    end = bisect.bisect_left(record_indexes, second.record_index)
    return list(events[start:end])


def _edge_class(intervening: Sequence[TimelineEvent]) -> tuple[str, bool]:
    material = [
        event for event in intervening if event.kind != "response_boundary"
    ]
    if any(
        event.kind in {"user_turn", "turn_boundary", "unknown"}
        for event in material
    ):
        return "user_turn_or_session_boundary", False
    if any(
        event.kind in {"edit", "non_shell_call", "non_shell_output"}
        for event in material
    ):
        return "edit_or_other_tool", True
    if any(event.kind == "assistant_decision_or_message" for event in material):
        return "assistant_decision_observed", True
    if any(event.kind == "shell_output" for event in material):
        return "tool_output_only", True
    if not material:
        return "none_observed", True
    return "unknown", True


def _mode_for_atoms(atoms: Sequence[_Atom]) -> tuple[str, str | None]:
    if any(atom.node.invocation.bundle_id for atom in atoms):
        return "unknown", "custom_outer_bundle"
    batch_serials = {
        atom.node.serial for atom in atoms if atom.node.invocation.execution_form != "direct"
    }
    direct_present = any(
        atom.node.invocation.execution_form == "direct" for atom in atoms
    )
    if not batch_serials:
        return "separate_direct_calls", None
    if len(batch_serials) == 1 and direct_present:
        return "mixed_batch_and_direct", None
    if (
        len(batch_serials) == 1
        and not direct_present
        and all(atom.node.serial in batch_serials for atom in atoms)
    ):
        return "explicit_batch", None
    if len(batch_serials) > 1:
        return "unknown", "multiple_batch_boundaries"
    return "unknown", "unresolved_packaging"


def _occurrence(
    atoms: Sequence[_Atom],
    response_by_serial: dict[int, str],
    edges_by_pair: dict[tuple[int, int], dict[str, str]],
) -> _Occurrence:
    serials = list(dict.fromkeys(atom.node.serial for atom in atoms))
    atom_statuses = tuple(
        _atom_execution(atom.node.invocation, atom.command_index)
        for atom in atoms
    )
    matched_calls = sum(
        1
        for serial in serials
        for node in [next(atom.node for atom in atoms if atom.node.serial == serial)]
        if node.invocation.output is not None
    )
    confirmed_atoms = sum(status != "unknown" for status in atom_statuses)
    statuses = [
        _status_for_invocation(next(atom.node for atom in atoms if atom.node.serial == serial).invocation)
        for serial in serials
    ]
    if "failed" in statuses:
        status = "failed"
    elif statuses and all(value == "success" for value in statuses):
        status = "success"
    else:
        status = "unknown"
    exclusive_output_bytes = 0
    seen_serials: set[int] = set()
    for atom in atoms:
        node = atom.node
        if node.serial in seen_serials:
            continue
        seen_serials.add(node.serial)
        if (
            node.invocation.execution_form == "direct"
            and len(node.invocation.subcommands) == 1
            and node.invocation.subcommands[0].confidence == "high"
            and node.invocation.output is not None
        ):
            exclusive_output_bytes += node.invocation.output.metrics.bytes
    intervening: list[str] = []
    for first, second in zip(serials, serials[1:]):
        edge = edges_by_pair.get((first, second))
        if edge is not None:
            intervening.append(edge["class"])
    same_response_values = [response_by_serial.get(serial) for serial in serials]
    same_response = (
        all(atom.node.invocation.execution_form == "direct" for atom in atoms)
        and all(value is not None for value in same_response_values)
        and len(set(same_response_values)) == 1
    )
    mode, unknown_reason = _mode_for_atoms(atoms)
    return _Occurrence(
        atoms=tuple(atoms),
        mode=mode,
        same_response=same_response,
        invocation_count=len(serials),
        matched_calls=matched_calls,
        confirmed_atoms=confirmed_atoms,
        atom_statuses=atom_statuses,
        status=status,
        exclusive_output_bytes=exclusive_output_bytes,
        intervening=tuple(intervening),
        unknown_reason=unknown_reason,
    )


def _candidate_category(row: dict[str, Any], granularity: str) -> str:
    if granularity != "family":
        return "shape_only"
    identities = [item["identity"] for item in row["sequence"]]
    already = row["explicit_batch"] > 0
    separate = row["separate_direct_calls"] > 0
    mixed_or_unknown = row["mixed"] > 0 or row["unknown"] > 0
    formatters = {"cargo fmt", "gofmt", "rustfmt", "prettier", "npm format", "pnpm format"}
    validators = {
        "cargo test",
        "cargo clippy",
        "cargo check",
        "cargo build",
        "go test",
        "go vet",
        "pytest",
        "python -m pytest",
        "python -m unittest",
        "npm test",
        "pnpm test",
        "yarn test",
        "eslint",
        "ruff",
        "mypy",
        "tsc",
    }
    source_reads = {"cat", "head", "tail", "sed", "rg", "grep", "find", "ls", "git"}
    if already and separate:
        if row["observed_status"]["failed"] > 0:
            return "decision_dependent"
        return "mixed_evidence_requires_review"
    if mixed_or_unknown:
        if row["observed_status"]["failed"] > 0:
            return "decision_dependent"
        return "unsafe_or_ambiguous"
    if already:
        if row["observed_status"]["failed"] > 0:
            return "decision_dependent"
        return "already_batched"
    if row["observed_status"]["failed"] > 0:
        return "decision_dependent"
    if all(
        identity in formatters | validators
        for identity in identities
    ) and (
        identities[0] in formatters
        or all(identity in validators for identity in identities[1:])
    ):
        return "plausible_static_sequence"
    if identities and identities[0] in source_reads:
        return "decision_dependent"
    return "unsafe_or_ambiguous"


def _row_for_key(
    granularity: str,
    key: tuple[Any, ...],
    stats: _SequenceStats,
) -> dict[str, Any]:
    identities = [
        {
            "identity": identity,
            "confidence": confidence,
        }
        for identity, confidence in zip(key[0], key[1])
    ]
    modes = stats.mode
    explicit = modes["explicit_batch"].occurrences
    separate = modes["separate_direct_calls"].occurrences
    mixed = modes["mixed_batch_and_direct"].occurrences
    unknown = modes["unknown"].occurrences
    eligible = explicit + separate
    explicit_direct_session_instances = (
        modes["explicit_batch"].session_instances
        & modes["separate_direct_calls"].session_instances
    )
    matched_invocations = sum(
        value.matched_calls for value in stats.mode.values()
    )
    matched_invocation_occurrences = sum(
        value.invocation_occurrences for value in stats.mode.values()
    )
    session_instances = set().union(
        *(value.session_instances for value in stats.mode.values())
    )
    confirmed_executed_atoms = sum(
        value.confirmed_atoms for value in stats.mode.values()
    )
    requested_atoms = sum(value.requested_atoms for value in stats.mode.values())
    success_occurrences = sum(
        value.succeeded for value in stats.mode.values()
    )
    failed_occurrences = sum(value.failed for value in stats.mode.values())
    row: dict[str, Any] = {
        "granularity": granularity,
        "sequence": identities,
        "total": stats.total,
        "explicit_batch": explicit,
        "separate_direct_calls": separate,
        "mixed": mixed,
        "unknown": unknown,
        "distinct_sessions": len(stats.sessions),
        "distinct_session_instances": len(session_instances),
        "distinct_sessions_by_mode": {
            name: len(stats.mode[name].sessions) for name in MODE_NAMES
        },
        "by_mode": {
            name: {
                "occurrences": value.occurrences,
                "distinct_sessions": len(value.sessions),
                "distinct_session_instances": len(value.session_instances),
                "same_response_inferred": value.same_response,
                "confirmed_executed_occurrences": value.confirmed,
                "requested_only_occurrences": value.requested_only,
                "invocation_occurrences": value.invocation_occurrences,
                "matched_invocations": value.matched_calls,
                "matched_invocation_rate": (
                    round(
                        value.matched_calls / value.invocation_occurrences,
                        6,
                    )
                    if value.invocation_occurrences
                    else None
                ),
                "requested_subcommands": value.requested_atoms,
                "confirmed_executed_subcommands": value.confirmed_atoms,
                "unknown_subcommand_statuses": (
                    value.requested_atoms - value.confirmed_atoms
                ),
                "subcommand_status": {
                    "success": value.succeeded_atoms,
                    "failed": value.failed_atoms,
                    "unknown": value.unknown_atoms,
                },
                "observed_status": {
                    "success": value.succeeded,
                    "failed": value.failed,
                    "unknown": value.unknown_status,
                },
                "exclusive_output_bytes": value.exclusive_output_bytes,
                "intervening_events": dict(sorted(value.intervening.items())),
            }
            for name, value in modes.items()
        },
        "parser_confidence": list(stats.confidence),
        "same_response_inferred": modes["separate_direct_calls"].same_response,
        "confirmed_executed_occurrences": sum(
            value.confirmed for value in stats.mode.values()
        ),
        "requested_only_occurrences": sum(
            value.requested_only for value in stats.mode.values()
        ),
        "invocation_occurrences": matched_invocation_occurrences,
        "matched_invocations": matched_invocations,
        "matched_invocation_rate": (
            round(matched_invocations / matched_invocation_occurrences, 6)
            if matched_invocation_occurrences
            else None
        ),
        "requested_subcommands": requested_atoms,
        "confirmed_executed_subcommands": confirmed_executed_atoms,
        "unknown_subcommand_statuses": requested_atoms - confirmed_executed_atoms,
        "subcommand_status": {
            "success": sum(
                value.succeeded_atoms for value in stats.mode.values()
            ),
            "failed": sum(value.failed_atoms for value in stats.mode.values()),
            "unknown": sum(
                value.unknown_atoms for value in stats.mode.values()
            ),
        },
        "observed_status": {
            "success": success_occurrences,
            "failed": failed_occurrences,
            "unknown": sum(value.unknown_status for value in stats.mode.values()),
        },
        "failure_rate": (
            round(failed_occurrences / (success_occurrences + failed_occurrences), 6)
            if success_occurrences + failed_occurrences
            else None
        ),
        "exclusive_output_bytes": sum(
            value.exclusive_output_bytes for value in stats.mode.values()
        ),
        "intervening_events": dict(
            sorted(
                sum(
                    (value.intervening for value in stats.mode.values()),
                    collections.Counter(),
                ).items()
            )
        ),
        "batched_fraction": (
            round(explicit / eligible, 6) if eligible else None
        ),
        "batched_fraction_denominator": eligible,
        "unbatched_same_response_count": (
            modes["separate_direct_calls"].same_response
        ),
        "unbatched_same_response_fraction": (
            round(modes["separate_direct_calls"].same_response / eligible, 6)
            if eligible
            else None
        ),
        "unbatched_same_response_denominator": eligible,
        "cross_mode_repeat": explicit > 0 and separate > 0,
        "cross_mode_same_response_repeat": (
            explicit > 0 and modes["separate_direct_calls"].same_response > 0
        ),
        "within_session_mode_overlap": {
            "explicit_and_direct_session_instances": len(
                explicit_direct_session_instances
            ),
        },
        "unknown_reasons": dict(sorted(stats.unknown_reasons.items())),
        "shape_variants": [
            {
                "shape_sequence": list(identities),
                "occurrences": count,
            }
            for identities, count in sorted(
                stats.shape_variants.items(),
                key=lambda item: (-item[1], item[0]),
            )[:5]
        ],
    }
    row["candidate_category"] = _candidate_category(row, granularity)
    return row


def build_sequence_analysis(
    events: Sequence[TimelineEvent],
    calls: Sequence[Any],
) -> dict[str, Any]:
    ordered = _ordered_events(events)
    response_by_serial, response_group_count = _assign_response_ids(ordered)
    call_by_serial = {int(call.serial): call for call in calls}
    first_events = _first_call_events(ordered)
    event_kind_counts = collections.Counter(event.kind for event in ordered)

    events_by_source: dict[str, list[TimelineEvent]] = collections.defaultdict(list)
    for event in ordered:
        events_by_source[event.source_key].append(event)
    source_session_pairs = {
        (event.source_key, event.session_id) for event in ordered
    }

    nodes_by_source: dict[str, list[_Node]] = collections.defaultdict(list)
    excluded_invocations = 0
    excluded_commands = 0
    ambiguous_ordering_invocations = 0
    for source_key, source_events in events_by_source.items():
        seen_serials: set[int] = set()
        for event in source_events:
            if event.kind != "shell_call" or event.invocation_serial is None:
                continue
            serial = event.invocation_serial
            if serial in seen_serials or serial not in call_by_serial:
                continue
            seen_serials.add(serial)
            invocation = call_by_serial[serial]
            if event.ordering_evidence != "ordered":
                ambiguous_ordering_invocations += 1
                excluded_invocations += 1
                excluded_commands += len(invocation.subcommands)
                continue
            commands_supported = bool(invocation.subcommands) and all(
                command.confidence == "high" for command in invocation.subcommands
            )
            useful = (
                commands_supported
                and (
                    (
                        invocation.execution_form == "direct"
                        and len(invocation.subcommands) == 1
                    )
                    or (
                        invocation.execution_form != "direct"
                        and len(invocation.subcommands) >= 2
                    )
                )
            )
            if not useful:
                excluded_invocations += 1
                excluded_commands += len(invocation.subcommands)
                continue
            nodes_by_source[source_key].append(
                _Node(
                    source_key=source_key,
                    session_id=event.session_id,
                    record_index=event.record_index,
                    event_index=event.sequence_index,
                    invocation=invocation,
                    response_id=response_by_serial.get(serial),
                )
            )

    chains: list[list[_Node]] = []
    edge_rows: list[dict[str, Any]] = []
    edges_by_pair: dict[tuple[int, int], dict[str, str]] = {}
    intervening_histogram: collections.Counter[str] = collections.Counter()
    elapsed_histogram: collections.Counter[str] = collections.Counter()
    boundary_evidence: collections.Counter[str] = collections.Counter()
    hard_boundaries = 0
    direct_edges_classified = 0
    eligible_direct_edges = 0

    for source_key, nodes in nodes_by_source.items():
        nodes.sort(key=lambda node: (node.record_index, node.event_index))
        current_chain: list[_Node] = []
        source_events = events_by_source[source_key]
        source_record_indexes = [
            event.record_index for event in source_events
        ]
        for index, node in enumerate(nodes):
            if not current_chain:
                current_chain = [node]
                continue
            previous = nodes[index - 1]
            first_event = first_events[previous.serial]
            second_event = first_events[node.serial]
            between = _between(
                source_events,
                source_record_indexes,
                first_event,
                second_event,
            )
            edge_class, eligible = _edge_class(between)
            same_response = (
                previous.response_id is not None
                and previous.response_id == node.response_id
                and previous.invocation.execution_form == "direct"
                and node.invocation.execution_form == "direct"
            )
            if same_response:
                evidence = "same_response_inferred"
            elif previous.response_id is not None and node.response_id is not None:
                evidence = "separate_response_observed"
            else:
                evidence = "unknown_response_boundary"
            both_direct = (
                previous.invocation.execution_form == "direct"
                and node.invocation.execution_form == "direct"
            )
            if both_direct:
                direct_edges_classified += 1
                if eligible:
                    eligible_direct_edges += 1
            boundary_evidence[evidence] += 1
            intervening_histogram[edge_class] += 1
            elapsed_histogram[_elapsed_bucket(first_event.timestamp, second_event.timestamp)] += 1
            edge = {
                "class": edge_class,
                "evidence": evidence,
                "elapsed": _elapsed_bucket(first_event.timestamp, second_event.timestamp),
                "eligible": eligible,
            }
            edges_by_pair[(previous.serial, node.serial)] = edge
            edge_rows.append(edge)
            if not eligible:
                hard_boundaries += 1
                chains.append(current_chain)
                current_chain = [node]
            else:
                current_chain.append(node)
        if current_chain:
            chains.append(current_chain)

    aggregate: dict[tuple[str, tuple[Any, ...]], _SequenceStats] = {}
    occurrences_by_length = collections.Counter()
    non_overlapping_by_length = collections.Counter()
    for chain in chains:
        atoms = [
            _Atom(node, command, index)
            for node in chain
            for index, command in enumerate(node.invocation.subcommands)
        ]
        for length in SEQUENCE_LENGTHS:
            occurrences_by_length[length] += max(0, len(atoms) - length + 1)
            non_overlapping_by_length[length] += len(atoms) // length
            for start in range(len(atoms) - length + 1):
                window = atoms[start : start + length]
                occurrence = _occurrence(window, response_by_serial, edges_by_pair)
                for granularity in ("family", "shape"):
                    identities = tuple(
                        (
                            atom.command.family
                            if granularity == "family"
                            else atom.command.shape
                        )
                        for atom in window
                    )
                    confidences = tuple(
                        atom.command.confidence for atom in window
                    )
                    key = (granularity, identities, confidences)
                    stats = aggregate.setdefault(key, _SequenceStats(confidence=confidences))
                    if granularity == "family":
                        stats.shape_variants[
                            tuple(atom.command.shape for atom in window)
                        ] += 1
                    mode = stats.mode[occurrence.mode]
                    mode.occurrences += 1
                    mode.sessions.add(window[0].node.session_id)
                    mode.session_instances.add(
                        (window[0].node.source_key, window[0].node.session_id)
                    )
                    stats.sessions.add(window[0].node.session_id)
                    if occurrence.same_response:
                        mode.same_response += 1
                    if occurrence.confirmed_atoms == len(window):
                        mode.confirmed += 1
                    else:
                        mode.requested_only += 1
                    mode.invocation_occurrences += occurrence.invocation_count
                    mode.matched_calls += occurrence.matched_calls
                    mode.requested_atoms += len(window)
                    mode.confirmed_atoms += occurrence.confirmed_atoms
                    mode.succeeded_atoms += occurrence.atom_statuses.count("success")
                    mode.failed_atoms += occurrence.atom_statuses.count("failed")
                    mode.unknown_atoms += occurrence.atom_statuses.count("unknown")
                    if occurrence.status == "failed":
                        mode.failed += 1
                    elif occurrence.status == "success":
                        mode.succeeded += 1
                    else:
                        mode.unknown_status += 1
                    mode.exclusive_output_bytes += occurrence.exclusive_output_bytes
                    mode.intervening.update(occurrence.intervening)
                    if occurrence.unknown_reason is not None:
                        stats.unknown_reasons[occurrence.unknown_reason] += 1

    rows_by_granularity: dict[str, list[dict[str, Any]]] = {
        "family": [],
        "shape": [],
    }
    repeated_identity_counts: collections.Counter[tuple[str, int]] = collections.Counter()
    for (granularity, identities, confidences), stats in aggregate.items():
        if stats.total < 2:
            continue
        row = _row_for_key(
            granularity,
            (identities, confidences),
            stats,
        )
        rows_by_granularity[granularity].append(row)
        repeated_identity_counts[(granularity, len(identities))] += 1

    ranking: dict[str, list[dict[str, Any]]] = {}
    explicit_batches: dict[str, list[dict[str, Any]]] = {}
    direct_sequences: dict[str, list[dict[str, Any]]] = {}
    cross_mode: dict[str, list[dict[str, Any]]] = {}
    cross_mode_same_response: dict[str, list[dict[str, Any]]] = {}
    for granularity, rows in rows_by_granularity.items():
        rows.sort(
            key=lambda row: (
                -row["total"],
                -row["cross_mode_repeat"],
                tuple(item["identity"] for item in row["sequence"]),
            )
        )
        for length in SEQUENCE_LENGTHS:
            length_rows = [row for row in rows if len(row["sequence"]) == length]
            ranking[f"{granularity}_{length}"] = length_rows[: DEFAULT_TOP_COUNTS[length]]
            explicit_batches[f"{granularity}_{length}"] = sorted(
                (row for row in length_rows if row["explicit_batch"] > 0),
                key=lambda row: (-row["explicit_batch"], -row["total"]),
            )[:10]
            direct_sequences[f"{granularity}_{length}"] = sorted(
                (row for row in length_rows if row["separate_direct_calls"] > 0),
                key=lambda row: (
                    -row["unbatched_same_response_count"],
                    -row["separate_direct_calls"],
                    -row["total"],
                ),
            )[:10]
            cross_mode[f"{granularity}_{length}"] = [
                row for row in length_rows if row["cross_mode_repeat"]
            ][:10]
            cross_mode_same_response[f"{granularity}_{length}"] = [
                row
                for row in length_rows
                if row["cross_mode_same_response_repeat"]
            ][:10]

    transitions = _transition_analysis(chains)
    candidates = _candidate_rows(rows_by_granularity["family"])

    batch_requested = 0
    batch_confirmed = 0
    shell_calls_with_timeline = sum(
        1
        for serial in call_by_serial
        if serial in first_events
    )
    matched_shell_invocations = sum(
        1 for call in calls if call.output is not None
    )
    for call in calls:
        if call.execution_form == "direct":
            continue
        batch_requested += len(call.subcommands)
        if call.output is not None and not call.dry_run:
            batch_confirmed += call.output.wrapper_succeeded + call.output.wrapper_failed

    return {
        "sequence_schema_version": SEQUENCE_SCHEMA_VERSION,
        "coverage": {
            "source_files": len(events_by_source),
            "sessions": len({event.session_id for event in ordered}),
            "source_session_occurrences": len(source_session_pairs),
            "reused_session_ids_across_sources": max(
                0,
                len(source_session_pairs)
                - len({event.session_id for event in ordered}),
            ),
            "timeline_events": len(ordered),
            "timeline_event_kinds": dict(sorted(event_kind_counts.items())),
            "response_groups_observed": response_group_count,
            "shell_invocations_with_timeline": shell_calls_with_timeline,
            "matched_shell_invocations": matched_shell_invocations,
            "shell_invocations_excluded_from_sequences": excluded_invocations,
            "commands_excluded_from_sequences": excluded_commands,
            "ambiguous_ordering_invocations_excluded": ambiguous_ordering_invocations,
            "requested_batch_subcommands": batch_requested,
            "confirmed_executed_batch_subcommands": batch_confirmed,
            "unknown_batch_subcommand_statuses": max(0, batch_requested - batch_confirmed),
            "direct_edges_classified": len(edge_rows),
            "direct_only_edges_classified": direct_edges_classified,
            "eligible_direct_only_edges": eligible_direct_edges,
            "hard_boundaries": hard_boundaries,
            "eligible_edges": len(edge_rows) - hard_boundaries,
            "occurrences_by_length": {
                str(length): occurrences_by_length[length] for length in SEQUENCE_LENGTHS
            },
            "non_overlapping_occurrences_by_length": {
                str(length): non_overlapping_by_length[length]
                for length in SEQUENCE_LENGTHS
            },
            "repeated_sequences_by_granularity_and_length": {
                f"{granularity}_{length}": repeated_identity_counts[
                    (granularity, length)
                ]
                for granularity in ("family", "shape")
                for length in SEQUENCE_LENGTHS
            },
        },
        "ranking": ranking,
        "explicit_batch_sequences": explicit_batches,
        "direct_sequences": direct_sequences,
        "cross_mode_repeats": cross_mode,
        "cross_mode_same_response_repeats": cross_mode_same_response,
        "transitions": transitions,
        "intervening_event_histogram": dict(
            sorted(intervening_histogram.items())
        ),
        "elapsed_time_histogram": dict(sorted(elapsed_histogram.items())),
        "response_boundary_evidence": dict(sorted(boundary_evidence.items())),
        "batching_candidates": candidates,
        "methodology": {
            "ordering": "physical rollout order within one source file",
            "canonical_key": (
                "granularity, ordered command identities, and parser confidence; "
                "packaging is excluded from the key"
            ),
            "same_response": (
                "Assigned only from a following token_usage_record response_id; "
                "not inferred from timestamps."
            ),
            "overlapping_windows": True,
            "non_overlapping_metric": (
                "Greedy floor(window_count / sequence_length) per ordered chain; "
                "reported separately and not used for ranking."
            ),
            "mixed_boundary_policy": (
                "Windows spanning exactly one explicit batch and direct calls are "
                "mixed; windows spanning multiple batches are unknown."
            ),
        },
        "limitations": [
            "Physical adjacency and observed reasoning do not prove hidden model decisions.",
            "Same-response calls may have been issued concurrently; order is rollout order.",
            "Delayed-sequence output does not identify per-subcommand output ownership.",
            "Sequence counts use overlapping windows and are not independent samples.",
            "No command is executed or rewritten from rollout history.",
        ],
    }


def _transition_analysis(
    chains: Sequence[Sequence[_Node]],
) -> dict[str, Any]:
    pair_counts: collections.Counter[tuple[str, str]] = collections.Counter()
    pair_sessions: dict[tuple[str, str], set[str]] = collections.defaultdict(set)
    pair_output_bytes: collections.Counter[tuple[str, str]] = collections.Counter()
    source_counts: collections.Counter[str] = collections.Counter()
    source_sessions: dict[str, set[str]] = collections.defaultdict(set)
    for chain in chains:
        atoms = [
            _Atom(node, command, index)
            for node in chain
            for index, command in enumerate(node.invocation.subcommands)
        ]
        for first, second in zip(atoms, atoms[1:]):
            pair = (first.command.family, second.command.family)
            pair_counts[pair] += 1
            pair_sessions[pair].add(first.node.session_id)
            if (
                second.node.invocation.execution_form == "direct"
                and len(second.node.invocation.subcommands) == 1
                and second.command.confidence == "high"
                and second.node.invocation.output is not None
            ):
                pair_output_bytes[pair] += (
                    second.node.invocation.output.metrics.bytes
                )
            source_counts[first.command.family] += 1
            source_sessions[first.command.family].add(first.node.session_id)

    def row_for_pair(first: str, second: str) -> dict[str, Any]:
        count = pair_counts[(first, second)]
        denominator = source_counts[first]
        output_bytes = pair_output_bytes[(first, second)]
        return {
            "first": first,
            "second": second,
            "count": count,
            "conditional_follow_rate": (
                round(count / denominator, 6) if denominator else None
            ),
            "denominator": denominator,
            "distinct_sessions": len(pair_sessions[(first, second)]),
            "first_command_session_support": len(source_sessions[first]),
            "next_command_exclusive_output_bytes": output_bytes,
            "mean_next_command_output_bytes": (
                round(output_bytes / count, 1) if count else 0.0
            ),
        }

    rows = [
        row_for_pair(first, second)
        for (first, second), _ in sorted(
            pair_counts.items(), key=lambda item: (-item[1], item[0])
        )[:40]
    ]
    high_output_rows = [
        row_for_pair(first, second)
        for (first, second), output_bytes in sorted(
            pair_output_bytes.items(),
            key=lambda item: (-item[1], -pair_counts[item[0]], item[0]),
        )
        if output_bytes > 0 and pair_counts[(first, second)] <= 3
    ][:10]
    return {
        "rows": rows,
        "low_frequency_high_output_rows": high_output_rows,
        "warning": (
            "Conditional follow rates are observational and do not establish causality "
            "or batch safety."
        ),
    }


def _candidate_rows(
    family_rows: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = []
    for row in family_rows:
        category = row["candidate_category"]
        if category == "shape_only":
            continue
        rows.append(
            {
                "sequence": [
                    item["identity"] for item in row["sequence"]
                ],
                "category": category,
                "total_occurrences": row["total"],
                "explicit_batch": row["explicit_batch"],
                "separate_direct_calls": row["separate_direct_calls"],
                "cross_mode_repeat": row["cross_mode_repeat"],
                "same_response_inferred": row["same_response_inferred"],
                "failure_count": row["observed_status"]["failed"],
                "unknown_status_count": row["observed_status"]["unknown"],
                "intervening_events": row["intervening_events"],
                "unknown_reasons": row["unknown_reasons"],
                "shape_examples": row["shape_variants"][:3],
            }
        )
    category_order = {
        "plausible_static_sequence": 0,
        "mixed_evidence_requires_review": 1,
        "decision_dependent": 2,
        "unsafe_or_ambiguous": 3,
        "already_batched": 4,
    }
    rows.sort(
        key=lambda row: (
            category_order.get(row["category"], 9),
            -row["total_occurrences"],
            tuple(row["sequence"]),
        )
    )
    return rows[:30]
