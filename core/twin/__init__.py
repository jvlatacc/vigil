"""Twin domain package.

The digital twin: the devices in Vigil's environment, the processes on
them, and the connections between them — upserted from observation batches
by natural key and read back as a layered graph. ``ingest`` holds the
upsert and read logic behind the versioned contract surface
(``core.api.v1.digital_twin_router``); there is no other twin API.
"""

from core.twin.ingest import (
    TwinReferenceError,
    build_graph_payload,
    derive_connection_key,
    derive_device_key,
    derive_edges,
    derive_process_key,
    ingest_batch,
    list_devices,
)

__all__ = [
    "TwinReferenceError",
    "build_graph_payload",
    "derive_connection_key",
    "derive_device_key",
    "derive_edges",
    "derive_process_key",
    "ingest_batch",
    "list_devices",
]
