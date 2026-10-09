"""Enrollment tokens: domain-separated HMAC, bound to node id and expiry.

These are the pure-logic guarantees behind POST /api/v1/edge/enroll: a token
is single-purpose (the exact node id minted into it), single-window (expiry is
checked before anything else), and tamper-evident (any body edit breaks the
MAC). The secret itself never travels.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac as hmac_mod

import pytest

from core.edge.enrollment import (
    DEFAULT_TOKEN_TTL_HOURS,
    ENROLLMENT_SECRET_NAME,
    NODE_ID_MAX_LENGTH,
    EnrollmentTokenError,
    mint_enrollment_token,
    validate_node_id,
    verify_enrollment_token,
)

pytestmark = pytest.mark.unit

SECRET = "enroll-secret-for-tests"
NODE = "wn-7f3a"
PREFIX = "vigil.enroll.v1."
NOW = dt.datetime(2026, 10, 9, 12, 0, 0, tzinfo=dt.UTC)


def _mint(**kwargs) -> str:
    kwargs.setdefault("secret", SECRET)
    kwargs.setdefault("node_id", NODE)
    kwargs.setdefault("expires_at", NOW + dt.timedelta(hours=DEFAULT_TOKEN_TTL_HOURS))
    return mint_enrollment_token(**kwargs)


class TestMintAndVerify:
    def test_roundtrip_returns_the_bound_node_id(self):
        token = _mint()

        assert verify_enrollment_token(token, secret=SECRET, now=NOW) == NODE

    def test_secret_name_is_the_documented_env_key(self):
        # The operator provisioner and the fail-closed 503 both key on this.
        assert ENROLLMENT_SECRET_NAME == "EDGE_ENROLLMENT_TOKEN"

    def test_token_is_a_bearer_shaped_compact_string(self):
        token = _mint()

        assert token.startswith(PREFIX)
        body = token.removeprefix(PREFIX)
        assert body.count(".") == 1  # body.mac
        assert " " not in token

    def test_token_binds_the_node_id_and_expiry_in_its_body(self):
        token = _mint()
        body_b64 = token.removeprefix(PREFIX).rsplit(".", 1)[0]

        payload = base64.urlsafe_b64decode(body_b64 + "=" * (-len(body_b64) % 4))

        assert b'"node_id":"wn-7f3a"' in payload
        assert b'"not_after":"2026-10-10T12:00:00Z"' in payload

    def test_wrong_secret_is_rejected_as_bad_signature(self):
        token = _mint(secret="another-secret")

        with pytest.raises(EnrollmentTokenError) as err:
            verify_enrollment_token(token, secret=SECRET, now=NOW)
        assert err.value.code == "bad-signature"

    def test_tampered_body_is_rejected_even_with_a_recomputed_mac(self):
        # The MAC proves the body is exactly what the control plane minted:
        # an attacker who edits the body cannot re-mint the MAC without the
        # secret. Forge the way a blind forger would (key guessed) and
        # expect refusal.
        token = _mint()
        body_b64, _mac = token.removeprefix(PREFIX).rsplit(".", 1)
        body = base64.urlsafe_b64decode(body_b64 + "=" * (-len(body_b64) % 4))
        forged_body = body.replace(NODE.encode(), b"wn-hacked", 1)
        assert forged_body != body

        blind_mac = hmac_mod.new(
            b"attacker-guess", forged_body, hashlib.sha256
        ).hexdigest()

        with pytest.raises(EnrollmentTokenError) as err:
            verify_enrollment_token(
                f"{PREFIX}{forged_body.decode()}.{blind_mac}", secret=SECRET, now=NOW
            )
        assert err.value.code == "bad-signature"

    def test_expired_token_is_rejected_before_its_node_id_matters(self):
        expiry = NOW + dt.timedelta(hours=DEFAULT_TOKEN_TTL_HOURS)
        token = mint_enrollment_token(secret=SECRET, node_id=NODE, expires_at=expiry)

        with pytest.raises(EnrollmentTokenError) as err:
            verify_enrollment_token(
                token, secret=SECRET, now=expiry + dt.timedelta(seconds=1)
            )
        assert err.value.code == "expired"

    def test_token_valid_on_the_last_second_of_its_lifetime(self):
        expiry = NOW + dt.timedelta(hours=DEFAULT_TOKEN_TTL_HOURS)
        token = mint_enrollment_token(secret=SECRET, node_id=NODE, expires_at=expiry)

        assert (
            verify_enrollment_token(
                token, secret=SECRET, now=expiry - dt.timedelta(seconds=1)
            )
            == NODE
        )

    def test_malformed_strings_are_rejected_not_crashed(self):
        for garbage in (
            "",
            "not-a-token",
            f"{PREFIX}not-base64!!.mac",
            "other-domain-9.aGk.ff",
            f"{PREFIX}{b'x'.hex()}.{b'y'.hex()}",
        ):
            with pytest.raises(EnrollmentTokenError) as err:
                verify_enrollment_token(garbage, secret=SECRET, now=NOW)
            assert err.value.code in ("malformed", "bad-signature", "expired")

    def test_error_carries_no_token_material(self):
        token = _mint()

        with pytest.raises(EnrollmentTokenError) as err:
            verify_enrollment_token(token + "junk", secret=SECRET, now=NOW)

        assert token not in str(err.value)


class TestValidateNodeId:
    @pytest.mark.parametrize(
        "good", ["wn-7f3a", "Node_1", "a", "x" * NODE_ID_MAX_LENGTH]
    )
    def test_accepts_shape_conforming_ids(self, good):
        assert validate_node_id(good) == good

    @pytest.mark.parametrize(
        "bad", ["", " ", "-lead", "_trail", "has space", "x" * (NODE_ID_MAX_LENGTH + 1)]
    )
    def test_rejects_shape_violations(self, bad):
        with pytest.raises(EnrollmentTokenError) as err:
            validate_node_id(bad)
        assert err.value.code == "bad-node-id"

    def test_rejects_injection_characters(self):
        for hostile in ("../etc", "node;drop", "n\x00ull", "a\nb"):
            with pytest.raises(EnrollmentTokenError):
                validate_node_id(hostile)
