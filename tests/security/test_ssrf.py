"""Regression tests for FIN-005 — SSRF via LLM provider discovery.

Covers the ``core.platform.url_safety.validate_provider_url`` gate that all
provider-discovery / provider-test paths now run through.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from core.platform.url_safety import (  # noqa: E402
    DEFAULT_ALLOWED_PROVIDER_HOSTS,
    UrlSafetyError,
    validate_provider_url,
)

pytestmark = pytest.mark.unit


# Every entry must raise UrlSafetyError. Sourced from the disclosure
# plus the standard SSRF playbook.
BLOCKED_URLS = [
    "http://127.0.0.1:11434",
    "http://localhost:11434",
    "http://[::1]:11434",
    "http://0.0.0.0/admin",
    "http://169.254.169.254/latest/meta-data?x=",
    "http://10.0.0.1/admin?x=",
    "http://172.16.0.1/admin?x=",
    "http://192.168.1.1/admin?x=",
    "http://fd00::1/admin",  # private IPv6
    "file:///etc/passwd",
    "gopher://attacker/",
    "ftp://attacker/",
    "http://user:pass@api.openai.com/v1",  # userinfo banned
    "http://api.openai.com/v1#frag",  # fragment banned
]


@pytest.mark.parametrize("url", BLOCKED_URLS)
def test_blocked_url_rejected(url):
    with pytest.raises(UrlSafetyError):
        validate_provider_url(url, allow_custom=True)


def test_allowlisted_host_passes():
    safe = validate_provider_url("https://api.openai.com/v1", allow_custom=False)
    assert safe.is_allowlisted_host
    assert safe.sanitized == "https://api.openai.com/v1"


def test_query_string_stripped():
    """The disclosure showed ``base_url=http://x/foo?proof=`` letting an
    attacker control the path of the final request once the handler
    appended ``/models``. Verify the validator strips the query
    string."""
    safe = validate_provider_url(
        "https://api.openai.com/internal/status?proof=", allow_custom=False
    )
    assert "?" not in safe.sanitized
    assert "proof" not in safe.sanitized
    assert safe.sanitized == "https://api.openai.com/internal/status"


def test_non_allowlisted_requires_allow_custom():
    with pytest.raises(UrlSafetyError):
        validate_provider_url("https://attacker.example/", allow_custom=False)


def test_default_allowed_hosts_includes_openai_anthropic():
    assert "api.openai.com" in DEFAULT_ALLOWED_PROVIDER_HOSTS
    assert "api.anthropic.com" in DEFAULT_ALLOWED_PROVIDER_HOSTS


# An IPv4-mapped IPv6 literal connects as real IPv4 on Linux, so it must
# not slip the metadata block by classifying as a plain private address.
IPV4_MAPPED_METADATA = [
    "http://[::ffff:169.254.169.254]/latest/meta-data",
    "http://[::ffff:a9fe:a9fe]/latest/meta-data",
]


@pytest.mark.parametrize("url", IPV4_MAPPED_METADATA)
def test_ipv4_mapped_metadata_blocked_even_with_loopback(url):
    with pytest.raises(UrlSafetyError):
        validate_provider_url(url, allow_custom=True, allow_loopback=True)


def test_allow_loopback_permits_localhost_but_not_metadata():
    safe = validate_provider_url("http://127.0.0.1:11434", allow_loopback=True)
    assert safe.sanitized == "http://127.0.0.1:11434"
    with pytest.raises(UrlSafetyError):
        validate_provider_url(
            "http://169.254.169.254/latest/meta-data", allow_loopback=True
        )


# --- Extension connector origins (E15) ----------------------------------------
#
# The gate above answers for LLM provider base URLs. A second SSRF-shaped
# surface is the page-extension connector: Vigil mints a session token by
# calling the connectorUrl an operator configured, and the CSP admits the
# origin's bundle to the browser. core/integrations/extension/trust.py is
# the single source of truth for what may be trusted: https always, http
# only on loopback, and — when the operator set EXTENSION_CONNECTOR_ALLOWLIST
# — membership in it, compared on canonicalized origins.
#
# The allowlist defaulting to empty is the shipped, documented default (the
# scheme rule alone applies at the trust gate; the CSP admits no connector
# origin until the operator lists one). It is pinned here so a silent flip
# to strict-by-default — or a hole in the other direction — lands as a red
# test, not as a behavior change nobody noticed.


def _with_allowlist(monkeypatch, origins):
    """Swap the settings the trust module reads, without a Settings import
    chain: connector_allowlist_origins() reads one attribute off it."""
    from types import SimpleNamespace

    from core.integrations.extension import trust

    monkeypatch.setattr(
        trust,
        "get_settings",
        lambda: SimpleNamespace(extension_connector_allowlist=origins),
    )
    return trust


def test_a_non_allowlisted_origin_is_refused_as_a_connector_target(monkeypatch):
    """The E15 refusal: with the allowlist set, membership is enforced."""
    trust = _with_allowlist(monkeypatch, ["https://connector.example"])

    assert not trust.is_trusted_connector_url("https://attacker.example/v1")


def test_an_allowlisted_origin_passes(monkeypatch):
    trust = _with_allowlist(monkeypatch, ["https://connector.example"])

    assert trust.is_trusted_connector_url("https://connector.example/v1")


def test_allowlist_matching_is_canonical(monkeypatch):
    """Entries match on canonicalized origins: scheme and host are
    case-insensitive, and an explicit port is part of the origin — an
    entry on :8443 does not bless the same host on :443."""
    trust = _with_allowlist(monkeypatch, ["https://Connector.Example"])

    assert trust.is_trusted_connector_url("https://connector.example")

    trust = _with_allowlist(monkeypatch, ["https://connector.example:8443"])

    assert not trust.is_trusted_connector_url("https://connector.example")


def test_a_junk_allowlist_entry_does_not_widen_the_allowlist(monkeypatch):
    """canonical_origin() drops entries with no scheme+host — a typo in the
    env var narrows what is trusted, never widens it."""
    trust = _with_allowlist(monkeypatch, ["https://connector.example", "not a url", ""])

    assert trust.is_trusted_connector_url("https://connector.example/v1")
    assert not trust.is_trusted_connector_url("https://attacker.example/v1")


def test_with_the_allowlist_unset_the_scheme_rule_alone_applies(monkeypatch):
    """The shipped default: no EXTENSION_CONNECTOR_ALLOWLIST means https —
    or http on loopback — from any host passes the trust gate. What a
    connector origin may do in the browser is the CSP's separate answer,
    and an empty allowlist admits nothing there (the backend warns at
    startup when connectors are configured in that state)."""
    trust = _with_allowlist(monkeypatch, [])

    assert trust.is_trusted_connector_url("https://any-host.example/v1")
    assert not trust.is_trusted_connector_url("http://any-host.example/v1")
    assert trust.is_trusted_connector_url("http://127.0.0.1:8787")
