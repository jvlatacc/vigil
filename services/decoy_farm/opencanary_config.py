"""Merge farm overrides into the OpenCanary config (build-time).

Dockerfile.decoy-opencanary runs, after ``opencanaryd --copyconfig``:

    python3 services/decoy_farm/opencanary_config.py /etc/opencanaryd/opencanary.conf

The generated file is upstream's default for the installed release; this
script never hard-codes the module list. It disables every
``<module>.enabled`` key except the farm's two protocols, then applies the
farm's settings. A module upstream adds later therefore degrades to
disabled — never to "enabled in the decoy plane unannounced". Exits non-zero
when the file cannot be merged, so the image build fails loudly instead of
shipping a broken decoy.

Settings applied (verified against opencanary 0.9.10's generated default):
- every module disabled except ``http`` and ``smb`` (upstream enables ftp by
  default — port 21 is privileged and would die under the farm's cap_drop)
- ``http.enabled`` true on port 8080 (unprivileged)
- ``smb.enabled`` true; ``smb.auditfile`` pointed at the shared volume
- ``device.node_id`` = decoy-opencanary
- the logger's file handler moved onto the shared volume (alerts feed the
  shipper); the console handler stays for ``docker logs``
"""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, List

KEEP_ENABLED = ("http", "smb")
NODE_ID = "decoy-opencanary"
AUDIT_FILE = "/decoy-logs/samba-audit.log"
ALERT_LOG = "/decoy-logs/opencanary.log"
HTTP_PORT = 8080


def apply(config: Dict[str, Any]) -> Dict[str, Any]:
    for key in list(config):
        if key.endswith(".enabled"):
            module = key.rsplit(".enabled", 1)[0]
            if module and module not in KEEP_ENABLED:
                config[key] = False

    config["http.enabled"] = True
    config["http.port"] = HTTP_PORT
    config["smb.enabled"] = True
    config["smb.auditfile"] = AUDIT_FILE
    config["device.node_id"] = NODE_ID

    # Upstream's logger section shape is release-dependent; replace it
    # wholesale with the known-good structure (verified 0.9.10): a PyLogger
    # whose file handler feeds the shared volume the shipper reads.
    config["logger"] = {
        "class": "PyLogger",
        "kwargs": {
            "formatters": {"plain": {"format": "%(message)s"}},
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stdout",
                },
                "file": {"class": "logging.FileHandler", "filename": ALERT_LOG},
            },
        },
    }
    return config


def main(argv: List[str]) -> int:
    if len(argv) != 2:
        print("usage: opencanary_config.py <opencanary.conf>", file=sys.stderr)
        return 2
    path = argv[1]
    try:
        with open(path, "r", encoding="utf-8") as fh:
            config = json.load(fh)
        if not isinstance(config, dict):
            raise ValueError("config is not a JSON object")
    except (OSError, ValueError) as exc:
        print(f"Cannot read generated OpenCanary config {path}: {exc}", file=sys.stderr)
        return 1
    apply(config)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(config, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(f"OpenCanary config merged: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
