-- Digital-twin tables: the physical-to-logical map the console's digital-twin
-- graph reads.
--
-- Part of the digital-twin persistence slice: the ingest API and graph
-- endpoint (a later PR) read and upsert these tables; nothing else in the
-- backend consumes them yet. Three surfaces, one per layer of the map:
--
-- twin_devices     a physical resource — MAC address, serial number — that a
--                  feed (the demo seed, a host sensor, a vendor adapter)
--                  observed. ip_address is the last address it was seen at:
--                  the heuristic key the graph's cross-device "talks-to"
--                  edges match on, not an identity. mac_address and
--                  serial_number are the identity, stored canonical (MAC in
--                  the lower-case colon form aa:bb:cc:dd:ee:ff) so the index
--                  compares equal to what it matches with.
-- twin_processes   a process observed on a device, named by its PID. (device,
--                  pid, name) identifies a process within one observation
--                  window; the ingest's serialization of that triple is the
--                  process_key later observations upsert against.
-- twin_connections a network connection observed on a device — socket, stream,
--                  or session (check-constrained). A connection dies with its
--                  device (CASCADE) but may outlive its process: a network
--                  sensor reports device-level traffic it cannot attribute to
--                  a PID, so process_id is nullable and SET NULL on process
--                  deletion, demoting the row to a device-level connection
--                  rather than erasing an observed flow.
--
-- The *_key columns are the upsert conflict targets: one row per observed
-- entity, so re-posting a batch updates last_seen and changes no row counts.
-- "user" is a reserved word in PostgreSQL and quoted on purpose — the column
-- name matches the ingest payload the API PR defines.
--
-- A file of its own (42), not an edit to an earlier one: the Helm init job
-- records each file once it has run, so edits never reach a cluster that
-- already applied the original. scripts/migrate_schema.py covers a database
-- this file never reached.

CREATE TABLE IF NOT EXISTS twin_devices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Natural key the ingest upserts against (host name, MAC, or serial —
    -- whichever identity the source provides), never a client-supplied UUID.
    device_key VARCHAR(255) NOT NULL,

    hostname TEXT,
    ip_address VARCHAR(45),
    mac_address VARCHAR(32),
    serial_number VARCHAR(64),

    -- server | workstation | appliance | iot | container_host | ... — an open
    -- vocabulary, deliberately unconstrained: the taxonomy grows per source.
    device_type VARCHAR(30) NOT NULL DEFAULT 'unknown',

    os_info TEXT,
    source VARCHAR(50) NOT NULL,
    first_seen TIMESTAMP NOT NULL DEFAULT now(),
    last_seen TIMESTAMP NOT NULL DEFAULT now(),
    attributes JSONB
);

CREATE UNIQUE INDEX IF NOT EXISTS uniq_twin_devices_device_key
    ON twin_devices (device_key);
CREATE INDEX IF NOT EXISTS idx_twin_devices_ip_address
    ON twin_devices (ip_address);
CREATE INDEX IF NOT EXISTS idx_twin_devices_mac_address
    ON twin_devices (mac_address);
CREATE INDEX IF NOT EXISTS idx_twin_devices_serial_number
    ON twin_devices (serial_number);

CREATE TABLE IF NOT EXISTS twin_processes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    process_key VARCHAR(255) NOT NULL,
    device_id UUID NOT NULL REFERENCES twin_devices (id) ON DELETE CASCADE,
    pid INTEGER NOT NULL,
    name VARCHAR(255) NOT NULL,
    "user" VARCHAR(100),
    command TEXT,
    started_at TIMESTAMP,
    source VARCHAR(50) NOT NULL,
    first_seen TIMESTAMP NOT NULL DEFAULT now(),
    last_seen TIMESTAMP NOT NULL DEFAULT now(),
    attributes JSONB
);

CREATE UNIQUE INDEX IF NOT EXISTS uniq_twin_processes_process_key
    ON twin_processes (process_key);
-- Process lookups lead with the device (the graph's "what ran on this box").
CREATE INDEX IF NOT EXISTS idx_twin_processes_device_pid
    ON twin_processes (device_id, pid);

CREATE TABLE IF NOT EXISTS twin_connections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    connection_key VARCHAR(255) NOT NULL,
    device_id UUID NOT NULL REFERENCES twin_devices (id) ON DELETE CASCADE,
    process_id UUID REFERENCES twin_processes (id) ON DELETE SET NULL,

    -- socket | stream | session.
    connection_type VARCHAR(16) NOT NULL,
    protocol VARCHAR(16),
    local_ip VARCHAR(45),
    local_port INTEGER,
    remote_ip VARCHAR(45),
    remote_port INTEGER,
    state VARCHAR(30),
    direction VARCHAR(10),
    source VARCHAR(50) NOT NULL,
    started_at TIMESTAMP,
    first_seen TIMESTAMP NOT NULL DEFAULT now(),
    last_seen TIMESTAMP NOT NULL DEFAULT now(),
    attributes JSONB,

    CONSTRAINT ck_twin_connections_connection_type
        CHECK (connection_type IN ('socket', 'stream', 'session'))
);

CREATE UNIQUE INDEX IF NOT EXISTS uniq_twin_connections_connection_key
    ON twin_connections (connection_key);
-- The graph reads a device's connections filtered by layer class.
CREATE INDEX IF NOT EXISTS idx_twin_connections_device_type
    ON twin_connections (device_id, connection_type);
-- The talks-to pivot: which connections point at a given address.
CREATE INDEX IF NOT EXISTS idx_twin_connections_remote_ip
    ON twin_connections (remote_ip);

COMMENT ON TABLE twin_devices IS
    'Digital twin: observed physical resources (MAC, serial) the graph maps to processes and connections.';
COMMENT ON TABLE twin_processes IS
    'Digital twin: processes observed on twin_devices, named by PID; upserted via process_key.';
COMMENT ON TABLE twin_connections IS
    'Digital twin: network connections (socket|stream|session) observed on twin_devices; upserted via connection_key.';
