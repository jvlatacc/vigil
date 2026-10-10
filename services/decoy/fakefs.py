"""A small in-memory virtual filesystem for the SSH decoy.

Plausibility layer, nothing more: enough of a tree that ``ls``, ``cd``,
``pwd`` and ``cat`` behave like a tired Ubuntu box. Every file it serves is
generated here — no real credential, hostname, or network detail is ever
planted, and credential-shaped artifacts (``/etc/passwd``, ``/etc/shadow``)
carry canary values only, marked per the containment invariant.

This module is intentionally synchronous and side-effect free: the SSH shell
threads read it read-only. Files "downloaded" during a session are tracked
in the session, never written here.
"""

from typing import Dict, List, Optional

from services.decoy.config import CANARY_MARKER, CANARY_USERNAMES

# A stable fake identity. A decoy that changes hostname between sessions
# looks like what it is; one boring name reads as one boring box.
DEFAULT_HOSTNAME = "app-01"
KERNEL = "Linux app-01 5.15.0-91-generic #101-Ubuntu SMP x86_64 GNU/Linux"

# Canary password hash placeholder for the planted shadow file. It is a
# string, never a real hash of anything an attacker can brute-force offline
# into a working production credential — and it is marked.
CANARY_SHADOW_HASH = f"$6${CANARY_MARKER}$placeholder-no-real-hash"

_FAKE_PASSWD_LINES = [
    "root:x:0:0:root:/root:/bin/bash",
    "daemon:x:1:1:daemon:/usr/sbin:/usr/sbin/nologin",
    "ubuntu:x:1000:1000:Ubuntu:/home/ubuntu:/bin/bash",
    "deploy:x:1001:1001:Deployment account (canary):/home/deploy:/bin/bash",
    "service:x:1002:1002:Service account (canary):/home/service:/usr/sbin/nologin",
]

_FAKE_LS_ROOT = [
    "bin   etc   lib    media  proc  srv  vagrant",
    "boot  home  lib64  mnt    root  sys  var",
    "dev   initrd.tmp  opt    run    tmp",
]

_FAKE_MOTD = (
    "Welcome to Ubuntu 22.04.3 LTS (GNU/Linux 5.15.0-91-generic x86_64)\n"
    " * Documentation:  https://help.ubuntu.com\n"
)


class FakeFilesystem:
    """Directories, files, and canned command output for one decoy host."""

    def __init__(self, hostname: str = DEFAULT_HOSTNAME):
        self.hostname = hostname
        self._files: Dict[str, str] = {
            "/etc/passwd": "\n".join(_FAKE_PASSWD_LINES) + "\n",
            "/etc/shadow": "\n".join(
                f"{user}:{CANARY_SHADOW_HASH}:19600:0:99999:7:::"
                for user in CANARY_USERNAMES
            )
            + "\n",
            "/etc/hostname": self.hostname + "\n",
            "/etc/os-release": (
                'PRETTY_NAME="Ubuntu 22.04.3 LTS"\nNAME="Ubuntu"\nID=ubuntu\n'
            ),
            "/etc/motd": _FAKE_MOTD,
            "/home/ubuntu/.bash_history": "# canary host — nothing real here\n",
            "/home/deploy/.bash_history": "# canary host — nothing real here\n",
            "/root/.bash_history": "# canary host — nothing real here\n",
        }
        # Directory listing table: path -> sorted listing (kept simple; the
        # tree only needs to be wide enough that `ls` feels honest).
        self._dirs: Dict[str, List[str]] = {
            "/": _FAKE_LS_ROOT,
            "/etc": sorted(
                ["passwd", "shadow", "hostname", "os-release", "motd", "ssh"]
            ),
            "/home": sorted(CANARY_USERNAMES[:1] + ("deploy",)),
            "/home/ubuntu": [".bash_history", ".ssh"],
            "/home/deploy": [".bash_history", "app"],
            "/root": [".bash_history"],
            "/var/log": ["syslog", "auth.log", "kern.log"],
            "/tmp": [],
        }

    def canon(self, cwd: str, path: str) -> str:
        """Resolve a path the way a shell would (no traversal games — the
        fake tree is flat enough that this is presentation, not security)."""
        if not path:
            return cwd
        if path == "~":
            path = "/root"
        if not path.startswith("/"):
            path = f"{cwd.rstrip('/')}/{path}"
        parts: List[str] = []
        for part in path.split("/"):
            if part in ("", "."):
                continue
            if part == "..":
                parts = parts[:-1]
                continue
            parts.append(part)
        return "/" + "/".join(parts)

    def list_dir(self, path: str) -> Optional[str]:
        if path in self._dirs:
            entries = self._dirs[path]
            return "\n".join(entries) if entries else ""
        if path in self._files:
            return path
        return None

    def read_file(self, path: str) -> Optional[str]:
        return self._files.get(path)

    def exists(self, path: str) -> bool:
        return path in self._files or path in self._dirs

    # --- canned command output -------------------------------------------

    def motd(self) -> str:
        return _FAKE_MOTD

    def uname(self) -> str:
        return KERNEL

    def ps(self) -> str:
        return (
            "  PID TTY          TIME CMD\n"
            "    1 ?        00:00:02 systemd\n"
            "  431 ?        00:00:00 sshd\n"
            "  512 ?        00:00:01 python3\n"
            "  919 pts/0    00:00:00 bash\n"
        )

    def ip_addr(self) -> str:
        # One boring RFC1918 address; nothing about the real deployment.
        return (
            "1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536\n"
            "    inet 127.0.0.1/8 scope host lo\n"
            "2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500\n"
            "    inet 10.0.2.15/24 brd 10.0.2.255 scope global eth0\n"
        )

    def passwd_view(self) -> str:
        return self._files["/etc/passwd"]
