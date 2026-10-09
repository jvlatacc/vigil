"""In-memory streaming CEP for Vigil.

Spec of record: "In-Memory Streaming CEP for Vigil" (project prj_qKAjwNOs).
The engine taps the daemon's finding-queue seam beside FindingProcessor so
compound sequences correlate while findings are still in flight — before the
SIEM has indexed anything. Containment always routes through the existing
approval gate (``core.response``); nothing here executes an action.
"""
