"""Twin domain package.

The digital twin: the network Vigil actually sees, derived from finding
``entity_context`` — entities as nodes, observed relationships as edges,
every finding pinned to the node it concerns. ``graph`` holds the pure
derivation; ``twin_router`` serves it on the unversioned console surface.
"""

from core.twin.graph import build_graph

__all__ = [
    "build_graph",
]
