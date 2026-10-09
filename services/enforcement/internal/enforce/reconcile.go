package enforce

import (
	"errors"
	"fmt"
	"time"
)

// MapEntry is one live entry in a kind's pinned map as the reconciler sees
// it: the raw map key and its decoded expiry.
type MapEntry struct {
	Key    []byte
	Expiry time.Time
}

// mapStore is the map-level read/write view the reconciler needs. BPFKernel
// implements it over the real pinned maps; FakeKernel implements it in
// memory, which is what makes TTL eviction CI-testable over the faked kernel
// interface (spec: decision logic runs against the faked interface; the real
// kernel path is verified by the veth runbook).
type mapStore interface {
	Entries(kind Kind) ([]MapEntry, error)
	Evict(kind Kind, key []byte) error
}

// Reconciler evicts expired enforcement entries. The datapath ignores
// expired entries on its own (fail-open compare in the BPF programs), so
// eviction reclaims LRU capacity and keeps /metrics occupancy honest; it is
// not what makes a block stop.
type Reconciler struct {
	Store mapStore
}

// ReconcileExpired evicts every entry whose expiry has passed and returns
// how many were evicted. Errors are joined, not swallowed: one kind's read
// failure must not hide another kind's eviction, and the caller sees every
// failure in one error.
func (r *Reconciler) ReconcileExpired(now time.Time) (int, error) {
	var evicted int
	var errs []error
	for _, kind := range Kinds() {
		entries, err := r.Store.Entries(kind)
		if err != nil {
			errs = append(errs, fmt.Errorf("%s: reading entries: %w", kind, err))
			continue
		}
		for _, e := range expiredEntries(entries, now) {
			if err := r.Store.Evict(kind, e.Key); err != nil {
				errs = append(errs, fmt.Errorf("%s: evicting %x: %w", kind, e.Key, err))
				continue
			}
			evicted++
		}
	}
	return evicted, errors.Join(errs...)
}

// expiredEntries returns the entries that are no longer in force at now.
// The boundary matches the datapath's: an entry blocks while now < expiry,
// so it is expired the instant now >= expiry.
func expiredEntries(entries []MapEntry, now time.Time) []MapEntry {
	var out []MapEntry
	for _, e := range entries {
		if !now.Before(e.Expiry) {
			out = append(out, e)
		}
	}
	return out
}
