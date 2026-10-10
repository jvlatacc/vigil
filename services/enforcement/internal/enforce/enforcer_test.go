package enforce

import (
	"errors"
	"strings"
	"sync"
	"testing"
	"time"
)

// fixedNow makes TTL arithmetic exact: every test sees this clock.
var fixedNow = time.Date(2026, 10, 9, 21, 0, 0, 0, time.UTC)

func newTestEnforcer(t *testing.T, fk *FakeKernel) *Enforcer {
	t.Helper()
	e := NewEnforcer(fk, time.Hour)
	e.now = func() time.Time { return fixedNow }
	return e
}

func blockInput(actionID, ip string) Input {
	return Input{
		ActionID:       actionID,
		Kind:           KindXDPDrop,
		IP:             ip,
		TTLSeconds:     3600,
		Reason:         "credential harvesting, finding f-20261009-abc",
		IdempotencyKey: "xdp_block_ip:" + ip,
	}
}

func TestEnforceHappyPathEvidence(t *testing.T) {
	fk := NewFakeKernel("eth0")
	e := newTestEnforcer(t, fk)

	got, enforcerr := e.Enforce(blockInput("aa-2026-10-09-4417", "203.0.113.7"))
	if enforcerr != nil {
		t.Fatalf("Enforce: %v", enforcerr)
	}
	if got.State != StateEnforced {
		t.Errorf("state = %q, want %q", got.State, StateEnforced)
	}
	if got.Evidence.AttachPoint != "eth0/xdp" {
		t.Errorf("attach_point = %q, want eth0/xdp", got.Evidence.AttachPoint)
	}
	if !strings.HasPrefix(got.Evidence.Map, "/sys/fs/bpf/vigil/") {
		t.Errorf("map = %q, want under /sys/fs/bpf/vigil/", got.Evidence.Map)
	}
	if !strings.HasSuffix(got.Evidence.Map, "/xdp_block_v1") {
		t.Errorf("map = %q, want the xdp_block_v1 pinned map", got.Evidence.Map)
	}
	if got.Evidence.Counters == nil || len(got.Evidence.Counters) == 0 {
		t.Errorf("evidence has no counters — evidence without counters is a faked success")
	}
	if _, ok := got.Evidence.Counters["dropped_packets"]; !ok {
		t.Errorf("counters missing dropped_packets: %v", got.Evidence.Counters)
	}
	want := fixedNow.Add(time.Hour).UTC().Truncate(time.Second)
	if !got.ExpiresAt.Equal(want) {
		t.Errorf("expires_at = %v, want %v (created + ttl)", got.ExpiresAt, want)
	}
	if got.Replayed {
		t.Errorf("fresh enforcement must not be marked replayed")
	}
}

func TestReplayIsNoOpReturningOriginalEvidence(t *testing.T) {
	fk := NewFakeKernel("eth0")
	e := newTestEnforcer(t, fk)

	first, err := e.Enforce(blockInput("aa-1", "203.0.113.7"))
	if err != nil {
		t.Fatalf("first Enforce: %v", err)
	}
	fk.Bump(KindXDPDrop, "dropped_packets", 42) // data path moves between deliveries
	second, err := e.Enforce(blockInput("aa-1", "203.0.113.7"))
	if err != nil {
		t.Fatalf("replayed Enforce: %v", err)
	}

	if !second.Replayed {
		t.Errorf("replayed delivery not marked as replay")
	}
	if second.Evidence.MapSlot != first.Evidence.MapSlot || second.Evidence.Map != first.Evidence.Map {
		t.Errorf("replay must return the original evidence: first %+v, second %+v", first.Evidence, second.Evidence)
	}
	if second.ExpiresAt != first.ExpiresAt {
		t.Errorf("replay must not extend expiry: first %v, second %v", first.ExpiresAt, second.ExpiresAt)
	}

	a, u, r := fk.Counts(KindXDPDrop)
	if u != 1 || r != 0 {
		t.Errorf("replay re-enforced: attach=%d update=%d release=%d, want update=1 release=0", a, u, r)
	}
}

func TestActionIDConflict(t *testing.T) {
	e := newTestEnforcer(t, NewFakeKernel("eth0"))

	if _, err := e.Enforce(blockInput("aa-1", "203.0.113.7")); err != nil {
		t.Fatalf("first Enforce: %v", err)
	}
	different := blockInput("aa-1", "198.51.100.9")
	_, err := e.Enforce(different)
	if err == nil || err.Code != ErrCodeActionIDConflict {
		t.Fatalf("reused action_id with different request: err = %v, want %s", err, ErrCodeActionIDConflict)
	}
}

func TestTTLFloorAndDefaults(t *testing.T) {
	e := newTestEnforcer(t, NewFakeKernel("eth0"))

	cases := []struct {
		name    string
		ttl     int
		wantErr string
	}{
		{"exactly at floor is accepted", 60, ""},
		{"below floor refused", 59, ErrCodeTTLBelowFloor},
		{"zero means daemon default (no floor trip)", 0, ""},
		{"above ceiling refused", maxTTLSeconds + 1, ErrCodeInvalidRequest},
	}
	for i, tc := range cases {
		in := blockInput("aa-ttl-"+string(rune('a'+i)), "203.0.113.70")
		in.TTLSeconds = tc.ttl
		_, err := e.Enforce(in)
		if tc.wantErr == "" {
			if err != nil {
				t.Errorf("%s: unexpected error %v", tc.name, err)
			}
			continue
		}
		if err == nil || err.Code != tc.wantErr {
			t.Errorf("%s: err = %v, want %s", tc.name, err, tc.wantErr)
		}
	}
}

func TestDefaultTTLApplied(t *testing.T) {
	fk := NewFakeKernel("eth0")
	e := NewEnforcer(fk, 2*time.Hour)
	e.now = func() time.Time { return fixedNow }

	in := blockInput("aa-1", "203.0.113.7")
	in.TTLSeconds = 0
	got, err := e.Enforce(in)
	if err != nil {
		t.Fatalf("Enforce: %v", err)
	}
	if want := fixedNow.Add(2 * time.Hour).UTC().Truncate(time.Second); !got.ExpiresAt.Equal(want) {
		t.Errorf("expires_at = %v, want %v (default ttl)", got.ExpiresAt, want)
	}
	if got.TTLSeconds != 7200 {
		t.Errorf("TTLSeconds = %d, want 7200", got.TTLSeconds)
	}
}

func TestTargetRefusals(t *testing.T) {
	cases := []struct {
		name   string
		kind   Kind
		ip     string
		port   int
		pid    int
		reason string
	}{
		{"loopback v4", KindXDPDrop, "127.0.0.1", 0, 0, ReasonLoopback},
		{"loopback v6", KindXDPDrop, "::1", 0, 0, ReasonLoopback},
		{"multicast v4", KindXDPDrop, "224.0.0.1", 0, 0, ReasonMulticast},
		{"multicast v6", KindXDPDrop, "ff02::1", 0, 0, ReasonMulticast},
		{"unspecified", KindXDPDrop, "0.0.0.0", 0, 0, ReasonUnspecified},
		{"link-local", KindXDPDrop, "169.254.1.1", 0, 0, ReasonLinkLocal},
		{"v4 broadcast", KindXDPDrop, "255.255.255.255", 0, 0, ReasonBroadcast},
		{"unparseable ip", KindXDPDrop, "999.999.999.999", 0, 0, ReasonUnparseableIP},
		{"missing ip", KindXDPDrop, "", 0, 0, ReasonMissingIP},
		{"port on xdp_drop", KindXDPDrop, "203.0.113.7", 4444, 0, ReasonPortNotAllowed},
		{"pid on xdp_drop", KindXDPDrop, "203.0.113.7", 0, 4242, ReasonPIDNotAllowed},
		{"bad port range", KindSocketRedirect, "203.0.113.7", 70000, 0, ReasonBadPort},
		{"ip on interdict", KindProcessInterdict, "203.0.113.7", 0, 0, ReasonIPNotAllowed},
		{"port on interdict", KindProcessInterdict, "", 4444, 4242, ReasonPortNotAllowed},
		{"missing pid", KindProcessInterdict, "", 0, 0, ReasonMissingPID},
		{"pid out of range", KindProcessInterdict, "", 0, maxPID + 1, ReasonBadPID},
		{"negative pid", KindProcessInterdict, "", 0, -1, ReasonBadPID},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			e := newTestEnforcer(t, NewFakeKernel("eth0"))
			in := Input{ActionID: "aa-x", Kind: tc.kind, IP: tc.ip, Port: tc.port, PID: tc.pid, TTLSeconds: 3600, Reason: "r", IdempotencyKey: "k"}
			_, err := e.Enforce(in)
			if err == nil {
				t.Fatalf("Enforce accepted %v/%s/%d/%d", tc.kind, tc.ip, tc.port, tc.pid)
			}
			if err.Code != ErrCodeInvalidTarget {
				t.Fatalf("error code = %s, want %s", err.Code, ErrCodeInvalidTarget)
			}
			if got, _ := err.Details["reason"].(string); got != tc.reason {
				t.Fatalf("details.reason = %q, want %q", got, tc.reason)
			}
		})
	}
}

func TestAcceptsRoutableTargets(t *testing.T) {
	e := newTestEnforcer(t, NewFakeKernel("eth0"))
	for _, ip := range []string{"203.0.113.7", "198.51.100.9", "2606:4700::1111"} {
		if _, err := e.Enforce(blockInput("aa-"+ip, ip)); err != nil {
			t.Errorf("routable target %s refused: %v", ip, err)
		}
	}
}

func TestUnknownKind(t *testing.T) {
	e := newTestEnforcer(t, NewFakeKernel("eth0"))
	in := blockInput("aa-1", "203.0.113.7")
	in.Kind = "drop_everything"
	_, err := e.Enforce(in)
	if err == nil || err.Code != ErrCodeUnsupportedKind {
		t.Fatalf("err = %v, want %s", err, ErrCodeUnsupportedKind)
	}
}

func TestRequiredFieldsRefused(t *testing.T) {
	e := newTestEnforcer(t, NewFakeKernel("eth0"))

	in := blockInput("aa-1", "203.0.113.7")
	in.ActionID = ""
	if _, err := e.Enforce(in); err == nil || err.Code != ErrCodeInvalidRequest {
		t.Errorf("empty action_id: err = %v", err)
	}
	in = blockInput("", "203.0.113.7")
	in.Reason = ""
	if _, err := e.Enforce(in); err == nil || err.Code != ErrCodeInvalidRequest {
		t.Errorf("empty reason: err = %v", err)
	}
	in = blockInput("", "203.0.113.7")
	in.IdempotencyKey = ""
	if _, err := e.Enforce(in); err == nil || err.Code != ErrCodeInvalidRequest {
		t.Errorf("empty idempotency_key: err = %v", err)
	}
}

func TestPrimitiveUnavailable(t *testing.T) {
	fk := NewFakeKernel("eth0")
	fk.Caps[KindProcessInterdict] = Capability{Supported: false, Reason: "LSM BPF not available"}
	e := newTestEnforcer(t, fk)

	in := Input{ActionID: "aa-1", Kind: KindProcessInterdict, PID: 4242, TTLSeconds: 3600, Reason: "r", IdempotencyKey: "k"}
	_, err := e.Enforce(in)
	if err == nil || err.Code != ErrCodePrimitiveUnavailable {
		t.Fatalf("err = %v, want %s", err, ErrCodePrimitiveUnavailable)
	}
	if _, ok := err.Details["kind"]; !ok {
		t.Errorf("details should name the kind: %v", err.Details)
	}
	// Nothing reached the kernel for an unsupported primitive.
	if a, u, _ := fk.Counts(KindProcessInterdict); a != 0 || u != 0 {
		t.Errorf("unsupported primitive touched the kernel: attach=%d update=%d", a, u)
	}
}

func TestKernelErrorsFailClosed(t *testing.T) {
	fk := NewFakeKernel("eth0")
	fk.AttachErr[KindXDPDrop] = errors.New("bpf prog load: operation not permitted")
	e := newTestEnforcer(t, fk)

	_, err := e.Enforce(blockInput("aa-1", "203.0.113.7"))
	if err == nil || err.Code != ErrCodeKernelError {
		t.Fatalf("attach failure: err = %v, want %s", err, ErrCodeKernelError)
	}

	fk2 := NewFakeKernel("eth0")
	fk2.UpdateErr[KindXDPDrop] = errors.New("map update: no space left on device")
	e2 := newTestEnforcer(t, fk2)
	_, err = e2.Enforce(blockInput("aa-2", "203.0.113.7"))
	if err == nil || err.Code != ErrCodeKernelError {
		t.Fatalf("update failure: err = %v, want %s", err, ErrCodeKernelError)
	}
	// A failed enforcement must not be recorded as enforceable-or-replayed.
	if _, err := e2.Enforce(blockInput("aa-2", "203.0.113.7")); err == nil {
		t.Errorf("a failed enforcement must not become a replayable record")
	}
}

func TestReleaseRemovesKernelStateIdempotently(t *testing.T) {
	fk := NewFakeKernel("eth0")
	e := newTestEnforcer(t, fk)

	if _, err := e.Enforce(blockInput("aa-1", "203.0.113.7")); err != nil {
		t.Fatalf("Enforce: %v", err)
	}
	if _, err := fk.Stats(KindXDPDrop); err != nil {
		t.Fatalf("Stats: %v", err)
	}
	stats, _ := fk.Stats(KindXDPDrop)
	if stats.Occupancy != 1 {
		t.Fatalf("occupancy = %d, want 1 after enforcement", stats.Occupancy)
	}

	out, err := e.Release("aa-1")
	if err != nil {
		t.Fatalf("Release: %v", err)
	}
	if out.State != StateReleased {
		t.Errorf("state = %q, want %q", out.State, StateReleased)
	}
	stats, _ = fk.Stats(KindXDPDrop)
	if stats.Occupancy != 0 {
		t.Errorf("occupancy = %d, want 0 after release", stats.Occupancy)
	}

	again, err := e.Release("aa-1")
	if err != nil {
		t.Fatalf("second Release: %v", err)
	}
	if again.State != StateReleased || again.ReleasedAt.IsZero() {
		t.Errorf("second release: state=%q released_at=%v, want released with a stamped time", again.State, again.ReleasedAt)
	}

	if _, err := e.Release("aa-unknown"); err == nil || err.Code != ErrCodeUnknownAction {
		t.Errorf("unknown release: err = %v, want %s", err, ErrCodeUnknownAction)
	}
}

func TestReleasedActionStaysReleasedOnReplay(t *testing.T) {
	fk := NewFakeKernel("eth0")
	e := newTestEnforcer(t, fk)

	if _, err := e.Enforce(blockInput("aa-1", "203.0.113.7")); err != nil {
		t.Fatalf("Enforce: %v", err)
	}
	if _, err := e.Release("aa-1"); err != nil {
		t.Fatalf("Release: %v", err)
	}
	got, err := e.Enforce(blockInput("aa-1", "203.0.113.7"))
	if err != nil {
		t.Fatalf("replay after release: %v", err)
	}
	if got.State != StateReleased {
		t.Errorf("replay of a released action: state = %q, want %q — re-enforcing under a released id would silently re-open containment", got.State, StateReleased)
	}
	if _, u, _ := fk.Counts(KindXDPDrop); u != 1 {
		t.Errorf("replay after release re-updated the map: updates = %d, want 1", u)
	}
}

func TestConcurrentEnforcementDistinctIDs(t *testing.T) {
	fk := NewFakeKernel("eth0")
	e := newTestEnforcer(t, fk)

	var wg sync.WaitGroup
	errs := make(chan *Error, 16)
	for i := 0; i < 16; i++ {
		wg.Add(1)
		go func(n int) {
			defer wg.Done()
			ip := "203.0.113." + string(rune('0'+n%10)) + ""
			_, enforcerr := e.Enforce(blockInput("aa-concurrent-"+ip, ip))
			if enforcerr != nil {
				errs <- enforcerr
			}
		}(i)
	}
	wg.Wait()
	close(errs)
	for err := range errs {
		t.Errorf("concurrent Enforce failed: %v", err)
	}
	stats, _ := fk.Stats(KindXDPDrop)
	if stats.Occupancy != 10 {
		t.Errorf("occupancy = %d, want 10 (ten distinct targets)", stats.Occupancy)
	}
}

func TestSocketRedirectEvidenceAndInterdict(t *testing.T) {
	fk := NewFakeKernel("eth0")
	e := newTestEnforcer(t, fk)

	in := Input{ActionID: "aa-r", Kind: KindSocketRedirect, IP: "203.0.113.7", Port: 4444, TTLSeconds: 3600, Reason: "r", IdempotencyKey: "k"}
	got, err := e.Enforce(in)
	if err != nil {
		t.Fatalf("socket redirect: %v", err)
	}
	if got.Evidence.AttachPoint != "eth0/sockmap" {
		t.Errorf("attach_point = %q, want eth0/sockmap", got.Evidence.AttachPoint)
	}
	if !strings.HasSuffix(got.Evidence.Map, "/socket_redir_v1") {
		t.Errorf("map = %q, want socket_redir_v1", got.Evidence.Map)
	}

	in2 := Input{ActionID: "aa-i", Kind: KindProcessInterdict, PID: 4242, TTLSeconds: 3600, Reason: "r", IdempotencyKey: "k"}
	got2, err := e.Enforce(in2)
	if err != nil {
		t.Fatalf("process interdict: %v", err)
	}
	if got2.Evidence.AttachPoint != "cgroup/vigil" {
		t.Errorf("attach_point = %q, want cgroup/vigil", got2.Evidence.AttachPoint)
	}
}

func TestListAndGet(t *testing.T) {
	e := newTestEnforcer(t, NewFakeKernel("eth0"))
	if got := e.List(); len(got) != 0 {
		t.Errorf("fresh enforcer List = %d records, want 0", len(got))
	}
	if _, err := e.Enforce(blockInput("aa-1", "203.0.113.7")); err != nil {
		t.Fatalf("Enforce: %v", err)
	}
	if _, err := e.Enforce(blockInput("aa-2", "198.51.100.9")); err != nil {
		t.Fatalf("Enforce: %v", err)
	}
	if got := e.List(); len(got) != 2 || got[0].ActionID != "aa-1" || got[1].ActionID != "aa-2" {
		t.Errorf("List = %+v, want aa-1 then aa-2 in insertion order", got)
	}
	if got, ok := e.Get("aa-2"); !ok || got.ActionID != "aa-2" {
		t.Errorf("Get(aa-2) = (%+v, %v)", got, ok)
	}
	if _, ok := e.Get("aa-nope"); ok {
		t.Errorf("Get of unknown id must not be ok")
	}
}
