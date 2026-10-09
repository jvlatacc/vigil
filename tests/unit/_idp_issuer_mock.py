"""A stand-in identity provider for the MCP surface's JWT tests.

One RSA key, a JWKS endpoint over real HTTP on loopback, and the tokens it
signs -- the parts worth testing for real: PyJWT fetches and caches the key
set the way it will in a deployment. The account store is faked at its own
seam (``store_with``), not here; nothing token-shaped is a secret and nothing
here reaches the network beyond loopback.
"""

from __future__ import annotations

import json
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

# Keygen is the slow part; one key is all an issuer ever has.
_key = None


def _issuers_key():
    global _key
    if _key is None:
        _key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return _key


class Issuer:
    """An OIDC issuer: the key its JWKS serves, and the tokens it signs."""

    def __init__(
        self, issuer: str = "https://idp.example.test", audience: str = "vigil-mcp"
    ):
        self.key = _issuers_key()
        self.kid = "idp-test-key"
        self.issuer = issuer
        self.audience = audience
        jwk = RSAAlgorithm.to_jwk(self.key.public_key(), as_dict=True)
        jwk.update({"kid": self.kid, "use": "sig", "alg": "RS256"})
        self.jwks = {"keys": [jwk]}
        self._server: ThreadingHTTPServer | None = None
        self.jwks_url = ""

    def start(self) -> "Issuer":
        issuer = self

        class _JWKS(BaseHTTPRequestHandler):
            def do_GET(self):
                body = json.dumps(issuer.jwks).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):  # the tests need no request log
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _JWKS)
        self.jwks_url = f"http://127.0.0.1:{self._server.server_port}/jwks.json"
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self

    def stop(self):
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    def __enter__(self) -> "Issuer":
        return self.start()

    def __exit__(self, *exc):
        self.stop()

    def token(self, signed_with=None, **overrides) -> str:
        """A token this issuer would have signed -- overrides bend it wrong."""
        now = int(time.time())
        claims = {
            "iss": self.issuer,
            "aud": self.audience,
            "sub": "idp-subject-1",
            "exp": now + 300,
            "iat": now,
        }
        claims.update(overrides)
        return jwt.encode(
            claims,
            signed_with if signed_with is not None else self.key,
            algorithm="RS256",
            headers={"kid": self.kid},
        )


def settings_for(issuer: Issuer):
    """The Settings a deployment carries when it configures this issuer."""
    from core.config import Settings

    return Settings(
        vigil_mcp_oidc_issuer=issuer.issuer,
        vigil_mcp_oidc_audience=issuer.audience,
        vigil_mcp_oidc_jwks_url=issuer.jwks_url,
    )


def store_with(user):
    """A stand-in for the account store behind ``idp_user``.

    Returns a replacement for ``unit_of_work`` whose user lookup always
    answers ``user`` -- None meaning no account maps. What sits above it,
    the JWT verifier, runs for real.
    """

    @contextmanager
    def fake_unit_of_work(session=None):
        class _Query:
            def filter(self, *args, **kwargs):
                return self

            def first(self):
                return user

        class _Store:
            def query(self, *args):
                return _Query()

        yield _Store()

    return fake_unit_of_work
