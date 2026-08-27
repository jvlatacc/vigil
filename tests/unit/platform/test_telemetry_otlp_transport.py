"""Which OTLP transport gets used, and whether it is encrypted.

Before this wiring existed, the exporter was chosen by whichever import
succeeded and the gRPC channel was constructed with ``insecure=True``
unconditionally. Against an in-cluster collector that is harmless. Against the
external OTLP endpoint the Cloudflare topology requires, it means spans -- which
carry investigation ids, finding attributes and, when opted in, IOC values --
leave the tier in plaintext while the configured URL says ``https``.

So the two decisions are pure functions, and these are their tests: protocol
normalization (with a loud fallback rather than silent telemetry loss) and TLS
derived from the endpoint scheme unless explicitly overridden.
"""

from __future__ import annotations

import logging

import pytest

from core.telemetry import _resolve_otlp_protocol, _use_insecure_channel


class TestResolveOtlpProtocol:
    @pytest.mark.parametrize(
        ("configured", "expected"),
        [
            ("grpc", "grpc"),
            ("GRPC", "grpc"),
            ("  grpc  ", "grpc"),
            ("http/protobuf", "http/protobuf"),
            ("HTTP/PROTOBUF", "http/protobuf"),
            # The Python exporter has no JSON implementation, so http/json and
            # bare http both resolve to the protobuf-over-HTTP exporter.
            ("http", "http/protobuf"),
            ("http/json", "http/protobuf"),
        ],
    )
    def test_accepted_values(self, configured: str, expected: str) -> None:
        assert _resolve_otlp_protocol(configured) == expected

    @pytest.mark.parametrize("configured", ["", "   ", "gprc", "otlp", "thrift"])
    def test_unknown_value_falls_back_to_grpc(self, configured: str) -> None:
        assert _resolve_otlp_protocol(configured) == "grpc"

    def test_unknown_value_is_reported_not_swallowed(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A typo costs a warning, not a silently dark trace pipeline."""
        with caplog.at_level(logging.WARNING, logger="core.telemetry"):
            _resolve_otlp_protocol("gprc")
        assert "gprc" in caplog.text
        assert "grpc" in caplog.text


class TestUseInsecureChannel:
    @pytest.mark.parametrize(
        ("endpoint", "expected_insecure"),
        [
            # The repo default: local collector, plaintext, unchanged behavior.
            ("http://localhost:4317", True),
            ("http://otel-collector:4317", True),
            # External endpoint: TLS, which the old unconditional insecure=True
            # silently disabled.
            ("https://otlp.example.com", False),
            ("HTTPS://OTLP.EXAMPLE.COM:443", False),
            ("  https://otlp.example.com  ", False),
            # No scheme: cannot claim TLS, so do not pretend. Override exists.
            ("otlp.example.com:4317", True),
        ],
    )
    def test_derived_from_endpoint_scheme(
        self, endpoint: str, expected_insecure: bool
    ) -> None:
        assert _use_insecure_channel(endpoint, None) is expected_insecure

    @pytest.mark.parametrize("endpoint", ["https://otlp.example.com", "http://localhost:4317"])
    @pytest.mark.parametrize("override", [True, False])
    def test_explicit_override_wins_over_the_scheme(
        self, endpoint: str, override: bool
    ) -> None:
        assert _use_insecure_channel(endpoint, override) is override


class TestSettingsDefaults:
    def test_defaults_preserve_the_previous_local_behavior(self) -> None:
        """Nobody's existing local setup changes: gRPC to a plaintext collector."""
        from core.config import Settings

        settings = Settings(_env_file=None)
        assert settings.otel_exporter_otlp_protocol == "grpc"
        assert settings.otel_exporter_otlp_insecure is None
        assert _resolve_otlp_protocol(settings.otel_exporter_otlp_protocol) == "grpc"
        assert (
            _use_insecure_channel(
                settings.otel_exporter_otlp_endpoint,
                settings.otel_exporter_otlp_insecure,
            )
            is True
        )
