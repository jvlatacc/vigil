// Package enforce holds the enforcement engine: target validation, TTL
// handling, idempotent dispatch to the kernel, and the evidence returned to
// the caller. Everything here is kernel-agnostic — the Kernel seam is the
// only place kernel-specific behaviour lives.
package enforce

import "net"

// Kind names an enforcement primitive. v1 keeps API kinds and kernel
// primitives 1:1 — one BPF program per kind.
type Kind string

const (
	// KindXDPDrop drops matching packets in the NIC driver (XDP verdict path).
	KindXDPDrop Kind = "xdp_drop"
	// KindSocketRedirect steers matching flows to the capture sink instead of
	// dropping them.
	KindSocketRedirect Kind = "socket_redirect"
	// KindProcessInterdict denies connect/exec for the target process.
	KindProcessInterdict Kind = "process_interdict"
)

// AllKinds is the fixed v1 kind vocabulary, in contract order.
var AllKinds = []Kind{KindXDPDrop, KindSocketRedirect, KindProcessInterdict}

// Kinds returns a copy of the kind vocabulary — callers get their own slice
// so they cannot mutate the package-level AllKinds.
func Kinds() []Kind {
	out := make([]Kind, len(AllKinds))
	copy(out, AllKinds)
	return out
}

// Valid reports whether k is one of the three v1 kinds.
func (k Kind) Valid() bool {
	switch k {
	case KindXDPDrop, KindSocketRedirect, KindProcessInterdict:
		return true
	}
	return false
}

// mapName is the pinned map backing the kind, under MapPinDir.
func (k Kind) mapName() string {
	switch k {
	case KindXDPDrop:
		return "xdp_block_v1"
	case KindSocketRedirect:
		return "socket_redir_v1"
	case KindProcessInterdict:
		return "interdict_v1"
	}
	return ""
}

// MapPinDir is where the daemon pins its maps. Scoping everything under one
// directory is what makes the daemon's kernel footprint enumerable (spec:
// maps scoped to /sys/fs/bpf/vigil/).
const MapPinDir = "/sys/fs/bpf/vigil"

// Capability is the startup probe result for one kind. The daemon degrades
// per primitive instead of failing whole: a host without LSM BPF still gets
// XDP drops.
type Capability struct {
	Supported bool   `json:"supported"`
	Reason    string `json:"reason,omitempty"`
	// Degraded marks a primitive enforced through a fallback mechanism —
	// supported, but not the primary mechanism (the interdict kind's
	// signal suspension when BPF LSM is unavailable). /healthz reports
	// the daemon degraded while any primitive is degraded.
	Degraded bool `json:"-"`
}

// ModeReporter is the optional kernel capability of reporting the
// enforcement mechanism a kind uses — "bpf" for the primary mechanism, or
// a degraded fallback ("signal"). Kernels that do not distinguish
// mechanisms report nothing and /healthz omits the mode.
type ModeReporter interface {
	Mode(kind Kind) string
}

// Stats are the per-kind kernel reads behind /metrics: in-kernel counters and
// how many entries the kind's pinned map currently holds.
type Stats struct {
	Counters  map[string]uint64
	Occupancy int
}

// Kernel is the seam between the enforcement engine and the kernel. This
// skeleton ships with FakeKernel so the API logic is fully testable without
// kernel capabilities; the next PR implements it with cilium/ebpf against
// CO-RE objects compiled at image build time. Implementations must be safe
// for concurrent use.
type Kernel interface {
	// Attach makes sure the kind's program is attached and returns the attach
	// point (for example "eth0/xdp") — it goes verbatim into the evidence.
	Attach(kind Kind) (string, error)
	// MapUpdate writes one enforcement entry into the kind's pinned map and
	// returns the pinned map path plus the slot the entry landed in — both go
	// verbatim into the evidence.
	MapUpdate(kind Kind, key, value []byte) (string, int, error)
	// Release removes one entry from the kind's pinned map.
	Release(kind Kind, key []byte) error
	// Capability probes whether the kind can be enforced on this host.
	Capability(kind Kind) Capability
	// Stats reads the kind's counters and map occupancy.
	Stats(kind Kind) (Stats, error)
}

// SinkSetter is the optional kernel capability of steering a redirect
// primitive's flows into a live sink socket. main.go checks for it after
// construction and dials the configured sink; a kernel without it never
// promises redirection.
type SinkSetter interface {
	// SetSink inserts the connected sink socket (a tarpit or capture
	// listener) into the redirect primitive's sockmap. The kernel holds the
	// connection for its lifetime.
	SetSink(conn net.Conn) error
}

// Degrader is the optional kernel capability of marking a primitive degraded
// after startup — for example when the sink dial fails: the entry was in the
// map (MapUpdate succeeded) but no sink socket exists to steer into, so the
// primitive must stop reporting itself as enforceable.
type Degrader interface {
	MarkDegraded(kind Kind, reason string)
}
