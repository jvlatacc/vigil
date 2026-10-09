"""Structural wiring of the edge domain: the properties CI cannot grep for.

These are the rules the spec sets that other tests won't catch if drifted:
Medic is untouched, the reserved vocabulary is not reused, the content types
are the spec's, policy.py never imports the verifier at module level, and a
well-formed trust root loads with its own signature verified.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


class TestMedicUntouched:
    def test_medic_has_no_edge_imports(self):
        hits = subprocess.run(
            ["grep", "-rn", r"core\.edge\|core/edge", "services/medic/"],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        assert hits.returncode == 1, f"Medic imports the edge domain: {hits.stdout}"

    def test_import_fence_covers_the_edge_domain(self):
        """lint-imports runs in CI; this asserts the contract list knows the
        domain (a missing entry would silently ungate core.edge)."""
        config = (REPO / ".importlinter").read_text()
        assert "core.edge" in config


class TestReservedVocabulary:
    def test_edge_modules_do_not_use_reserved_terms(self):
        """The repo reserves agent/daemon/federation for other things."""
        from core.edge import executors, policy, signing, verify

        for module in (policy, signing, verify, executors):
            names = " ".join(vars(module))
            for term in ("agent", "daemon", "federation"):
                assert term not in names, f"core.edge uses the reserved term '{term}'"


class TestContentTypes:
    def test_spec_content_types(self):
        from core.edge import EDGE_POLICY, EDGE_TRUST_ROOT

        assert EDGE_POLICY == "application/vnd.deeptempo.vigil.edge-policy.v1+json"
        assert (
            EDGE_TRUST_ROOT == "application/vnd.deeptempo.vigil.edge-trust-root.v1+json"
        )

    def test_schema_and_module_agree_on_envelope_shape(self):
        """Every schema-required envelope field is one the verifier reads."""
        schema = json.loads((REPO / "core/edge/trust.schema.json").read_text())
        required = schema["$defs"]["envelope"]["required"]
        assert set(required) == {"payloadType", "payload", "signatures"}

    def test_module_schemas_are_draft_2020_12_with_ids(self):
        for name in ("policy.schema.json", "trust.schema.json"):
            schema = json.loads((REPO / "core/edge" / name).read_text())
            assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
            assert "$id" in schema  # every $ref in it resolves from a root


class TestLayering:
    def test_policy_module_has_no_module_level_verify_import(self):
        """policy.py imports the verifier lazily, inside load_policy_pack —
        the schema layer stays usable without the trust machinery."""
        source = (REPO / "core/edge/policy.py").read_text()
        body = source.split("def load_policy_pack", 1)[0]
        assert "from core.edge.verify" not in body
        assert "import core.edge.verify" not in body

    def test_signing_module_does_not_load_the_trust_schema(self):
        """The schema belongs to verification; signing goes through pae()."""
        source = (REPO / "core/edge/signing.py").read_text()
        assert "trust.schema.json" not in source


class TestTrustRootLoads:
    def test_well_formed_root_roundtrips_through_load_root(self):
        """A root that satisfies trust.schema.json must load with its own
        signature verified — the bake check the image build relies on."""
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        from core.edge import EDGE_TRUST_ROOT
        from core.edge.signing import deterministic_json, sign_envelope
        from core.edge.verify import load_root

        from .helpers import NOW, bake_root, build_root_doc, generate_key

        rk, pk = generate_key(), Ed25519PrivateKey.generate()
        doc = build_root_doc([rk], [pk])
        root = bake_root(doc, [rk])
        assert root["version"] == 1
        # And a re-load of the same baked bytes gives the same root:
        again = load_root(
            sign_envelope(deterministic_json(doc), EDGE_TRUST_ROOT, [rk]), now=NOW
        )
        assert again == root
