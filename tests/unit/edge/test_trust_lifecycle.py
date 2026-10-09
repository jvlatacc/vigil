"""Trust-root lifecycle: revocation is immediate, rotation is monotonic.

Medic-grade properties the spec names explicitly: a revoked key signs nothing,
a newer root can only be installed by the current root role (and its own new
role when the keys change), versions never go down, and no key is ever
un-revoked.
"""

from __future__ import annotations

from core.edge import EDGE_TRUST_ROOT
from core.edge.policy import load_policy_pack
from core.edge.signing import deterministic_json, keyid_for, sign_envelope
from core.edge.verify import load_root, update_trust_root

from .helpers import (
    NOW,
    build_root_doc,
    default_root,
    generate_key,
    policy_doc,
    sign_policy,
)


class TestRevocation:
    def test_a_revoked_policy_key_signs_nothing(self):
        key = generate_key()
        root = default_root(policy_keys=[key], revoked=(key,))
        data = sign_policy(policy_doc(), [key])
        out = load_policy_pack(data, root, now=NOW)
        assert out.pack is None and out.codes == {"S-REVOKED"}

    def test_revocation_names_the_key(self):
        key = generate_key()
        root = default_root(policy_keys=[key], revoked=(key,))
        data = sign_policy(policy_doc(), [key])
        out = load_policy_pack(data, root, now=NOW)
        assert keyid_for(key) in out.errors[0][1]


class TestRotation:
    def _v2_doc(self, new_rk, *, revoked=()):
        """A v2 root: new root key, same policy role shape, version bumped."""
        return build_root_doc(
            [new_rk],
            [generate_key()],
            version=2,
            issued_at="2026-10-08T00:00:00Z",
            revoked=revoked,
        )

    def test_rotation_signed_by_both_roles_is_accepted(self):
        rk1, rk2 = generate_key(), generate_key()
        current = default_root(root_keys=[rk1])
        doc2 = self._v2_doc(rk2)
        data = sign_envelope(deterministic_json(doc2), EDGE_TRUST_ROOT, [rk1, rk2])
        res = update_trust_root(current, data, now=NOW)
        assert res.ok and not res.errors
        # And the v2 root loads standalone once signed by its own role:
        standalone = sign_envelope(deterministic_json(doc2), EDGE_TRUST_ROOT, [rk2])
        assert load_root(standalone, now=NOW)["version"] == 2

    def test_stale_root_version_is_refused(self):
        rk1 = generate_key()
        current = default_root(root_keys=[rk1])
        data = sign_envelope(
            deterministic_json(build_root_doc([rk1], [generate_key()], version=1)),
            EDGE_TRUST_ROOT,
            [rk1],
        )
        res = update_trust_root(current, data, now=NOW)
        assert not res.ok
        assert {c for c, _ in res.errors} == {"S-ROOT-VERSION"}

    def test_un_revocation_is_refused(self):
        """A key the current root revoked can never come back — the one
        transition that only tightens, never loosens."""
        rk1, dead = generate_key(), generate_key()
        current = default_root(root_keys=[rk1], revoked=(dead,))
        # v2 drops the revocation — and doesn't even carry the dead key.
        doc2 = build_root_doc([rk1], [generate_key()], version=2)
        data = sign_envelope(deterministic_json(doc2), EDGE_TRUST_ROOT, [rk1])
        res = update_trust_root(current, data, now=NOW)
        assert not res.ok
        assert {c for c, _ in res.errors} == {"S-ROOT-UNREVOKE"}

    def test_rotation_needs_the_new_root_role_too(self):
        """When the root keyids change, the new root role must also sign —
        the current role alone cannot hand trust to keys it does not know."""
        rk1, rk2 = generate_key(), generate_key()
        current = default_root(root_keys=[rk1])
        data = sign_envelope(
            deterministic_json(self._v2_doc(rk2)), EDGE_TRUST_ROOT, [rk1]
        )
        res = update_trust_root(current, data, now=NOW)
        assert not res.ok
        assert "S-ROOT-THRESHOLD" in {c for c, _ in res.errors}
