"""Honey-routing enforcement integration (MTD deception plane).

Turns an approved ``honey_route`` response action into real enforcement: a
backend (Cilium first) pins an attacker's flows to a decoy registered in
``mtd_decoy_registry``. The decision plane lives in ``core.response``; this
slice only ever executes what that plane approved.

A missing backend is an honest failure, never a fabricated success — the
``isolate_host`` rule.
"""
