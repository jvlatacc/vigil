# Kernel-path runbook: live eBPF/XDP enforcement demos

CI verifies the enforcement daemon's decision logic against a faked kernel
interface (`internal/enforce/fake.go`); the real kernel path — program
attach, map updates, datapath verdicts, TTL self-expiry — is verified with
this manual runbook. Every transcript below was captured on 2026-10-09
against a real kernel (6.1.158+), using the three shipped CO-RE objects
(`bpf/xdp_drop.c`, `bpf/socket_redirect.c`, `bpf/interdict.c`).

Run it on any Linux host with root, clang (with the BPF target), libelf
headers, and Go. Expect ~5 minutes.

## 1 · Prerequisites

```sh
clang --version          # BPF target support: clang >= 11 (tested on 19)
go version               # tested on 1.27
```

The daemon compiles its CO-RE objects at image build time in production
(the packaging PR wires clang into the builder stage); locally,
`build-bpf.sh` does the same compile. **No kernel headers are needed on
the enforcement host** — CO-RE relocates against the running kernel's BTF.

Kernel requirements by primitive:

| Primitive | Needs | Degrades to |
|---|---|---|
| XDP drop (native) | driver-level XDP on the NIC (or a veth) | `unsupported` in `/healthz` |
| Socket redirect | cgroup v2 sockops + sk_msg | `unsupported` in `/healthz` |
| Process interdict | BPF LSM (`lsm=bpf` in the kernel's LSM list) | SIGSTOP/SIGCONT suspension, `mode: "signal"` |

## 2 · Build the objects and the daemon

```sh
cd services/enforcement
./build-bpf.sh           # clang -> bpf/build/{xdp_drop,socket_redirect,interdict}.o
go build -o /tmp/vigil-enforcer ./cmd/enforcement
```

## 3 · Build the demo topology

A veth pair makes XDP ingress real: packets from `demo-host` arrive at
`vxdp-a`'s driver hook from the *outside*, exactly as hostile traffic
would.

```sh
sudo ip link add vxdp-a type veth peer name vxdp-b
sudo ip addr add 10.200.0.1/24 dev vxdp-a
sudo ip netns add demo-host
sudo ip link set vxdp-b netns demo-host
sudo ip netns exec demo-host ip addr add 10.200.0.2/24 dev vxdp-b
sudo ip link set vxdp-a up
sudo ip netns exec demo-host ip link set lo up
sudo ip netns exec demo-host ip link set vxdp-b up
```

Start two TCP listeners that play C2 (on the enforced path) and forensic
sink (loopback):

```sh
# tcpcat.py (in this directory): accept connections and append every
# received byte to the given file — the forensic sink and the "C2".
python3 tcpcat.py 10.200.0.1 9999 /tmp/c2-captured.txt  &   # "C2" listener
python3 tcpcat.py 127.0.0.1 9999 /tmp/sink-captured.txt &   # forensic sink
```

## 4 · Start the daemon on the real loader

```sh
sudo -n env VIGIL_ENFORCEMENT_TOKEN=runbook-token \
  VIGIL_ENFORCEMENT_INTERFACE=vxdp-a \
  VIGIL_ENFORCEMENT_BPF_DIR="$PWD/bpf/build" \
  VIGIL_ENFORCEMENT_SINK=127.0.0.1:9999 \
  /tmp/vigil-enforcer > /tmp/enforcer.log 2>&1 &
```

Health shows the per-primitive capability probe. On the reference host
(BPF LSM unavailable), the interdict primitive reports its degraded mode:

```sh
$ curl -s http://127.0.0.1:6986/healthz | python3 -m json.tool
{
  "status": "degraded",
  "kernel_faked": "",
  "primitives": {
    "xdp_drop":         {"supported": true, "mode": "bpf"},
    "socket_redirect":  {"supported": true, "mode": "bpf"},
    "process_interdict": {"supported": true, "mode": "signal",
      "reason": "BPF LSM unavailable: kernel reports the hook unsupported
                 (program vigil_interdict_connect: attach LSM/LSMMac:
                 socket_connect LSM hook not supported)"}
  }
}
```

`kernel_faked` is empty — a real loader. The daemon refuses to serve when
the kernel is unreachable; fake mode is an explicit
`VIGIL_ENFORCEMENT_KERNEL=fake` opt-in for dev/CI only.

## 5 · Demo 1 — XDP drop, counters, self-expiry

Baseline traffic passes:

```sh
$ sudo ip netns exec demo-host ping -c 3 10.200.0.1 | tail -1
3 packets transmitted, 3 received, 0% packet loss
```

Enforce a 60-second drop of the source IP (the API echoes the action id
and kernel evidence):

```sh
$ curl -s -X POST http://127.0.0.1:6986/v1/actions \
  -H "Authorization: Bearer runbook-token" -H "Content-Type: application/json" \
  -d '{"action_id":"aa-runbook-xdp-001","kind":"xdp_drop",
       "target":{"ip":"10.200.0.2"},"ttl_seconds":60,
       "reason":"veth runbook: demonstrate driver-level drop",
       "idempotency_key":"xdp_block_ip:10.200.0.2"}' | python3 -m json.tool
{
  "action_id": "aa-runbook-xdp-001",
  "state": "enforced",
  "evidence": {
    "attach_point": "vxdp-a/xdp",
    "map": "/sys/fs/bpf/vigil/xdp_block_v1",
    "map_slot": 0,
    "counters": {"dropped_packets": 0}
  },
  "expires_at": "2026-10-09T22:20:27Z"
}
```

Traffic now dies in the driver — three pings, three drops, counter 3:

```sh
$ sudo ip netns exec demo-host ping -c 3 10.200.0.1 | tail -1
3 packets transmitted, 0 received, 100% packet loss
$ curl -s http://127.0.0.1:6986/metrics | grep dropped_packets
vigil_enforcement_dropped_packets{kind="xdp_drop"} 3
```

Replay the action — idempotent, no second enforcement row:

```sh
$ curl -s -o /dev/null -w "%{http_code}\n" -X POST ... (same body)
200
```

Wait out the TTL: the block self-expires from the datapath — the entry's
value *is* the expiry, so no controller is needed. Pings resume with the
drop counter frozen (an explicit `actions_released` increment happens only
on DELETE — expiry is deliberately not a status change in v1):

```sh
$ sleep 60 && sudo ip netns exec demo-host ping -c 3 10.200.0.1 | tail -1
3 packets transmitted, 3 received, 0% packet loss
$ curl -s http://127.0.0.1:6986/metrics | grep dropped_packets
vigil_enforcement_dropped_packets{kind="xdp_drop"} 3   # frozen
```

## 6 · Demo 2 — socket redirect to the forensic sink

Enforce a 60-second redirect of flows to `10.200.0.1:9999` (the "C2"):

```sh
$ curl -s -X POST http://127.0.0.1:6986/v1/actions \
  -H "Authorization: Bearer runbook-token" -H "Content-Type: application/json" \
  -d '{"action_id":"aa-runbook-redirect-006","kind":"socket_redirect",
       "target":{"ip":"10.200.0.1","port":9999},"ttl_seconds":60,
       "reason":"preserve C2 traffic for forensics (runbook demo)",
       "idempotency_key":"xdp_redirect_socket:10.200.0.1:9999"}' | \
  python3 -c "import json,sys; d=json.load(sys.stdin); print(d['state'], d['evidence'])"
enforced {'attach_point': 'vxdp-a/sockmap', 'map': '/sys/fs/bpf/vigil/socket_redir_v1',
          'map_slot': 0, 'counters': {'redirected_packets': 0}}
```

Beacon from the namespace: the payload reaches the **sink**, not the C2:

```sh
$ sudo ip netns exec demo-host python3 -c "
import socket
s = socket.create_connection(('10.200.0.1', 9999), timeout=5)
s.sendall(b'intercepted-c2-beacon-20261009\n')
s.shutdown(socket.SHUT_WR); s.close()"
$ sleep 2
$ cat /tmp/sink-captured.txt | tail -1
intercepted-c2-beacon-20261009
$ cat /tmp/c2-captured.txt | tail -1
[listening on 10.200.0.1:9999]        # no beacon — traffic never arrived
$ curl -s http://127.0.0.1:6986/metrics | grep redirected
vigil_enforcement_redirected_packets{kind="socket_redirect"} 1
vigil_enforcement_map_entries{kind="socket_redirect"} 1
```

The sk_msg verdict redirected the message (`redirected_packets: 1`). After
the TTL, the same beacon reaches the C2 again and the reconciler's next
tick evicts the expired entry:

```sh
$ sleep 60   # past expires_at
$ sudo ip netns exec demo-host python3 -c "(beacon again)"
$ cat /tmp/c2-captured.txt | tail -1
beacon-after-redirect-expiry
$ cat /tmp/sink-captured.txt | tail -1
intercepted-c2-beacon-20261009       # unchanged — no new interception
$ curl -s http://127.0.0.1:6986/metrics | grep map_entries.*socket_redirect
vigil_enforcement_map_entries{kind="socket_redirect"} 0
$ grep 'evicted expired' /tmp/enforcer.log | tail -1
{"time":"...T22:32:38Z","level":"INFO","msg":"evicted expired enforcement entries","count":1}
```

**Delivery mechanism note:** `bpf_msg_redirect_map` with `BPF_F_INGRESS`
queues the message on the sink socket's receive queue. The sockmap holds
the *daemon's end* of the sink connection (the daemon dials the configured
sink address), so the daemon runs a read-and-echo bridge: a goroutine
reads deposited payloads from its sink socket and writes them straight
back down the wire, delivering them as ordinary TCP data to the configured
sink application (`SetSink` in `internal/enforce/kernel_bpf.go`).

## 7 · Demo 3 — process interdiction (BPF LSM or signal fallback)

On a host with BPF LSM enabled (`lsm=bpf` among the boot-time LSMs), the
primitive attaches cgroup-scoped connect/exec denial. On the reference
host the kernel reports the hooks unsupported, the daemon degrades to
signal mode, and `/healthz` says so (§4).

Suspend a target process through the API; `/proc` state flips `S → T`:

```sh
$ TARGET_PID=$(pgrep -f '^sleep 600$' | head -1)   # any long-running target
$ curl -s -X POST http://127.0.0.1:6986/v1/actions \
  -H "Authorization: Bearer runbook-token" -H "Content-Type: application/json" \
  -d "{\"action_id\":\"aa-runbook-interdict-200\",\"kind\":\"process_interdict\",
       \"target\":{\"pid\":$TARGET_PID},\"ttl_seconds\":60,
       \"reason\":\"contain suspect build process (runbook demo)\",
       \"idempotency_key\":\"interdict_process:$TARGET_PID\"}" | \
  python3 -c "import json,sys; d=json.load(sys.stdin); print(d['state'], d['evidence']['attach_point'])"
enforced pid/signal
$ ps -o pid,stat,cmd -p $TARGET_PID | tail -1
77516 T+   sleep 600
```

No one releases it: the TTL reconciler resumes the process at expiry
(SIGCONT) and logs the eviction receipt — enforcement self-expires in
signal mode exactly as it does in the maps:

```sh
$ sleep 60 && ps -o pid,stat,cmd -p $TARGET_PID | tail -1
77516 S+   sleep 600
$ grep 'evicted expired' /tmp/enforcer.log | tail -1
{"time":"...T22:30:08Z","level":"INFO","msg":"evicted expired enforcement entries","count":1}
```

Signal-mode suspensions are in-memory: graceful shutdown resumes them; a
daemon crash leaves stopped processes unresumed by design (logged at
startup as a warning). Persistence for crash recovery is deferred.

## 8 · Environment caveats (reference sandbox)

- **Cross-session signals**: the reference sandbox silently drops signals
  between processes in different sessions (a tmux-hosted target could not
  be SIGSTOPped even as root). Demos 3's target and daemon therefore run
  in the *same* session. On a normal host (systemd units, shell jobs)
  cross-session SIGSTOP behaves per POSIX; the suspend/resume logic is
  unit-tested against real child processes regardless.
- **LSM list**: the reference kernel runs `capability,landlock,selinux`
  without `bpf`, exercising the degraded path end-to-end. On a host with
  BPF LSM, expect `mode: "bpf"` and `attach_point: cgroup/.../lsm`.
- **CI**: GitHub-hosted runners' `bpf()` capability is unverified; that is
  why this runbook is manual. If runner capability is proven later, §5–§7
  are the script for graduating the kernel path into CI.

## 9 · What to attach to the PR

The transcript outputs above (health JSON, ping loss + drop counter, sink
vs C2 captures, redirected counter, process state transitions, reconciler
eviction receipts) constitute the kernel-path evidence. CI covers the
decision layer over the faked kernel: attach/detach sequencing, map
update/evict, TTL boundaries, capability-probe fallback, idempotent
replays, and contract vectors.
