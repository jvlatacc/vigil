# Enqueue agent runs onto the queue the TypeScript agent layer consumes. The
# backend enqueues plain JSON and never writes agent_events.

from __future__ import annotations

import asyncio
import logging
import uuid
from weakref import WeakKeyDictionary
from datetime import datetime, timezone
from typing import Any, Dict, NamedTuple, Optional, Sequence
from urllib.parse import quote

from bullmq import Queue

from core.agents.internal_token import bearer_header
from core.config import get_settings

logger = logging.getLogger(__name__)

# No colon: the Node library refuses a queue name containing one, while the
# Python library accepts it and writes the keys anyway. Keys are bull:agent-runs:*.
RUN_QUEUE = "agent-runs"

JOB_SCHEMA_VERSION = 1

DEFAULT_REDIS_URL = "redis://localhost:6379/0"

# What the backend may enqueue. Chat is absent deliberately: a conversation is a
# Durable Object at the edge, so its turns are dispatched over HTTP, not queued.
RUN_KINDS = ("hunt", "investigate", "compose")

# BullMQ defaults to one attempt, so a job that throws is permanently failed and
# nothing rescues it: the watchdog sweeps lapsed lease rows, and a job that died on
# its way into leases.claim never wrote one. On a dev box a transient Postgres or
# Redis failure is rare; under Kubernetes -- rolling upgrades, evictions, failover --
# it is routine, and the run would be lost with nothing reaching the console.
#
# Retrying is safe rather than merely tolerable: advance() checks terminal first and
# leases.claim is a conditional UPDATE, so a second attempt takes exactly the path a
# watchdog resume takes -- reachable because a failed attempt hands its lease back
# (services/agent/worker.ts::forget).
#
# The consumer reads these off the job, so the Node worker honours what is set here.
RUN_ATTEMPTS = 3
RUN_BACKOFF = {"type": "exponential", "delay": 5000}


def _redis_url() -> str:
    return get_settings().redis_url or DEFAULT_REDIS_URL


# The reason="start" arm of the RunJob union in the agent layer's job contract.
def build_start_job(
    run_id: str,
    run_kind: str,
    request: Dict[str, Any],
    enqueued_by: str,
    tenant_id: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "schema_version": JOB_SCHEMA_VERSION,
        "run_id": run_id,
        "run_kind": run_kind,
        "tenant_id": tenant_id,
        "enqueued_at": datetime.now(timezone.utc).isoformat(),
        "enqueued_by": enqueued_by,
        "reason": "start",
        "request": request,
    }


# A resume carries no request: the ledger holds the spec, and what unblocks the
# run is the decision the agent layer reads back, not anything said here.
def build_resume_job(
    run_id: str,
    run_kind: str,
    enqueued_by: str,
    tenant_id: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "schema_version": JOB_SCHEMA_VERSION,
        "run_id": run_id,
        "run_kind": run_kind,
        "tenant_id": tenant_id,
        "enqueued_at": datetime.now(timezone.utc).isoformat(),
        "enqueued_by": enqueued_by,
        "reason": "resume",
    }


_queues: "WeakKeyDictionary[asyncio.AbstractEventLoop, Queue]" = WeakKeyDictionary()


# One per event loop, not per call: a Queue per enqueue costs a Redis connection.
# Keyed by loop because its connection is bound to the one that made it.
def _run_queue() -> Queue:
    loop = asyncio.get_running_loop()
    queue = _queues.get(loop)
    if queue is None:
        queue = Queue(RUN_QUEUE, {"connection": _redis_url()})
        _queues[loop] = queue
    return queue


# Called on shutdown, so the connection does not outlive the loop that made it.
async def close_run_queue() -> None:
    queue = _queues.pop(asyncio.get_running_loop(), None)
    if queue is not None:
        await queue.close()


async def enqueue_run(job: Dict[str, Any], job_id: Optional[str] = None) -> str:
    queue = _run_queue()
    try:
        # jobId is the run id for a start, so a double POST dedupes in BullMQ. A
        # resume takes a fresh id: any derived one repeats, and the queue drops it.
        enqueued = await queue.add(
            "run",
            job,
            {
                "jobId": job_id or _default_job_id(job),
                "attempts": RUN_ATTEMPTS,
                "backoff": RUN_BACKOFF,
            },
        )
        logger.info("enqueued agent run %s (%s)", job["run_id"], job["run_kind"])
        return str(enqueued.id)
    except Exception:
        # A queue that failed is not reused: the next call builds a fresh one
        # rather than inheriting a connection that may already be gone.
        await close_run_queue()
        raise


def _default_job_id(job: Dict[str, Any]) -> str:
    if job.get("reason") == "start":
        return str(job["run_id"])
    return f"{job['run_id']}:{uuid.uuid4()}"


def new_run_id() -> str:
    return str(uuid.uuid4())


# A turn is admitted, not awaited: the edge answers 202 the moment the delivery is
# durable, and the answer itself is read from the stream named in the receipt.
CHAT_DISPATCH_TIMEOUT_S = 10.0


class ChatDispatchError(RuntimeError):
    pass


class ChatDispatch(NamedTuple):
    submission_id: str
    stream_url: str
    # Where the reader resumes. Opaque: it is passed back verbatim, never parsed.
    offset: Optional[str]


# The identity a conversation is created with, resolved here because this is the
# side that authenticated the human and knows what their scope allows.
def chat_identity(
    user_id: str,
    model: str,
    scopes: Sequence[str],
    tenant_id: Optional[str] = None,
    system_prompt: str = "",
    tools: Optional[Sequence[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    return {
        "userId": user_id,
        "scopes": list(scopes),
        "tenantId": tenant_id,
        "model": model,
        "systemPrompt": system_prompt,
        # The arch document's declaration shape, renamed to the edge's field. Both
        # carry the same JSON Schema, so nothing is reshaped on the way through.
        "tools": [
            {
                "name": tool["id"],
                "description": tool["description"],
                "parameters": tool.get("parameters") or {"type": "object"},
            }
            for tool in (tools or ())
        ],
    }


# Identity travels with the delivery rather than on the request, because the agent
# reading it may run days later, on a machine this call never touched.
async def dispatch_chat_turn(
    conversation_id: str,
    text: str,
    identity: Dict[str, Any],
) -> ChatDispatch:
    import httpx

    url = (
        f"{get_settings().edge_url.rstrip('/')}/chat/{quote(conversation_id, safe='')}"
    )
    body: Dict[str, Any] = {"message": text, "initialData": identity}
    try:
        async with httpx.AsyncClient(timeout=CHAT_DISPATCH_TIMEOUT_S) as client:
            response = await client.post(url, json=body, headers=bearer_header())
    except httpx.HTTPError as exc:
        raise ChatDispatchError(f"the edge did not answer: {exc}") from exc

    # Anything but 202 means the turn was never admitted. Reporting it as dispatched
    # would leave the console reading a stream that will never carry an answer.
    if response.status_code != 202:
        detail = response.text[:200]
        raise ChatDispatchError(
            f"the edge refused the turn ({response.status_code}): {detail}"
        )

    receipt = response.json()
    stream_url = receipt.get("streamUrl")
    if not stream_url:
        raise ChatDispatchError("the edge admitted the turn but named no stream")

    logger.info("dispatched chat turn for conversation %s", conversation_id)
    return ChatDispatch(
        submission_id=str(receipt.get("submissionId") or ""),
        stream_url=str(stream_url),
        offset=receipt.get("offset"),
    )
