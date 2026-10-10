package enforce

import (
	"errors"
	"testing"
	"time"
)

// The reconciler runs over the faked kernel interface: entries land through
// the engine (Enforce -> MapUpdate), the reconciler evicts past expiry, and
// unexpired entries survive. This is the CI-facing half of the spec's
// self-expiry story; the kernel path is the runbook's.
func TestReconcilerEvictsOnlyExpiredEntries(t *testing.T) {
	fk := NewFakeKernel("eth0")
	e := newTestEnforcer(t, fk)

	if _, err := e.Enforce(blockInput("aa-long", "198.51.100.9")); err != nil {
		t.Fatalf("Enforce long block: %v", err)
	}
	short := blockInput("aa-short", "203.0.113.7")
	short.TTLSeconds = 60
	if _, err := e.Enforce(short); err != nil {
		t.Fatalf("Enforce short block: %v", err)
	}

	rec := &Reconciler{Store: fk}
	// One second before the short block's expiry: nothing may be evicted.
	if n, err := rec.ReconcileExpired(fixedNow.Add(59 * time.Second)); err != nil || n != 0 {
		t.Fatalf("evicted = %d, err = %v, want 0/nil before expiry", n, err)
	}
	stats, err := fk.Stats(KindXDPDrop)
	if err != nil {
		t.Fatalf("Stats: %v", err)
	}
	if stats.Occupancy != 2 {
		t.Errorf("occupancy = %d, want 2 before expiry", stats.Occupancy)
	}

	// At the expiry instant the short block is gone — and only it.
	n, err := rec.ReconcileExpired(fixedNow.Add(60 * time.Second))
	if err != nil {
		t.Fatalf("ReconcileExpired: %v", err)
	}
	if n != 1 {
		t.Errorf("evicted = %d, want 1", n)
	}
	stats, err = fk.Stats(KindXDPDrop)
	if err != nil {
		t.Fatalf("Stats: %v", err)
	}
	if stats.Occupancy != 1 {
		t.Errorf("occupancy = %d, want 1 after eviction", stats.Occupancy)
	}

	// A second pass at the same instant is a no-op (idempotent).
	if n, err := rec.ReconcileExpired(fixedNow.Add(60 * time.Second)); err != nil || n != 0 {
		t.Errorf("second reconcile evicted = %d, err = %v, want 0/nil", n, err)
	}
}

// The reconciler walks every kind, not just the first one — the three
// primitives' maps all age out.
func TestReconcilerWalksEveryKind(t *testing.T) {
	fk := NewFakeKernel("eth0")
	e := newTestEnforcer(t, fk)

	inputs := []Input{
		blockInput("aa-drop", "203.0.113.7"),
		{ActionID: "aa-redirect", Kind: KindSocketRedirect, IP: "203.0.113.8", Port: 4444, TTLSeconds: 60, Reason: "tarpit", IdempotencyKey: "socket_redirect:203.0.113.8:4444"},
		{ActionID: "aa-interdict", Kind: KindProcessInterdict, PID: 4242, TTLSeconds: 60, Reason: "ransomware staging", IdempotencyKey: "interdict_process:4242"},
	}
	inputs[0].TTLSeconds = 60 // blockInput's default is the 1-hour block
	for i := range inputs {
		if _, err := e.Enforce(inputs[i]); err != nil {
			t.Fatalf("Enforce %s: %v", inputs[i].ActionID, err)
		}
	}

	n, err := (&Reconciler{Store: fk}).ReconcileExpired(fixedNow.Add(60 * time.Second))
	if err != nil {
		t.Fatalf("ReconcileExpired: %v", err)
	}
	if n != 3 {
		t.Errorf("evicted = %d, want one per kind (3)", n)
	}
}

// failingStore fails Evict for the key it was told to fail — the reconciler
// must surface the failure and keep evicting the rest.
type failingStore struct {
	fk        *FakeKernel
	failEvict map[string]bool
	failed    []string
}

func (s *failingStore) Entries(kind Kind) ([]MapEntry, error) { return s.fk.Entries(kind) }

func (s *failingStore) Evict(kind Kind, key []byte) error {
	if s.failEvict[string(key)] {
		s.failed = append(s.failed, string(key))
		return errors.New("kernel said no")
	}
	return s.fk.Evict(kind, key)
}

func TestReconcilerSurfacesEvictionErrors(t *testing.T) {
	fk := NewFakeKernel("eth0")
	e := newTestEnforcer(t, fk)
	victim := blockInput("aa-stuck", "203.0.113.7")
	if _, err := e.Enforce(victim); err != nil {
		t.Fatalf("Enforce: %v", err)
	}
	other := blockInput("aa-free", "198.51.100.9")
	other.TTLSeconds = 60
	if _, err := e.Enforce(other); err != nil {
		t.Fatalf("Enforce: %v", err)
	}

	target, terr := parseTarget(KindXDPDrop, victim.IP, victim.Port, victim.PID)
	if terr != nil {
		t.Fatalf("parsing target: %v", terr)
	}
	key := target.key()
	store := &failingStore{fk: fk, failEvict: map[string]bool{string(key): true}}

	n, err := (&Reconciler{Store: store}).ReconcileExpired(fixedNow.Add(3600 * time.Second))
	if err == nil {
		t.Fatal("an eviction failure must surface, not vanish")
	}
	if len(store.failed) != 1 {
		t.Errorf("failed evictions = %v, want only the stuck key", store.failed)
	}
	if n != 1 {
		t.Errorf("evicted = %d, want 1 — one stuck key must not block the rest", n)
	}
	// The stuck entry is still there; the other is gone.
	stats, err := fk.Stats(KindXDPDrop)
	if err != nil {
		t.Fatalf("Stats: %v", err)
	}
	if stats.Occupancy != 1 {
		t.Errorf("occupancy = %d, want 1 (only the stuck entry remains)", stats.Occupancy)
	}
}
