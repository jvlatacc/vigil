"""Wire schemas for the digital-twin graph (console surface).

Built by ``core.twin.graph.build_graph`` and served by
``core.twin.twin_router``. Plain response models, not :class:`ORMSchema`:
the graph is derived in code, never read back from a table.
"""

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from core.storage.schemas.base import IsoDateTime


class TwinNodeSchema(BaseModel):
    """One map node: a host, an address, an account, or the Unattributed sink."""

    id: str  # "host:web-01" · "ip:10.0.4.12" · "user:j.vanlowe" · "unattributed"
    kind: Literal["host", "ip", "user", "unattributed"]
    label: str
    finding_ids: List[str] = Field(default_factory=list)
    case_ids: List[str] = Field(default_factory=list)
    severity_counts: Dict[str, int] = Field(default_factory=dict)
    x: Optional[float] = None  # deterministic initial layout, computed server-side
    y: Optional[float] = None


class TwinEdgeSchema(BaseModel):
    """One observed relationship between two nodes."""

    id: str
    source: str
    target: str
    kind: Literal["flow", "link"]  # flow = src→dst of one finding; link = co-named
    weight: int  # distinct findings behind this edge
    finding_ids: List[str] = Field(default_factory=list)


class TwinGraphSchema(BaseModel):
    """The whole map in one payload."""

    generated_at: IsoDateTime
    nodes: List[TwinNodeSchema] = Field(default_factory=list)
    edges: List[TwinEdgeSchema] = Field(default_factory=list)
    unattributed_finding_ids: List[str] = Field(default_factory=list)
