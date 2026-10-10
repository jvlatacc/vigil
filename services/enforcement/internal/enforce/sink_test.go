package enforce

import (
	"net"
	"testing"
)

// SetSink records the connection and refuses when the primitive was
// degraded — the executor-visible behaviour the real loader mirrors.
func TestFakeKernelSinkWiring(t *testing.T) {
	fk := NewFakeKernel("eth0")

	pipeA, _ := net.Pipe()
	defer pipeA.Close()
	if err := fk.SetSink(pipeA); err != nil {
		t.Fatalf("SetSink: %v", err)
	}
	if fk.SinkConn() != net.Conn(pipeA) {
		t.Fatal("SetSink did not record the connection")
	}

	fk.MarkDegraded(KindSocketRedirect, "sink unreachable: test")
	pipeB, _ := net.Pipe()
	defer pipeB.Close()
	if err := fk.SetSink(pipeB); err == nil {
		t.Error("SetSink must refuse after the primitive was degraded")
	}
	cap := fk.Capability(KindSocketRedirect)
	if cap.Supported || cap.Reason != "sink unreachable: test" {
		t.Errorf("capability = %+v, want degraded with the marked reason", cap)
	}
}

// A degraded primitive stops the engine's dispatch: no MapUpdate, no
// evidence, primitive_unavailable — a hollow success is worse than a
// refusal.
func TestMarkDegradedStopsDispatch(t *testing.T) {
	fk := NewFakeKernel("eth0")
	e := newTestEnforcer(t, fk)

	before, err := e.Enforce(Input{
		ActionID: "aa-redirect", Kind: KindSocketRedirect, IP: "203.0.113.8",
		Port: 4444, TTLSeconds: 60, Reason: "tarpit", IdempotencyKey: "socket_redirect:203.0.113.8:4444",
	})
	if err != nil {
		t.Fatalf("Enforce before degrade: %v", err)
	}
	if before.State != StateEnforced {
		t.Errorf("state = %q, want %q", before.State, StateEnforced)
	}

	fk.MarkDegraded(KindSocketRedirect, "sink unreachable: connection refused")
	_, enforcerr := e.Enforce(Input{
		ActionID: "aa-redirect-2", Kind: KindSocketRedirect, IP: "203.0.113.9",
		Port: 4444, TTLSeconds: 60, Reason: "tarpit", IdempotencyKey: "socket_redirect:203.0.113.9:4444",
	})
	if enforcerr == nil {
		t.Fatal("dispatch after MarkDegraded must fail, not enforce")
	}
	if enforcerr.Code != ErrCodePrimitiveUnavailable {
		t.Errorf("error code = %q, want %q", enforcerr.Code, ErrCodePrimitiveUnavailable)
	}
}
