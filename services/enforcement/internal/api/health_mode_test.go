package api

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/jvlatacc/vigil/services/enforcement/internal/enforce"
)

// signalKernel fakes a host whose process-interdict degraded to the
// signal fallback: supported, but through a degraded non-BPF mechanism.
type signalKernel struct {
	*enforce.FakeKernel
}

func (s *signalKernel) Capability(k enforce.Kind) enforce.Capability {
	if k == enforce.KindProcessInterdict {
		return enforce.Capability{Supported: true, Degraded: true, Reason: "unit-test: LSM unavailable"}
	}
	return s.FakeKernel.Capability(k)
}

// Mode implements enforce.ModeReporter — the real loader does; a kernel
// that does not must leave the mode out of health output entirely.
func (s *signalKernel) Mode(k enforce.Kind) string {
	if k == enforce.KindProcessInterdict {
		return "signal"
	}
	return "bpf"
}

func newModeTestServer(t *testing.T, kernel enforce.Kernel) *httptest.Server {
	t.Helper()
	srv, err := New(testToken, enforce.NewEnforcer(kernel, enforce.TTLFloor*10), "faked")
	if err != nil {
		t.Fatalf("New: %v", err)
	}
	ts := httptest.NewServer(srv.Handler())
	t.Cleanup(ts.Close)
	return ts
}

// TestHealthzReportsSignalFallbackMode pins the degraded-mode reporting
// contract: the fallback mechanism is visible (mode "signal"), the
// primitive stays supported, and the overall status is degraded — a
// signal suspension is not the primary enforcement and must not read as
// a fully healthy daemon.
func TestHealthzReportsSignalFallbackMode(t *testing.T) {
	ts := newModeTestServer(t, &signalKernel{enforce.NewFakeKernel("eth0")})

	res := authedJSON(t, "GET", ts.URL+"/healthz", "", nil)
	if res.StatusCode != http.StatusOK {
		t.Fatalf("healthz: status = %d, want 200", res.StatusCode)
	}
	var h struct {
		Status     string `json:"status"`
		Primitives map[string]struct {
			Supported bool   `json:"supported"`
			Reason    string `json:"reason"`
			Mode      string `json:"mode"`
		} `json:"primitives"`
	}
	if err := json.NewDecoder(res.Body).Decode(&h); err != nil {
		t.Fatalf("decoding healthz: %v", err)
	}
	if h.Status != "degraded" {
		t.Errorf("status = %q, want degraded (a signal fallback is a degraded mechanism)", h.Status)
	}
	p := h.Primitives["process_interdict"]
	if !p.Supported || p.Mode != "signal" || p.Reason == "" {
		t.Errorf("process_interdict = %+v, want supported=true, mode=signal, with a reason", p)
	}
	xdp := h.Primitives["xdp_drop"]
	if !xdp.Supported || xdp.Mode != "bpf" {
		t.Errorf("xdp_drop = %+v, want supported=true, mode=bpf", xdp)
	}
}

// TestHealthzOmitsModeWithoutReporter pins the other edge: a kernel that
// does not implement ModeReporter (e.g. the plain faked kernel) leaves
// the optional field out entirely.
func TestHealthzOmitsModeWithoutReporter(t *testing.T) {
	ts := newModeTestServer(t, enforce.NewFakeKernel("eth0"))

	res := authedJSON(t, "GET", ts.URL+"/healthz", "", nil)
	var body map[string]any
	if err := json.NewDecoder(res.Body).Decode(&body); err != nil {
		t.Fatalf("decoding healthz: %v", err)
	}
	prims, _ := body["primitives"].(map[string]any)
	xdp, _ := prims["xdp_drop"].(map[string]any)
	if xdp == nil {
		t.Fatalf("healthz has no xdp_drop primitive: %v", body)
	}
	if _, present := xdp["mode"]; present {
		t.Errorf("mode = %v, want the field omitted when the kernel has no ModeReporter", xdp["mode"])
	}
}
