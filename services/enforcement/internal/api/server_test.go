package api

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/jvlatacc/vigil/services/enforcement/internal/enforce"
)

func newTestServer(t *testing.T, fk *enforce.FakeKernel) *httptest.Server {
	t.Helper()
	if fk == nil {
		fk = enforce.NewFakeKernel("eth0")
	}
	srv, err := New(testToken, enforce.NewEnforcer(fk, enforce.TTLFloor*10), "faked")
	if err != nil {
		t.Fatalf("New: %v", err)
	}
	ts := httptest.NewServer(srv.Handler())
	t.Cleanup(ts.Close)
	return ts
}

const testToken = "unit-test-token"

func authedJSON(t *testing.T, method, url, token string, body any) *http.Response {
	t.Helper()
	var buf bytes.Buffer
	if body != nil {
		if err := json.NewEncoder(&buf).Encode(body); err != nil {
			t.Fatalf("encoding body: %v", err)
		}
	}
	req, err := http.NewRequest(method, url, &buf)
	if err != nil {
		t.Fatalf("building request: %v", err)
	}
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}
	res, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("%s %s: %v", method, url, err)
	}
	t.Cleanup(func() { res.Body.Close() })
	return res
}

func decodeError(t *testing.T, res *http.Response) errorShape {
	t.Helper()
	var e errorShape
	if err := json.NewDecoder(res.Body).Decode(&e); err != nil {
		t.Fatalf("decoding error body: %v", err)
	}
	return e
}

func TestAuthRejectedWithoutOrWrongToken(t *testing.T) {
	ts := newTestServer(t, nil)
	body := map[string]any{"action_id": "aa-1", "kind": "xdp_drop"}

	res := authedJSON(t, "POST", ts.URL+"/v1/actions", "", body)
	if res.StatusCode != http.StatusUnauthorized {
		t.Errorf("no token: status = %d, want 401", res.StatusCode)
	}
	if e := decodeError(t, res); e.Error != "unauthorized" {
		t.Errorf("no token: error = %q, want unauthorized", e.Error)
	}

	res = authedJSON(t, "POST", ts.URL+"/v1/actions", "wrong-token", body)
	if res.StatusCode != http.StatusUnauthorized {
		t.Errorf("wrong token: status = %d, want 401", res.StatusCode)
	}
	if e := decodeError(t, res); e.Error != "unauthorized" {
		t.Errorf("wrong token: error = %q, want unauthorized", e.Error)
	}
}

func TestAuthSchemeMustBeBearer(t *testing.T) {
	ts := newTestServer(t, nil)

	req, err := http.NewRequest("POST", ts.URL+"/v1/actions", strings.NewReader("{}"))
	if err != nil {
		t.Fatalf("building request: %v", err)
	}
	req.Header.Set("Authorization", "Basic "+testToken)
	res, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("request: %v", err)
	}
	defer res.Body.Close()
	if res.StatusCode != http.StatusUnauthorized {
		t.Errorf("non-bearer auth: status = %d, want 401", res.StatusCode)
	}
}

func TestUnknownRouteAndMethod(t *testing.T) {
	ts := newTestServer(t, nil)

	res := authedJSON(t, "GET", ts.URL+"/v1/nope", testToken, nil)
	if res.StatusCode != http.StatusNotFound {
		t.Errorf("unknown route: status = %d, want 404", res.StatusCode)
	}
	if e := decodeError(t, res); e.Error != "unknown_action" {
		t.Errorf("unknown route: error = %q, want unknown_action", e.Error)
	}

	res = authedJSON(t, "PUT", ts.URL+"/v1/actions", testToken, map[string]any{})
	if res.StatusCode != http.StatusMethodNotAllowed {
		t.Errorf("wrong method: status = %d, want 405", res.StatusCode)
	}
}

func TestMalformedBodiesRefused(t *testing.T) {
	ts := newTestServer(t, nil)

	// Invalid JSON.
	req, err := http.NewRequest("POST", ts.URL+"/v1/actions", strings.NewReader("{not json"))
	if err != nil {
		t.Fatalf("building request: %v", err)
	}
	req.Header.Set("Authorization", "Bearer "+testToken)
	req.Header.Set("Content-Type", "application/json")
	res, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("request: %v", err)
	}
	defer res.Body.Close()
	if res.StatusCode != http.StatusBadRequest {
		t.Errorf("invalid json: status = %d, want 400", res.StatusCode)
	}
	if e := decodeError(t, res); e.Error != "invalid_request" {
		t.Errorf("invalid json: error = %q, want invalid_request", e.Error)
	}

	// Unknown fields are refused — the request contract is closed.
	res = authedJSON(t, "POST", ts.URL+"/v1/actions", testToken, map[string]any{
		"action_id": "aa-1", "kind": "xdp_drop", "surprise": true,
	})
	if res.StatusCode != http.StatusBadRequest {
		t.Errorf("unknown field: status = %d, want 400", res.StatusCode)
	}

	// Bodies beyond the size cap are refused without being read whole.
	huge := strings.Repeat("x", MaxRequestBytes+1)
	req, err = http.NewRequest("POST", ts.URL+"/v1/actions", strings.NewReader(huge))
	if err != nil {
		t.Fatalf("building request: %v", err)
	}
	req.Header.Set("Authorization", "Bearer "+testToken)
	res, err = http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("request: %v", err)
	}
	defer res.Body.Close()
	if res.StatusCode != http.StatusBadRequest {
		t.Errorf("oversized body: status = %d, want 400", res.StatusCode)
	}
}

func TestHealthzShape(t *testing.T) {
	ts := newTestServer(t, nil)

	res := authedJSON(t, "GET", ts.URL+"/healthz", "", nil)
	if res.StatusCode != http.StatusOK {
		t.Fatalf("healthz: status = %d, want 200", res.StatusCode)
	}
	var h struct {
		Status        string `json:"status"`
		UptimeSeconds int    `json:"uptime_seconds"`
		KernelFaked   string `json:"kernel_faked"`
		Primitives    map[string]struct {
			Supported bool   `json:"supported"`
			Reason    string `json:"reason"`
		} `json:"primitives"`
	}
	if err := json.NewDecoder(res.Body).Decode(&h); err != nil {
		t.Fatalf("decoding healthz: %v", err)
	}
	if h.Status != "ok" {
		t.Errorf("status = %q, want ok", h.Status)
	}
	if h.KernelFaked == "" {
		t.Errorf("kernel_faked must be non-empty while running the faked kernel — a faked kernel must never be mistaken for enforcement")
	}
	for _, kind := range []string{"xdp_drop", "socket_redirect", "process_interdict"} {
		p, ok := h.Primitives[kind]
		if !ok {
			t.Errorf("healthz missing primitive %q", kind)
			continue
		}
		if !p.Supported {
			t.Errorf("primitive %q not supported on the fake kernel: %s", kind, p.Reason)
		}
	}
}

// A real loader reports an empty kernel_faked label — faked enforcement is
// the only distinguishable case (contract).
func TestHealthzRealLoaderReportsEmptyFakedLabel(t *testing.T) {
	srv, err := New(testToken, enforce.NewEnforcer(enforce.NewFakeKernel("eth0"), enforce.TTLFloor*10), "")
	if err != nil {
		t.Fatalf("New: %v", err)
	}
	ts := httptest.NewServer(srv.Handler())
	defer ts.Close()

	res := authedJSON(t, "GET", ts.URL+"/healthz", "", nil)
	if res.StatusCode != http.StatusOK {
		t.Fatalf("healthz: status = %d, want 200", res.StatusCode)
	}
	var h struct {
		Status      string `json:"status"`
		KernelFaked string `json:"kernel_faked"`
	}
	if err := json.NewDecoder(res.Body).Decode(&h); err != nil {
		t.Fatalf("decoding healthz: %v", err)
	}
	if h.Status != "ok" || h.KernelFaked != "" {
		t.Errorf("healthz = {status: %q, kernel_faked: %q}, want {ok, \"\"}", h.Status, h.KernelFaked)
	}
}

func TestHealthzReportsDegraded(t *testing.T) {
	fk := enforce.NewFakeKernel("eth0")
	fk.Caps[enforce.KindProcessInterdict] = enforce.Capability{Supported: false, Reason: "LSM BPF not available"}
	ts := newTestServer(t, fk)

	res := authedJSON(t, "GET", ts.URL+"/healthz", "", nil)
	var h struct {
		Status     string `json:"status"`
		Primitives map[string]struct {
			Supported bool   `json:"supported"`
			Reason    string `json:"reason"`
		} `json:"primitives"`
	}
	if err := json.NewDecoder(res.Body).Decode(&h); err != nil {
		t.Fatalf("decoding healthz: %v", err)
	}
	if h.Status != "degraded" {
		t.Errorf("status = %q, want degraded (spec: degrade per primitive, not whole)", h.Status)
	}
	p := h.Primitives["process_interdict"]
	if p.Supported || p.Reason == "" {
		t.Errorf("degraded primitive must report supported=false with a reason: %+v", p)
	}
}

func TestMetricsPrometheusText(t *testing.T) {
	fk := enforce.NewFakeKernel("eth0")
	ts := newTestServer(t, fk)

	in := map[string]any{
		"action_id": "aa-1", "kind": "xdp_drop", "target": map[string]any{"ip": "203.0.113.7"},
		"ttl_seconds": 3600, "reason": "r", "idempotency_key": "k",
	}
	if res := authedJSON(t, "POST", ts.URL+"/v1/actions", testToken, in); res.StatusCode != http.StatusCreated {
		t.Fatalf("enforce: status = %d", res.StatusCode)
	}
	fk.Bump(enforce.KindXDPDrop, "dropped_packets", 7)

	res := authedJSON(t, "GET", ts.URL+"/metrics", "", nil)
	if res.StatusCode != http.StatusOK {
		t.Fatalf("metrics: status = %d", res.StatusCode)
	}
	var buf bytes.Buffer
	if _, err := buf.ReadFrom(res.Body); err != nil {
		t.Fatalf("reading metrics: %v", err)
	}
	metrics := buf.String()
	for _, want := range []string{
		`vigil_enforcement_dropped_packets{kind="xdp_drop"} 7`,
		`vigil_enforcement_map_entries{kind="xdp_drop"} 1`,
		"vigil_enforcement_actions_enforced 1",
		"vigil_enforcement_actions_released 0",
		"# HELP ", "# TYPE ",
	} {
		if !strings.Contains(metrics, want) {
			t.Errorf("metrics missing %q in:\n%s", want, metrics)
		}
	}
	// Each metric name must define exactly one HELP/TYPE pair — a repeated
	// definition is a Prometheus scrape error.
	if got := strings.Count(metrics, "# HELP vigil_enforcement_map_entries "); got != 1 {
		t.Errorf("map_entries HELP defined %d times, want 1 in:\n%s", got, metrics)
	}
	if got := strings.Count(metrics, "# TYPE vigil_enforcement_map_entries "); got != 1 {
		t.Errorf("map_entries TYPE defined %d times, want 1", got)
	}
}

func TestEvidenceEchoesActionID(t *testing.T) {
	ts := newTestServer(t, nil)

	in := map[string]any{
		"action_id": "aa-echo-me", "kind": "xdp_drop", "target": map[string]any{"ip": "203.0.113.7"},
		"ttl_seconds": 3600, "reason": "r", "idempotency_key": "k",
	}
	res := authedJSON(t, "POST", ts.URL+"/v1/actions", testToken, in)
	var out struct {
		ActionID string `json:"action_id"`
		State    string `json:"state"`
	}
	if err := json.NewDecoder(res.Body).Decode(&out); err != nil {
		t.Fatalf("decoding: %v", err)
	}
	if out.ActionID != "aa-echo-me" {
		t.Errorf("response action_id = %q, want aa-echo-me — the executor keys mark_executed on this", out.ActionID)
	}
	if out.State != "enforced" {
		t.Errorf("state = %q, want enforced", out.State)
	}
}

func TestActionRoutesRoundTrip(t *testing.T) {
	ts := newTestServer(t, nil)

	in := map[string]any{
		"action_id": "aa-list", "kind": "xdp_drop", "target": map[string]any{"ip": "203.0.113.7"},
		"ttl_seconds": 3600, "reason": "r", "idempotency_key": "k",
	}
	if res := authedJSON(t, "POST", ts.URL+"/v1/actions", testToken, in); res.StatusCode != http.StatusCreated {
		t.Fatalf("enforce: status = %d", res.StatusCode)
	}

	res := authedJSON(t, "GET", ts.URL+"/v1/actions/aa-list", testToken, nil)
	if res.StatusCode != http.StatusOK {
		t.Errorf("get: status = %d, want 200", res.StatusCode)
	}
	res = authedJSON(t, "GET", ts.URL+"/v1/actions/aa-missing", testToken, nil)
	if res.StatusCode != http.StatusNotFound {
		t.Errorf("get unknown: status = %d, want 404", res.StatusCode)
	}
	if e := decodeError(t, res); e.Error != "unknown_action" {
		t.Errorf("get unknown: error = %q, want unknown_action (the contract's closed vocabulary has no action_not_found)", e.Error)
	}

	res = authedJSON(t, "GET", ts.URL+"/v1/actions", testToken, nil)
	var list struct {
		Actions []map[string]any `json:"actions"`
	}
	if err := json.NewDecoder(res.Body).Decode(&list); err != nil {
		t.Fatalf("decoding list: %v", err)
	}
	if len(list.Actions) != 1 || list.Actions[0]["action_id"] != "aa-list" {
		t.Errorf("list = %v, want one aa-list row", list.Actions)
	}

	res = authedJSON(t, "DELETE", ts.URL+"/v1/actions/aa-list", testToken, nil)
	if res.StatusCode != http.StatusOK {
		t.Errorf("release: status = %d, want 200", res.StatusCode)
	}
}
