"""Decoy farm support code: decoys, telemetry normalization, log shipper.

Third leg of feature 5 (honey-routing): the decoy plane that steered traffic
lands in. Like the decoy-controller, this package is a standalone deployment
— stdlib only, no ``core/`` imports, configured through its environment — so
its containers carry none of Vigil's credentials and none of Vigil's
machinery.

- ``http_decoy.py``: the fake internal app decoy (stdlib http.server)
- ``telemetry.py``: pure normalizers, decoy events -> Vigil finding payloads
- ``shipper.py``: tails decoy logs on the shared volume, posts to the
  daemon's generic ingest webhook
- ``opencanary_config.py``: build-time config merge for the OpenCanary image

Deployment lives in infra/docker/docker-compose.yml (profile ``deception``,
network ``decoy-net``); the compose ratchet keeps the containment invariants
(tests/unit/_ratchets/test_compose_deception_profile.py).
"""
