"""Minimal high-interaction SSH decoy.

A paramiko server that looks like a locked-down Ubuntu box: password auth
where the canary credential always succeeds, and an interactive shell with a
plausible fake filesystem. Attacker commands are captured in the session and
never executed; errors log and continue — a session ends only when the
attacker closes it.

The daemon handoff rides the shared emitter. The SSH server is thread-based
(paramiko), so a finished session schedules its emit on the process's
asyncio loop with ``run_coroutine_threadsafe``.
"""

import asyncio
import hashlib
import logging
import socket
import threading
from typing import Dict, List, Optional, Tuple

import paramiko

from services.decoy.canary import CanaryCredentials
from services.decoy.config import SSH_PORT, DecoyConfig
from services.decoy.emitter import SessionEventEmitter
from services.decoy.fakefs import FakeFilesystem
from services.decoy.session import (
    CREDENTIAL_CANARY,
    CREDENTIAL_REJECTED,
    DecoySession,
    DroppedFile,
)

logger = logging.getLogger(__name__)

DECOY_SERVICE_NAME = "ssh-decoy"

# A plausible banner instead of "SSH-2.0-paramiko_5.0.0" — a paramiko banner
# is the classic honeypot tell. The marker documents that the string is
# presentation, not a real server identity.
_PLAUSIBLE_SSH_BANNER = (
    "SSH-2.0-OpenSSH_9.2p1 Ubuntu-2ubuntu3.6"  # nosec — decoy plausibility
)

# Simulated downloads are stored as marked placeholder content; the SHA-256
# in the capture is honest about the bytes the decoy actually "served".
_SIMULATED_CONTENT_MARKER = "canary: simulated download"


def _simulate_download(session: DecoySession, url: str, now: str) -> str:
    """Pretend to fetch a URL: plausible wget-style output, with a canary-
    marked placeholder file recorded in the session."""
    name = url.rsplit("/", 1)[-1].split("?")[0] or "download"
    content = f"#!/bin/sh\n# {_SIMULATED_CONTENT_MARKER}: {url}\nexit 0\n"
    session.record_file(
        DroppedFile(
            name=name,
            sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            source="simulated-download",
        )
    )
    return (
        f"--{now}--  {url}\n"
        "Resolving host... connected.\n"
        "HTTP request sent, awaiting response... 200 OK\n"
        "Length: unspecified [text/x-shellscript]\n\n"
        f"{name}                                   0  --.-KB/s   in 0s\n\n"
        f"'{name}' saved\n"
    )


def execute_command(
    fs: FakeFilesystem,
    session: DecoySession,
    cwd: str,
    command: str,
    now: str = "",
) -> Tuple[str, str]:
    """Run one attacker command against the fake filesystem.

    Pure w.r.t. the filesystem: returns ``(output, new_cwd)``. The only
    side effect is recording a simulated download on the session — the
    capture sink, not the system. Unknown commands fail like bash would.
    """
    command = command.strip()
    if not command:
        return "", cwd
    # sudo passes straight through — on this box you are already root.
    if command.startswith("sudo "):
        command = command[5:].strip() or "sudo"
    parts = command.split()
    head = parts[0]

    if head in ("exit", "logout"):
        return "logout", cwd
    if head == "whoami":
        return "root", cwd
    if head == "id":
        return "uid=0(root) gid=0(root) groups=0(root)", cwd
    if head == "hostname":
        return fs.hostname, cwd
    if head == "uname":
        return fs.uname(), cwd
    if head == "pwd":
        return cwd, cwd
    if head in ("ls", "dir"):
        target = fs.canon(cwd, parts[1]) if len(parts) > 1 else cwd
        listing = fs.list_dir(target)
        if listing is None:
            return f"ls: cannot access '{target}': No such file or directory", cwd
        return listing, cwd
    if head == "cd":
        target = fs.canon(cwd, parts[1]) if len(parts) > 1 else "/root"
        if not fs.exists(target):
            return f"cd: {target}: No such file or directory", cwd
        return "", target
    if head == "cat":
        if len(parts) < 2:
            return "cat: missing operand", cwd
        content = fs.read_file(fs.canon(cwd, parts[1]))
        if content is None:
            return f"cat: {parts[1]}: No such file or directory", cwd
        return content.rstrip("\n"), cwd
    if head == "ps":
        return fs.ps(), cwd
    if head in ("ip", "ifconfig"):
        return fs.ip_addr(), cwd
    if head == "netstat":
        return (
            "Active Internet connections (w/o servers)\n"
            "Proto Recv-Q Send-Q Local Address           Foreign Address         State\n"
            "tcp        0      0 10.0.2.15:22            0.0.0.0:*               LISTEN\n"
        ), cwd
    if head in ("wget", "curl"):
        if len(parts) < 2:
            return f"{head}: missing URL", cwd
        return _simulate_download(session, parts[1], now), cwd
    if head == "echo":
        return " ".join(parts[1:]), cwd
    if head == "passwd":
        return "passwd: password updated successfully", cwd
    if head == "clear":
        return "", cwd
    return f"bash: {head}: command not found", cwd


class _DecoyServerInterface(paramiko.ServerInterface):
    """Auth gate for one connection. The canary credential always succeeds;
    every attempt — success or failure — lands on the session."""

    def __init__(self, canary: CanaryCredentials, session: DecoySession):
        self._canary = canary
        self._session = session

    def get_allowed_auths(self, username: str) -> str:
        return "password"

    def check_auth_password(self, username: str, password: str) -> int:
        # paramiko 5.0 calls this with (username, password) — no submethods.
        success = self._canary.matches(password)
        self._session.record_auth(
            user=username or "(none)",
            success=success,
            credential=CREDENTIAL_CANARY if success else CREDENTIAL_REJECTED,
        )
        if success:
            logger.info(
                "Decoy SSH canary login for %s as %s",
                self._session.attacker_ip,
                username,
            )
            return paramiko.AUTH_SUCCESSFUL
        return paramiko.AUTH_FAILED

    def check_channel_request(self, kind: str, chan) -> int:
        if kind == "session":
            return paramiko.OPEN_SUCCEEDED
        return paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_channel_shell_request(self, channel) -> bool:
        return True

    def check_channel_pty_request(
        self, channel, term, width, height, pixelwidth, pixelheight, modes
    ) -> bool:
        return True


class _DecoyShell:
    """Drives one interactive channel. Errors log and continue — the loop
    ends only when the channel itself closes."""

    def __init__(self, channel, session: DecoySession, fs: FakeFilesystem):
        self.channel = channel
        self.session = session
        self.fs = fs
        self.cwd = "/root"

    @property
    def prompt(self) -> str:
        return f"root@{self.fs.hostname}:{self.cwd}# "

    def run(self) -> None:
        """Read command lines until the channel closes. One bad read never
        kills the session; capture is the point."""
        buffer = b""
        try:
            self.channel.sendall(self.fs.motd())
            self.channel.sendall(self.prompt.encode("utf-8"))
            while True:
                data = self.channel.recv(4096)
                if not data:
                    break
                buffer += data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
                while b"\n" in buffer:
                    raw, buffer = buffer.split(b"\n", 1)
                    command = raw.decode("utf-8", "replace").strip()
                    # Server-side echo, like a real PTY.
                    self.channel.sendall(raw + b"\n")
                    if command:
                        self.session.record_command(command)
                        output, self.cwd = execute_command(
                            self.fs, self.session, self.cwd, command
                        )
                        if output:
                            self.channel.sendall((output + "\n").encode("utf-8"))
                        if command in ("exit", "logout"):
                            return
                    self.channel.sendall(self.prompt.encode("utf-8"))
        except (paramiko.SSHException, OSError, EOFError) as exc:
            logger.info(
                "Decoy SSH channel for %s closed with %s (session preserved)",
                self.session.attacker_ip,
                type(exc).__name__,
            )
        except Exception:
            logger.exception("Unexpected decoy SSH shell error — continuing")
        finally:
            try:
                self.channel.close()
            except Exception:  # noqa: BLE001 — channel may already be gone
                pass


class SshDecoy:
    """The SSH decoy server. Binds once; one thread per connection; finished
    sessions are handed to the process's asyncio loop for emission."""

    def __init__(
        self,
        config: DecoyConfig,
        canary: CanaryCredentials,
        emitter: SessionEventEmitter,
        host: str = "0.0.0.0",  # nosec B104 — container-scoped by the decoy network
        port: int = SSH_PORT,
    ):
        self.config = config
        self.canary = canary
        self.emitter = emitter
        self.host = host
        self.port = port
        self.fs = FakeFilesystem()
        self._server_socket: Optional[socket.socket] = None
        self._host_key: Optional[paramiko.RSAKey] = None
        self._sessions: Dict[str, DecoySession] = {}
        self._accept_thread: Optional[threading.Thread] = None
        self._conn_threads: List[threading.Thread] = []
        self._stopped = threading.Event()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    # --- lifecycle ----------------------------------------------------------

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        """Load the host key and bind the listener. Raises on failure — a
        decoy that cannot bind is down, and the container must say so."""
        self._loop = loop
        self._host_key = paramiko.RSAKey.generate(2048)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.host, self.port))
        sock.listen(16)
        sock.settimeout(1.0)
        self._server_socket = sock

    def start(self) -> None:
        self._accept_thread = threading.Thread(
            target=self._accept_loop, name="ssh-decoy-accept", daemon=True
        )
        self._accept_thread.start()
        logger.info("SSH decoy listening on %s:%d", self.host, self.port)

    def stop(self) -> None:
        self._stopped.set()
        if self._server_socket is not None:
            try:
                self._server_socket.close()
            except OSError:
                pass
        for thread in self._conn_threads:
            thread.join(timeout=5)

    def _accept_loop(self) -> None:
        while not self._stopped.is_set():
            try:
                sock, addr = self._server_socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break  # socket closed during shutdown
            thread = threading.Thread(
                target=self._handle_connection, args=(sock, addr), daemon=True
            )
            thread.start()
            self._conn_threads.append(thread)

    # --- sessions -----------------------------------------------------------

    def _session_for(self, attacker_ip: str) -> DecoySession:
        session = self._sessions.get(attacker_ip)
        if session is None:
            session = DecoySession(
                decoy_service=DECOY_SERVICE_NAME,
                attacker_ip=attacker_ip,
                ttl_seconds=self.config.session_ttl_seconds,
            )
            self._sessions[attacker_ip] = session
            logger.info("Decoy SSH session opened for %s", attacker_ip)
        return session

    async def _emit_and_drop(self, session: DecoySession) -> None:
        payload = session.build_payload()
        ok = await self.emitter.emit(payload)
        logger.info(
            "Decoy SSH session for %s closed (%s) — %d commands, %d auth attempts",
            session.attacker_ip,
            "emitted" if ok else "NOT emitted",
            len(payload["commands"]),
            len(payload["auth_attempts"]),
        )

    async def flush_all(self) -> None:
        """Emit every still-open session (shutdown path)."""
        while self._sessions:
            _, session = self._sessions.popitem()
            await self._emit_and_drop(session)

    # --- per-connection -------------------------------------------------------

    def _handle_connection(self, sock: socket.socket, addr) -> None:
        attacker_ip = addr[0] if addr else "unknown"
        session = self._session_for(attacker_ip)
        transport: Optional[paramiko.Transport] = None
        try:
            transport = paramiko.Transport(sock)
            transport.local_version = _PLAUSIBLE_SSH_BANNER
            transport.add_server_key(self._host_key)
            transport.start_server(server=_DecoyServerInterface(self.canary, session))
            channel = transport.accept(timeout=60)
            if channel is None:
                logger.info("Decoy SSH: no channel from %s within 60s", attacker_ip)
                return
            _DecoyShell(channel=channel, session=session, fs=self.fs).run()
        except (paramiko.SSHException, OSError, EOFError) as exc:
            logger.info(
                "Decoy SSH transport error for %s (continuing): %s",
                attacker_ip,
                type(exc).__name__,
            )
        except Exception:
            logger.exception(
                "Unexpected decoy SSH error for %s — continuing", attacker_ip
            )
        finally:
            self._schedule_emit(session)
            if transport is not None:
                try:
                    transport.close()
                except Exception:  # noqa: BLE001 — transport may already be gone
                    pass
            try:
                sock.close()
            except OSError:
                pass

    def _schedule_emit(self, session: DecoySession) -> None:
        """Thread-safe handoff of a finished session to the emitter loop."""
        loop = self._loop
        if loop is None or loop.is_closed():
            logger.warning(
                "No emitter loop — decoy session for %s captured in logs only",
                session.attacker_ip,
            )
            return
        asyncio.run_coroutine_threadsafe(self._emit_and_drop(session), loop)


def main() -> None:
    """Container entrypoint (``python -m services.decoy.ssh_decoy``)."""
    import signal

    from core.telemetry import configure_logging
    from services.decoy.canary import resolve_canary

    configure_logging()
    config = DecoyConfig.from_settings()
    if not config.enabled:
        # The container was started without its master switch: an honest no-op,
        # not a half-serving decoy.
        logger.info("Decoy disabled (DECOY_ENABLED is not true); exiting")
        return

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    shutdown_event = asyncio.Event()
    decoy = SshDecoy(
        config=config,
        canary=resolve_canary(),
        emitter=SessionEventEmitter(
            config.ingest_url, timeout_seconds=config.emit_timeout_seconds
        ),
    )

    def request_shutdown() -> None:
        shutdown_event.set()
        decoy.stop()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, request_shutdown)
        except NotImplementedError:  # pragma: no cover — non-POSIX
            pass

    try:
        decoy.bind(loop)
        decoy.start()
        loop.run_until_complete(shutdown_event.wait())
        loop.run_until_complete(decoy.flush_all())
    finally:
        decoy.stop()
        loop.close()
        logger.info("SSH decoy stopped")


if __name__ == "__main__":
    main()
