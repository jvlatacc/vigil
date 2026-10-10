"""Observation-tail suite: EVE normalization, direction inference, cold start
(no backfill), restart resume from the persisted offset, rotation, and
malformed-line tolerance. The async pump test runs under ``asyncio.run`` —
the edge package carries no pytest-asyncio dependency."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from ipaddress import ip_network
from pathlib import Path

import pytest

from services.edge.observations.base import Observation
from services.edge.observations.file_tail import (
    FileTail,
    infer_direction,
    parse_eve_line,
)

HOME_CIDRS = ("10.42.0.0/16",)  # FileTail takes CIDR strings
HOME_NETS = (ip_network("10.42.0.0/16"),)  # pure functions take network objects


def eve_line(**overrides: object) -> str:
    record: dict[str, object] = {
        "timestamp": "2026-10-09T12:00:00.000000+0000",
        "event_type": "flow",
        "src_ip": "10.42.7.7",
        "dest_ip": "203.0.113.55",
        "proto": "tcp",
    }
    record.update(overrides)
    return json.dumps(record)


def test_flow_line_normalizes() -> None:
    line = eve_line()
    observation = parse_eve_line(line, raw_ref="eve.json:0", home_cidrs=HOME_NETS)
    assert observation is not None
    assert observation.direction == "egress"
    assert observation.src_ip == "10.42.7.7"
    assert observation.dest_ip == "203.0.113.55"
    assert observation.event_type == "flow"
    assert observation.proto == "tcp"
    assert observation.raw_ref == "eve.json:0"
    assert observation.raw_digest == hashlib.sha256(line.encode()).hexdigest()
    assert observation.timestamp == datetime(2026, 10, 9, 12, 0, 0, tzinfo=UTC)


def test_naive_timestamp_gets_utc() -> None:
    observation = parse_eve_line(eve_line(timestamp="2026-10-09T12:00:00"), raw_ref="r")
    assert observation is not None
    assert observation.timestamp.tzinfo is UTC


def test_domain_candidates() -> None:
    dns = parse_eve_line(
        eve_line(event_type="dns", dns={"rrname": "c2.example.com."}), raw_ref="r"
    )
    assert dns is not None
    assert dns.dest_domain == "c2.example.com"
    http = parse_eve_line(
        eve_line(event_type="http", http={"hostname": "phish.example.com"}),
        raw_ref="r",
    )
    assert http is not None
    assert http.dest_domain == "phish.example.com"
    tls = parse_eve_line(
        eve_line(event_type="tls", tls={"sni": "evil.example.com"}), raw_ref="r"
    )
    assert tls is not None
    assert tls.dest_domain == "evil.example.com"


@pytest.mark.parametrize(
    ("src", "dest", "expected"),
    [
        ("10.42.7.7", "203.0.113.55", "egress"),
        ("203.0.113.55", "10.42.7.7", "ingress"),
        ("10.42.7.7", "10.42.7.9", "unknown"),  # internal to internal
        ("8.8.8.8", "198.51.100.1", "unknown"),  # neither side home
    ],
)
def test_direction(src: str, dest: str, expected: str) -> None:
    assert infer_direction(src, dest, HOME_NETS) == expected


def test_direction_without_home_cidrs_is_unknown() -> None:
    """No segment definition — the direction stays honest instead of guessed."""
    assert infer_direction("10.42.7.7", "203.0.113.55", ()) == "unknown"


@pytest.mark.parametrize(
    "line",
    [
        "not json",
        "[1, 2]",
        json.dumps({"event_type": "flow"}),  # no timestamp
        json.dumps({"timestamp": "2026-10-09T12:00:00+00:00"}),  # no event_type
        json.dumps({"timestamp": "gibberish", "event_type": "flow"}),
    ],
)
def test_malformed_lines_return_none(line: str) -> None:
    assert parse_eve_line(line, raw_ref="r") is None


def test_cold_start_does_not_backfill(tmp_path: Path) -> None:
    path = tmp_path / "eve.json"
    path.write_text(eve_line() + "\n" + eve_line(dest_ip="198.51.100.9") + "\n")
    tail = FileTail(path, home_cidrs=HOME_CIDRS)
    assert tail.poll_once() == []


def test_new_lines_are_observed_in_order(tmp_path: Path) -> None:
    path = tmp_path / "eve.json"
    path.write_text("")
    tail = FileTail(path, home_cidrs=HOME_CIDRS)
    assert tail.poll_once() == []  # cold start at EOF — new lines only
    with path.open("a") as handle:
        handle.write(eve_line() + "\n")
        handle.write(eve_line(dest_ip="198.51.100.9") + "\n")
    observed = tail.poll_once()
    assert [o.dest_ip for o in observed] == ["203.0.113.55", "198.51.100.9"]
    assert tail.poll_once() == []


def test_partial_line_buffered_until_complete(tmp_path: Path) -> None:
    path = tmp_path / "eve.json"
    path.write_text("")
    tail = FileTail(path, home_cidrs=HOME_CIDRS)
    assert tail.poll_once() == []  # cold start at EOF
    full = eve_line()
    completed = '{"timestamp": "2026-10-09T12:00:00+00:00", "event_type": "flow"}'
    with path.open("a") as handle:
        handle.write("not json\n")
        handle.write(full + "\n")
        handle.write(completed[:20])  # torn write, no newline
    assert len(tail.poll_once()) == 1
    with path.open("a") as handle:
        handle.write(completed[20:] + "\n")
    observed = tail.poll_once()
    assert len(observed) == 1
    assert observed[0].raw_digest == hashlib.sha256(completed.encode()).hexdigest()


def test_malformed_lines_counted_not_fatal(tmp_path: Path) -> None:
    path = tmp_path / "eve.json"
    path.write_text("")
    tail = FileTail(path, home_cidrs=HOME_CIDRS)
    assert tail.poll_once() == []  # cold start at EOF
    with path.open("a") as handle:
        handle.write("not json\n")
        handle.write(eve_line() + "\n")
        handle.write("[1, 2]\n")
        handle.write(json.dumps({"event_type": "flow"}) + "\n")  # no timestamp
    observed = tail.poll_once()
    assert len(observed) == 1
    assert tail.malformed_lines == 3


def test_missing_file_is_quiet(tmp_path: Path) -> None:
    tail = FileTail(tmp_path / "eve.json", home_cidrs=HOME_CIDRS)
    assert tail.poll_once() == []


def test_resume_from_persisted_offset(tmp_path: Path) -> None:
    path = tmp_path / "eve.json"
    path.write_text("")
    state_dir = tmp_path / "state"
    first = FileTail(path, home_cidrs=HOME_CIDRS, state_dir=state_dir)
    assert first.poll_once() == []
    with path.open("a") as handle:
        handle.write(eve_line() + "\n")
    assert len(first.poll_once()) == 1
    resumed = FileTail(path, home_cidrs=HOME_CIDRS, state_dir=state_dir)  # restart
    with path.open("a") as handle:
        handle.write(eve_line(dest_ip="198.51.100.9") + "\n")
    observed = resumed.poll_once()
    assert len(observed) == 1, "a restart resumes at the saved offset"
    assert observed[0].dest_ip == "198.51.100.9"


def test_restart_without_state_does_not_replay(tmp_path: Path) -> None:
    path = tmp_path / "eve.json"
    with path.open("a") as handle:
        handle.write(eve_line() + "\n")
    tail = FileTail(path, home_cidrs=HOME_CIDRS)  # no state_dir: cold start at EOF
    assert tail.poll_once() == []


def test_rotation_follows_new_file_even_when_larger(tmp_path: Path) -> None:
    path = tmp_path / "eve.json"
    path.write_text(eve_line() + "\n")
    tail = FileTail(path, home_cidrs=HOME_CIDRS)
    assert tail.poll_once() == []  # cold start at EOF
    # logrotate rename+recreate: new inode, LARGER than the old EOF offset —
    # the tail must read the new file from byte 0.
    path.unlink()
    path.write_text(eve_line(dest_ip="198.51.100.9", padding="y" * 2000) + "\n")
    observed = tail.poll_once()
    assert len(observed) == 1
    assert observed[0].dest_ip == "198.51.100.9"


def test_run_pumps_to_handler(tmp_path: Path) -> None:
    async def scenario() -> None:
        path = tmp_path / "eve.json"
        path.write_text("")
        tail = FileTail(path, poll_seconds=0.01, home_cidrs=HOME_CIDRS)
        received: list[Observation] = []

        async def handler(observation: Observation) -> None:
            received.append(observation)

        task = asyncio.create_task(tail.run(handler))
        try:
            await asyncio.sleep(0.05)  # let the first cold-start poll pass
            with path.open("a") as handle:
                handle.write(eve_line() + "\n")
            for _ in range(200):
                if received:
                    break
                await asyncio.sleep(0.01)
            assert len(received) == 1
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    asyncio.run(scenario())
