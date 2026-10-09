package enforce

import (
	"fmt"
	"sync"
)

// FakeKernel is the in-memory kernel behind this skeleton. Its semantics —
// slot assignment, occupancy, per-kind counters, attach points — mirror what
// the real cilium/ebpf loader will do, closely enough to pin the API's
// behaviour in CI. The error/capability fields let tests drive the failure
// paths the real kernel will have.
type FakeKernel struct {
	// Interface names the NIC that attach-point evidence refers to.
	Interface string
	// MaxEntries per map, like the LRU hashes the real loader will create.
	MaxEntries int
	// AttachErr / UpdateErr, when set for a kind, make the corresponding
	// kernel call fail — the error paths the real loader will hit.
	AttachErr map[Kind]error
	UpdateErr map[Kind]error
	// Caps overrides the capability probe; a missing entry means supported.
	Caps map[Kind]Capability

	mu       sync.Mutex
	attached map[Kind]string
	slots    map[Kind]int
	entries  map[Kind]map[string]bool
	counters map[Kind]map[string]uint64
	calls    map[Kind]*counts
}

type counts struct {
	attach, update, release int
}

// NewFakeKernel builds a FakeKernel for the named interface, with the
// canonical per-kind counters present at zero — the shape the real kernel's
// per-primitive counters will have.
func NewFakeKernel(interfaceName string) *FakeKernel {
	return &FakeKernel{
		Interface:  interfaceName,
		MaxEntries: 65536,
		attached:   make(map[Kind]string),
		slots:      make(map[Kind]int),
		entries:    make(map[Kind]map[string]bool),
		counters: map[Kind]map[string]uint64{
			KindXDPDrop:          {"dropped_packets": 0},
			KindSocketRedirect:   {"redirected_packets": 0},
			KindProcessInterdict: {"denied_ops": 0},
		},
		calls: make(map[Kind]*counts),
	}
}

// Counts returns per-kind kernel call counts — how tests assert that a
// replay never re-enforced.
func (f *FakeKernel) Counts(kind Kind) (attach, update, release int) {
	f.mu.Lock()
	defer f.mu.Unlock()
	c := f.calls[kind]
	if c == nil {
		return 0, 0, 0
	}
	return c.attach, c.update, c.release
}

// Bump simulates kernel datapath activity (packets dropped, flows
// redirected) so tests can watch counters move through /metrics.
func (f *FakeKernel) Bump(kind Kind, counter string, delta uint64) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.counters[kind] == nil {
		f.counters[kind] = make(map[string]uint64)
	}
	f.counters[kind][counter] += delta
}

func (f *FakeKernel) Attach(kind Kind) (string, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.call(kind).attach++
	if err := f.AttachErr[kind]; err != nil {
		return "", err
	}
	if p, ok := f.attached[kind]; ok {
		return p, nil
	}
	p := f.attachPoint(kind)
	f.attached[kind] = p
	return p, nil
}

func (f *FakeKernel) MapUpdate(kind Kind, key, value []byte) (string, int, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.call(kind).update++
	if err := f.UpdateErr[kind]; err != nil {
		return "", 0, err
	}
	if _, ok := f.attached[kind]; !ok {
		return "", 0, fmt.Errorf("%s: not attached", kind)
	}
	if len(f.entries[kind]) >= f.MaxEntries {
		return "", 0, fmt.Errorf("%s: map full", kind.mapName())
	}
	if f.entries[kind] == nil {
		f.entries[kind] = make(map[string]bool)
	}
	slot := f.slots[kind]
	f.slots[kind]++
	f.entries[kind][string(key)] = true
	return MapPinDir + "/" + kind.mapName(), slot, nil
}

func (f *FakeKernel) Release(kind Kind, key []byte) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.call(kind).release++
	// An absent key is a no-op, matching libbpf's quiet ENOENT on delete —
	// releases stay idempotent at the kernel level too.
	delete(f.entries[kind], string(key))
	return nil
}

func (f *FakeKernel) Capability(kind Kind) Capability {
	f.mu.Lock()
	defer f.mu.Unlock()
	if c, ok := f.Caps[kind]; ok {
		return c
	}
	return Capability{Supported: true}
}

func (f *FakeKernel) Stats(kind Kind) (Stats, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	cs := make(map[string]uint64, len(f.counters[kind]))
	for k, v := range f.counters[kind] {
		cs[k] = v
	}
	return Stats{Counters: cs, Occupancy: len(f.entries[kind])}, nil
}

func (f *FakeKernel) attachPoint(kind Kind) string {
	switch kind {
	case KindXDPDrop:
		return f.Interface + "/xdp"
	case KindSocketRedirect:
		return f.Interface + "/sockmap"
	case KindProcessInterdict:
		return "cgroup/vigil"
	}
	return "unknown"
}

func (f *FakeKernel) call(kind Kind) *counts {
	c := f.calls[kind]
	if c == nil {
		c = &counts{}
		f.calls[kind] = c
	}
	return c
}
