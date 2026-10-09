"""The sync plane: how the daemon talks to the control plane and reconciles
after a partition (design spec, "Partition is a state, not an error").

``client`` is the authenticated HTTP surface (bundle pull, heartbeat, batched
journal upload, enrollment); ``backoff`` is the jittered exponential schedule
that keeps a fleet of reconnecting nodes from stampeding the ingestion path;
``protocol`` maps journal records to wire events; ``reconciler`` drains the
journal with durable acks and closes the offline window; ``drift`` builds the
post-partition report; ``loop`` runs the whole cadence and owns the operating
states. Imports nothing from ``core`` — the wire contracts are the only
coupling to the control plane.
"""
