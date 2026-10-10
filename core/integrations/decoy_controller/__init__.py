"""Decoy-controller integration — the steering control plane Vigil programs.

Slice anatomy mirrors ``cloudflare``: a descriptor (Settings → Integrations
entry), a stdio MCP tool server for the agent path, and sync REST helpers the
daemon path imports. The remote service is the in-repo reference controller
(``services/decoy_controller/``); anything speaking its API shape (a vendor
appliance, an overlay controller) works the same way.
"""
