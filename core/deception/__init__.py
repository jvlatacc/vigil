"""Dynamic deception routing (feature 5): scores recon signals, holds the
lease registry's domain logic, and fronts the pluggable steering backends.

Vigil decides, scores, leases, and audits here; traffic steering itself
executes through a :class:`~core.deception.backends.SteeringBackend` outside
Vigil's processes — the same vendor-control-plane shape the response pipeline
already uses for Cloudflare. Shipped defaults are inert: the posture is off
and the backend is dry-run until an operator turns both on.
"""
