"""Tail decoy logs on the shared volume; post findings to Vigil's ingest webhook.

The last leg of the decoy plane: decoys write JSON-lines events to the
``decoy_logs`` volume (read-only to this process), and this shipper turns each
line into a Vigil finding payload (telemetry.py) and POSTs it — with the
webhook bearer token — to the daemon's generic ingest endpoint. Accepted
payloads become ordinary findings: triage, enrichment and, if warranted, a
higher-confidence response run on them exactly as they do for any other
source (spec AC10).

Delivery is at-least-once against webhook outages: unposted lines stay
pending and retry with backoff, and finding ids are content-addressed so
reposts dedupe. A crash between read and POST can lose one poll's events —
decoy telemetry is best-effort intelligence, never production data.

Environment (all optional except the webhook URL):
- DECOY_FARM_WEBHOOK_URL   e.g. http://soc-daemon:8081/ingest (required)
- DECOY_FARM_WEBHOOK_TOKEN the daemon's DAEMON_WEBHOOK_TOKEN value
- DECOY_FARM_SOURCES       "kind:path" pairs, comma-separated
- DECOY_FARM_POLL_INTERVAL seconds between polls (default 5)
- DECOY_FARM_FARM_ID       stable farm identity in every payload
"""

from __future__ import annotations

import json
import logging
import os
import signal
import time
from datetime import datetime, timezone
from http.client import HTTPConnection, HTTPSConnection
from typing import IO, Any, Dict, List, Mapping, Optional, Tuple
from urllib.parse import urlsplit

from services.decoy_farm.telemetry import build_finding

logger = logging.getLogger(__name__)

DEFAULT_SOURCES = (
    "cowrie:/cowrie-logs/cowrie.json,"
    "opencanary:/decoy-logs/opencanary.log,"
    "http-decoy:/decoy-logs/http-decoy.jsonl"
)
DEFAULT_POLL_INTERVAL = 5.0
DEFAULT_FARM_ID = "decoy-farm"
BATCH_LIMIT = 100
_BACKOFF_CAP = 60.0
_KNOWN_KINDS = ("cowrie", "opencanary", "http-decoy")


def parse_sources(raw: str) -> List[Tuple[str, str]]:
    """Parse ``cowrie:/a.json,opencanary:/b.log`` into ordered (kind, path) pairs.

    Fails loudly at startup: a typo in the source list must stop the shipper,
    not silently stop shipping one decoy's telemetry.
    """
    sources: List[Tuple[str, str]] = []
    for chunk in (raw or "").split(","):
        entry = chunk.strip()
        if not entry:
            continue
        kind, sep, path = entry.partition(":")
        kind = kind.strip()
        path = path.strip()
        if sep == "" or kind not in _KNOWN_KINDS or not path:
            raise SystemExit(f"Unparseable DECOY_FARM_SOURCES entry: {entry!r}")
        sources.append((kind, path))
    if not sources:
        raise SystemExit("DECOY_FARM_SOURCES is empty — nothing to tail")
    return sources


class ShipperConfig:
    def __init__(
        self,
        webhook_url: str,
        webhook_token: str,
        poll_interval: float,
        sources: List[Tuple[str, str]],
        farm_id: str,
    ) -> None:
        self.webhook_url = webhook_url
        self.webhook_token = webhook_token
        self.poll_interval = poll_interval
        self.sources = sources
        self.farm_id = farm_id

    @classmethod
    def from_env(cls, env: Optional[Dict[str, str]] = None) -> "ShipperConfig":
        # os.environ satisfies Mapping[str, str] as does the injected dict.
        settings: Mapping[str, str] = os.environ if env is None else env
        url = (settings.get("DECOY_FARM_WEBHOOK_URL") or "").strip()
        if not url:
            raise SystemExit(
                "DECOY_FARM_WEBHOOK_URL is not set — nothing to ship to "
                "(compose default: http://soc-daemon:8081/ingest)"
            )
        interval_raw = (settings.get("DECOY_FARM_POLL_INTERVAL") or "").strip()
        try:
            interval = float(interval_raw) if interval_raw else DEFAULT_POLL_INTERVAL
        except ValueError:
            raise SystemExit(f"Unparseable DECOY_FARM_POLL_INTERVAL: {interval_raw!r}")
        return cls(
            webhook_url=url,
            webhook_token=settings.get("DECOY_FARM_WEBHOOK_TOKEN", ""),
            poll_interval=max(1.0, interval),
            sources=parse_sources(
                settings.get("DECOY_FARM_SOURCES") or DEFAULT_SOURCES
            ),
            farm_id=settings.get("DECOY_FARM_FARM_ID") or DEFAULT_FARM_ID,
        )


class _TailedFile:
    """Follow one JSON-lines file across appends, truncation and rotation.

    History is skipped on first open: replaying old sessions after a container
    restart would only re-exercise Vigil's dedup, not add intelligence. After
    a rotation or truncation the new file is read from its start — it only
    exists because a writer replaced it, so none of it is history.
    """

    def __init__(self, path: str) -> None:
        self.path = path
        self._fh: Optional[IO[str]] = None
        self._ino: Optional[int] = None
        self._ever_opened = False

    def poll(self, max_lines: int) -> List[str]:
        lines: List[str] = []
        if self._fh is not None and self._anomalous():
            lines.extend(self._drain(max_lines - len(lines)))
            self._close()
        if self._fh is None and not self._open():
            return lines
        assert self._fh is not None
        lines.extend(self._drain(max_lines - len(lines)))
        return lines

    def _close(self) -> None:
        if self._fh is not None:
            try:
                self._fh.close()
            except OSError:
                pass
            self._fh = None
            self._ino = None

    def _open(self) -> bool:
        try:
            fh = open(self.path, "r", encoding="utf-8", errors="replace")
            self._ino = os.fstat(fh.fileno()).st_ino
            if self._ever_opened:
                fh.seek(0)  # reopened after rotation/truncation: read all
            else:
                fh.seek(0, os.SEEK_END)  # first open: skip history
            self._ever_opened = True
            self._fh = fh
            return True
        except FileNotFoundError:
            return False  # decoys start at their own pace; wait for the file
        except OSError as exc:
            logger.warning("Cannot read decoy log %s: %s", self.path, exc)
            return False

    def _anomalous(self) -> bool:
        """True when the open file was rotated away or truncated underneath us."""
        assert self._fh is not None
        try:
            stat = os.stat(self.path)
        except FileNotFoundError:
            return True
        if self._ino is not None and stat.st_ino != self._ino:
            return True
        return os.fstat(self._fh.fileno()).st_size < self._fh.tell()

    def _drain(self, max_lines: int) -> List[str]:
        lines: List[str] = []
        assert self._fh is not None
        while len(lines) < max_lines:
            position = self._fh.tell()
            raw = self._fh.readline()
            if raw and not raw.endswith("\n"):
                self._fh.seek(position)  # partial line: leave it for the next poll
                break
            if not raw:
                break
            lines.append(raw)
        return lines


def post_batch(
    url: str, token: str, payload: List[Dict[str, Any]], timeout: float = 10.0
) -> Tuple[bool, int]:
    """POST one JSON batch to the ingest webhook.

    Returns (accepted, status). Connection failures raise OSError — the
    caller keeps the batch and retries; a 4xx is a contract error that will
    not heal, so the caller drops that batch loudly.
    """
    parts = urlsplit(url)
    secure = parts.scheme == "https"
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError(f"Unsupported webhook URL: {url!r}")
    conn_cls = HTTPSConnection if secure else HTTPConnection
    conn = conn_cls(
        parts.hostname, parts.port or (443 if secure else 80), timeout=timeout
    )
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    try:
        conn.request(
            "POST", parts.path or "/ingest", body=json.dumps(payload), headers=headers
        )
        response = conn.getresponse()
        status = response.status
        response.read()
    finally:
        conn.close()
    return 200 <= status < 300, status


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _install_sigterm() -> None:
    def _stop(signum: int, frame: Any) -> None:
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _stop)


def run(cfg: ShipperConfig) -> None:
    tails = [(kind, _TailedFile(path)) for kind, path in cfg.sources]
    pending: Dict[str, List[Dict[str, Any]]] = {path: [] for _kind, path in cfg.sources}
    counts = {"shipped": 0, "dropped": 0, "malformed": 0, "failed_posts": 0}
    backoff = 1.0
    last_summary = time.monotonic()

    logger.info(
        "Shipping decoy telemetry to %s (poll every %.0fs)",
        cfg.webhook_url,
        cfg.poll_interval,
    )

    while True:
        for kind, tail in tails:
            raw_lines = tail.poll(BATCH_LIMIT)
            if not raw_lines:
                continue
            built = 0
            for raw in raw_lines:
                finding = build_finding(
                    kind, raw, farm_id=cfg.farm_id, fallback_ts=_utc_now_iso()
                )
                if finding is None:
                    counts["malformed"] += 1
                    logger.warning(
                        "Skipping unparseable decoy line in %s: %.200r", tail.path, raw
                    )
                    continue
                pending[tail.path].append(finding)
                built += 1
            if built:
                logger.debug("Parsed %d %s events from %s", built, kind, tail.path)

        had_failure = False
        for _kind, tail in tails:
            queue = pending[tail.path]
            while queue:
                chunk = queue[:BATCH_LIMIT]
                try:
                    accepted, status = post_batch(
                        cfg.webhook_url, cfg.webhook_token, chunk
                    )
                except OSError as exc:
                    counts["failed_posts"] += 1
                    had_failure = True
                    logger.warning(
                        "Webhook unreachable (%s); %d findings queued for retry",
                        exc,
                        len(queue),
                    )
                    accepted = False
                    # Status never arrived (no connection). 0 is neither a 2xx
                    # nor a 4xx, so the branch below correctly retries.
                    status = 0
                if accepted:
                    del queue[: len(chunk)]
                    counts["shipped"] += len(chunk)
                    continue
                if 400 <= status < 500:
                    counts["dropped"] += len(queue)
                    logger.error(
                        "Webhook rejected decoy findings (HTTP %d) — dropping %d; "
                        "a 4xx contract error cannot heal",
                        status,
                        len(queue),
                    )
                    queue.clear()
                break  # 5xx or unreachable: retry next cycle with backoff

        if time.monotonic() - last_summary >= 60.0:
            logger.info(
                "Decoy telemetry: shipped=%(shipped)d dropped=%(dropped)d "
                "malformed=%(malformed)d failed_posts=%(failed_posts)d",
                counts,
            )
            last_summary = time.monotonic()

        if had_failure:
            backoff = min(backoff * 2, _BACKOFF_CAP)
            time.sleep(backoff)
        else:
            backoff = 1.0
            time.sleep(cfg.poll_interval)


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("DECOY_FARM_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    cfg = ShipperConfig.from_env()
    _install_sigterm()
    try:
        run(cfg)
    except SystemExit:
        raise
    except Exception:
        logger.exception("Decoy telemetry shipper crashed")
        raise


if __name__ == "__main__":
    main()
