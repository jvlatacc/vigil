"""The verifier that answers for the identity provider's tokens.

What it proves and what it refuses -- signature against the issuer's JWKS,
strict issuer and audience, every timestamp and claim present -- and what it
never does: provision an account, trust the issuer's opinion about roles, or
say in a log which way a credential failed or what the credential was.
"""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest


@pytest.fixture
def an_issuer():
    from tests.unit._idp_issuer_mock import Issuer

    with Issuer() as issuer:
        yield issuer


def _a_verifier_configured(an_issuer):
    from tests.unit._idp_issuer_mock import settings_for

    return patch("core.auth.idp_jwt.get_settings", return_value=settings_for(an_issuer))


def test_the_verifier_needs_an_issuer_an_audience_and_a_key_set():
    """All three settings or nothing: a verifier missing one cannot answer."""
    from core.auth.idp_jwt import idp_jwt_active
    from core.config import Settings

    assert idp_jwt_active(Settings()) is False

    only_issuer = Settings(vigil_mcp_oidc_issuer="https://issuer.example")
    assert idp_jwt_active(only_issuer) is False

    no_key_set = Settings(
        vigil_mcp_oidc_issuer="https://issuer.example",
        vigil_mcp_oidc_audience="vigil-mcp",
    )
    assert idp_jwt_active(no_key_set) is False

    complete = Settings(
        vigil_mcp_oidc_issuer="https://issuer.example",
        vigil_mcp_oidc_audience="vigil-mcp",
        vigil_mcp_oidc_jwks_url="https://issuer.example/jwks.json",
    )
    assert idp_jwt_active(complete) is True


def test_an_explicit_veto_keeps_the_verifier_off_when_configured():
    """The tri-state is an operator's say, not a default they can be surprised by."""
    from core.auth.idp_jwt import idp_jwt_active
    from core.config import Settings

    vetoed = Settings(
        vigil_mcp_oidc_enabled=False,
        vigil_mcp_oidc_issuer="https://issuer.example",
        vigil_mcp_oidc_audience="vigil-mcp",
        vigil_mcp_oidc_jwks_url="https://issuer.example/jwks.json",
    )
    assert idp_jwt_active(vetoed) is False


def test_the_subject_is_what_a_working_token_carries(an_issuer):
    """Round trip through a real JWKS fetch, a real signature check."""
    from core.auth.idp_jwt import verify_idp_token

    with _a_verifier_configured(an_issuer):
        assert verify_idp_token(an_issuer.token()) == "idp-subject-1"


def test_a_refusal_never_logs_the_token(an_issuer, caplog):
    """What a caller sent is their business; the log learns only the refusal."""
    from core.auth.idp_jwt import verify_idp_token

    a_token = an_issuer.token()
    tampered = a_token[:-6] + "xxxxxx"

    with _a_verifier_configured(an_issuer), caplog.at_level(logging.DEBUG):
        assert verify_idp_token(tampered) is None

    assert a_token not in caplog.text
    assert tampered not in caplog.text


def test_an_unmapped_subject_is_refused(an_issuer):
    """Nothing the token says can create the account it would act as."""
    from core.auth.idp_jwt import idp_user
    from tests.unit._idp_issuer_mock import store_with

    with _a_verifier_configured(an_issuer), patch(
        "core.auth.idp_jwt.unit_of_work", store_with(None)
    ):
        assert idp_user(an_issuer.token()) is None


def test_the_subject_maps_to_the_account_an_administrator_named(an_issuer):
    from core.auth.idp_jwt import idp_user
    from tests.unit._idp_issuer_mock import store_with

    class _Person:
        username = "ext-alice"
        is_active = True

    with _a_verifier_configured(an_issuer), patch(
        "core.auth.idp_jwt.unit_of_work", store_with(_Person())
    ):
        mapped = idp_user(an_issuer.token())

    assert mapped is not None
    assert mapped.username == "ext-alice"


def test_a_deactivated_account_is_refused(an_issuer):
    """A mapping to an account that cannot sign in does not sign in here either."""
    from core.auth.idp_jwt import idp_user
    from tests.unit._idp_issuer_mock import store_with

    class _Deactivated:
        username = "ext-alice"
        is_active = False

    with _a_verifier_configured(an_issuer), patch(
        "core.auth.idp_jwt.unit_of_work", store_with(_Deactivated())
    ):
        assert idp_user(an_issuer.token()) is None


def test_a_store_that_cannot_answer_refuses_instead_of_erroring(an_issuer):
    """A database that is down has not authenticated anybody."""
    from contextlib import contextmanager

    from core.auth.idp_jwt import idp_user

    @contextmanager
    def a_store_that_fails(session=None):
        raise RuntimeError("the database is unreachable")
        yield  # pragma: no cover - never reached

    with _a_verifier_configured(an_issuer), patch(
        "core.auth.idp_jwt.unit_of_work", a_store_that_fails
    ):
        assert idp_user(an_issuer.token()) is None
