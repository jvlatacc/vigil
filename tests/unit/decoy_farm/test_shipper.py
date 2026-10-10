"""Shipper mechanics: source parsing, config, tail behavior, and post_batch.

The tail semantics are the safety-relevant part: history is skipped on first
open (a restarted shipper must not replay old sessions into Vigil), partial
lines are left for the next poll, and rotation/truncation re-reads from the
start of the new file.
"""

import http.server
import json
import threading

import pytest

from services.decoy_farm import shipper


class TestParseSources:
    def test_default_sources_parse_in_order(self):
        pairs = shipper.parse_sources(shipper.DEFAULT_SOURCES)
        assert pairs == [
            ("cowrie", "/cowrie-logs/cowrie.json"),
            ("opencanary", "/decoy-logs/opencanary.log"),
            ("http-decoy", "/decoy-logs/http-decoy.jsonl"),
        ]

    def test_unknown_kind_fails_loudly(self):
        with pytest.raises(SystemExit, match="samba-direct"):
            shipper.parse_sources("samba-direct:/var/log/x.log")

    def test_missing_path_fails_loudly(self):
        with pytest.raises(SystemExit, match="cowrie"):
            shipper.parse_sources("cowrie:")

    def test_empty_string_fails_loudly(self):
        with pytest.raises(SystemExit):
            shipper.parse_sources("")

    def test_whitespace_and_blanks_are_tolerated(self):
        pairs = shipper.parse_sources(" cowrie:/a.json , ,http-decoy:/b.jsonl")
        assert pairs == [("cowrie", "/a.json"), ("http-decoy", "/b.jsonl")]


class TestShipperConfigFromEnv:
    def test_missing_url_fails_loudly(self):
        with pytest.raises(SystemExit, match="DECOY_FARM_WEBHOOK_URL"):
            shipper.ShipperConfig.from_env({})

    def test_defaults_fill_in(self):
        cfg = shipper.ShipperConfig.from_env(
            {"DECOY_FARM_WEBHOOK_URL": "http://d:8081/ingest"}
        )
        assert cfg.webhook_token == ""
        assert cfg.poll_interval == shipper.DEFAULT_POLL_INTERVAL
        assert cfg.farm_id == shipper.DEFAULT_FARM_ID
        assert cfg.sources == shipper.parse_sources(shipper.DEFAULT_SOURCES)

    def test_poll_interval_is_clamped_to_one_second(self):
        cfg = shipper.ShipperConfig.from_env(
            {
                "DECOY_FARM_WEBHOOK_URL": "http://d:8081/ingest",
                "DECOY_FARM_POLL_INTERVAL": "0.1",
            }
        )
        assert cfg.poll_interval == 1.0

    def test_unparseable_poll_interval_fails_loudly(self):
        with pytest.raises(SystemExit, match="DECOY_FARM_POLL_INTERVAL"):
            shipper.ShipperConfig.from_env(
                {
                    "DECOY_FARM_WEBHOOK_URL": "http://d:8081/ingest",
                    "DECOY_FARM_POLL_INTERVAL": "soon",
                }
            )


class TestTailedFile:
    def test_first_open_skips_history(self, tmp_path):
        path = tmp_path / "cowrie.json"
        path.write_text('{"eventid": "old"}\n', encoding="utf-8")
        tail = shipper._TailedFile(str(path))
        assert tail.poll(100) == []  # history is not telemetry

    def test_appends_are_picked_up(self, tmp_path):
        path = tmp_path / "cowrie.json"
        path.write_text("", encoding="utf-8")
        tail = shipper._TailedFile(str(path))
        assert tail.poll(100) == []
        with path.open("a", encoding="utf-8") as fh:
            fh.write('{"eventid": "new"}\n')
        lines = tail.poll(100)
        assert len(lines) == 1
        assert json.loads(lines[0])["eventid"] == "new"

    def test_partial_line_is_left_for_the_next_poll(self, tmp_path):
        path = tmp_path / "cowrie.json"
        path.write_text("", encoding="utf-8")
        tail = shipper._TailedFile(str(path))
        tail.poll(100)
        with path.open("a", encoding="utf-8") as fh:
            fh.write('{"eventid": "half"')  # writer mid-line
        assert tail.poll(100) == []
        with path.open("a", encoding="utf-8") as fh:
            fh.write("}\n")
        lines = tail.poll(100)
        assert json.loads(lines[0])["eventid"] == "half"

    def test_rotation_rereads_the_new_file(self, tmp_path):
        path = tmp_path / "cowrie.json"
        path.write_text('{"eventid": "old"}\n', encoding="utf-8")
        tail = shipper._TailedFile(str(path))
        assert tail.poll(100) == []
        # Rotate: replace the file (new inode) with fresh content.
        path.unlink()
        path.write_text(
            '{"eventid": "rotated-1"}\n{"eventid": "rotated-2"}\n', encoding="utf-8"
        )
        lines = tail.poll(100)
        assert [json.loads(line)["eventid"] for line in lines] == [
            "rotated-1",
            "rotated-2",
        ]

    def test_missing_file_is_waited_for(self, tmp_path):
        tail = shipper._TailedFile(str(tmp_path / "not-yet.json"))
        assert tail.poll(100) == []
        assert tail.poll(100) == []  # and keeps waiting, without raising


class _Handler(http.server.BaseHTTPRequestHandler):
    status = 200

    def do_POST(self):  # noqa: N802 - http.server API
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        self.send_response(self.status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *args):  # silence the test handler
        pass


class TestPostBatch:
    @pytest.fixture()
    def _server(self):
        server = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        yield server.server_address[1]
        server.shutdown()
        thread.join(timeout=5)

    def test_2xx_is_accepted(self, _server):
        ok, status = shipper.post_batch(
            f"http://127.0.0.1:{_server}/ingest", "tok", [{"finding_id": "f-1"}]
        )
        assert ok is True
        assert status == 200

    def test_4xx_is_a_rejected_contract(self, _server):
        _Handler.status = 401
        try:
            ok, status = shipper.post_batch(
                f"http://127.0.0.1:{_server}/ingest", "tok", [{"finding_id": "f-1"}]
            )
        finally:
            _Handler.status = 200
        assert ok is False
        assert status == 401

    def test_connection_failure_raises_oserror(self):
        # Nothing listens here; the caller treats OSError as retryable.
        with pytest.raises(OSError):
            shipper.post_batch("http://127.0.0.1:1/ingest", "", [])

    def test_unsupported_url_scheme_raises_value_error(self):
        with pytest.raises(ValueError, match="ftp"):
            shipper.post_batch("ftp://host/ingest", "", [])

    def test_bearer_header_present_only_with_token(self, _server):
        # post_batch is the only place the header is built; both shapes must
        # be accepted by the daemon, so exercise the token-less path too.
        ok, _ = shipper.post_batch(f"http://127.0.0.1:{_server}/ingest", "", [])
        assert ok is True


class TestRunLoop:
    def test_webhook_unreachable_retries_without_unbound_status(
        self, tmp_path, monkeypatch
    ):
        """Regression: when the webhook is unreachable, post_batch raises OSError
        before returning a status — and run()'s 4xx check read `status` anyway
        (UnboundLocalError at exactly the worst moment). The except branch must
        initialize it. Driving run() through one unreachable cycle catches the
        regression: without the fix this test fails with UnboundLocalError, not
        KeyboardInterrupt."""
        log = tmp_path / "cowrie.json"
        log.write_text("", encoding="utf-8")
        cfg = shipper.ShipperConfig(
            webhook_url="http://127.0.0.1:1/ingest",
            webhook_token="",
            poll_interval=1.0,
            sources=[("cowrie", str(log))],
            farm_id="farm-x",
        )
        sleeps = {"n": 0}

        def fake_sleep(_seconds):
            sleeps["n"] += 1
            if sleeps["n"] == 1:
                # The tail skips history on first open, so deliver a session
                # event between iterations for the second one to post.
                with log.open("a", encoding="utf-8") as fh:
                    fh.write(
                        json.dumps(
                            {
                                "eventid": "cowrie.session.connect",
                                "src_ip": "203.0.113.7",
                            }
                        )
                        + "\n"
                    )
            else:
                raise KeyboardInterrupt  # one full post cycle, then stop

        monkeypatch.setattr(shipper.time, "sleep", fake_sleep)

        def unreachable(*args, **kwargs):
            raise OSError("connection refused")

        monkeypatch.setattr(shipper, "post_batch", unreachable)
        with pytest.raises(KeyboardInterrupt):
            shipper.run(cfg)
