"""Decoy environment — minimal high-interaction SSH and HTTP decoys.

Scope (spec plane 03, art_Yf4EZifj): plausibly hold an attacker's session,
capture everything they do, and leak nothing real. Three invariants shape
every module here:

- Canary credentials are the only credentials a decoy holds, and they always
  authenticate (``canary.py``).
- A session is never terminated by an error — log it and continue
  (``session.py`` and both decoys).
- Config flows through ``core.config`` settings and ``core.secrets``; a raw
  environment read here would fail the repo's ambient-state ratchet.
"""
