"""Warden — the Local Autonomy Mesh's edge runtime.

A standalone asyncio process embedded in cluster nodes and VPC gateways. It
keeps defending its segment when the control plane is unreachable: it syncs a
signed containment-policy pack while connected (``PolicySync``), triages local
alerts against it (``Sentinel`` + the core/edge decision ladder), enforces
only what the signed autonomy envelope allows (``Enforcer`` through registered
executors), journals every decision to a tamper-evident chain (``journal``),
and keeps local state under a 0700 data dir. It has no database, no Redis,
and no control-plane internals — only the shared ``core.edge`` domain.

Naming invariant: the repo reserves "agent" (AI agents + the TS agent layer),
"daemon" (the SOC daemon), and "federation" (source polling). This runtime is
Warden — ``services/warden/`` and ``core/edge/`` — and the reserved terms are
not reused for it.
"""
