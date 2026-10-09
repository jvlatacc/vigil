package api

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/jvlatacc/vigil/services/enforcement/internal/enforce"
)

// contractToken is the shared secret the vector runner authenticates with.
const contractToken = "vector-runner-token"

// vectorFile mirrors contract/vector.schema.json. The structure check in
// loadVector is that schema's required-fields subset in Go — the module
// stays stdlib-only; the schema file is the normative document.
type vectorFile struct {
	ID          string       `json:"id"`
	Description string       `json:"description"`
	Kernel      kernelSetup  `json:"kernel"`
	Steps       []vectorStep `json:"steps"`
}

type kernelSetup struct {
	UnsupportedKinds []string `json:"unsupported_kinds"`
}

type vectorStep struct {
	Name    string      `json:"name"`
	Request stepRequest `json:"request"`
	Expect  stepExpect  `json:"expect"`
}

type stepRequest struct {
	Method string         `json:"method"`
	Path   string         `json:"path"`
	Body   map[string]any `json:"body"`
	Auth   *bool          `json:"auth"`
}

type stepExpect struct {
	Status                 int    `json:"status"`
	State                  string `json:"state"`
	Error                  string `json:"error"`
	ErrorReason            string `json:"error_reason"`
	Replayed               *bool  `json:"replayed"`
	EvidenceEchoesActionID bool   `json:"evidence_echoes_action_id"`
}

// TestContractVectors executes every contract vector against the real HTTP
// stack on a fresh FakeKernel. The vectors are the spec's API contract in
// executable form: a vector or schema that looks wrong is a contract change,
// made in its own PR (medic convention).
func TestContractVectors(t *testing.T) {
	vectors, err := filepath.Glob(filepath.Join("..", "..", "contract", "vectors", "v*.json"))
	if err != nil || len(vectors) == 0 {
		t.Fatalf("no contract vectors found under contract/vectors/: %v", err)
	}
	for _, path := range vectors {
		vec := loadVector(t, path)
		t.Run(vec.ID, func(t *testing.T) {
			// Each vector gets a fresh daemon: vectors are independent
			// stories about contract behaviour, not a shared sequence.
			fk := enforce.NewFakeKernel("eth0")
			for _, kind := range vec.Kernel.UnsupportedKinds {
				fk.Caps[enforce.Kind(kind)] = enforce.Capability{
					Supported: false, Reason: "capability probe refused (vector override)",
				}
			}
			srv, err := New(contractToken, enforce.NewEnforcer(fk, enforce.TTLFloor*10), "faked")
			if err != nil {
				t.Fatalf("building server: %v", err)
			}
			ts := httptest.NewServer(srv.Handler())
			defer ts.Close()

			for i, step := range vec.Steps {
				res := doStep(t, ts, step)
				if res.status != step.Expect.Status {
					t.Errorf("step %d (%s): status = %d, want %d (body: %s)", i, step.Name, res.status, step.Expect.Status, res.body)
				}
				if res.status/100 == 2 {
					validateSuccessShape(t, vec.ID, i, step.Name, res.body)
				}
				if step.Expect.State != "" && res.success.State != step.Expect.State {
					t.Errorf("step %d (%s): state = %q, want %q", i, step.Name, res.success.State, step.Expect.State)
				}
				if step.Expect.Error != "" && res.errBody.Error != step.Expect.Error {
					t.Errorf("step %d (%s): error = %q, want %q", i, step.Name, res.errBody.Error, step.Expect.Error)
				}
				if step.Expect.ErrorReason != "" {
					got, _ := res.errBody.Details["reason"].(string)
					if got != step.Expect.ErrorReason {
						t.Errorf("step %d (%s): error details.reason = %q, want %q", i, step.Name, got, step.Expect.ErrorReason)
					}
				}
				if step.Expect.Replayed != nil && res.success.Replayed != *step.Expect.Replayed {
					t.Errorf("step %d (%s): replayed = %v, want %v", i, step.Name, res.success.Replayed, *step.Expect.Replayed)
				}
				// Evidence echoes the caller's action_id: the field the
				// executor keys mark_executed on.
				if step.Expect.EvidenceEchoesActionID {
					want, _ := step.Request.Body["action_id"].(string)
					if res.success.ActionID != want {
						t.Errorf("step %d (%s): response action_id = %q, want %q", i, step.Name, res.success.ActionID, want)
					}
				}
			}
		})
	}
}

// loadVector reads and structurally validates one vector file — the required
// subset of contract/vector.schema.json.
func loadVector(t *testing.T, path string) vectorFile {
	t.Helper()
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("reading %s: %v", path, err)
	}
	var vec vectorFile
	if err := json.Unmarshal(raw, &vec); err != nil {
		t.Fatalf("%s: %v", path, err)
	}
	if vec.ID == "" || vec.Description == "" || len(vec.Steps) == 0 {
		t.Fatalf("%s: vector requires id, description and at least one step", path)
	}
	for i, step := range vec.Steps {
		if step.Name == "" {
			t.Fatalf("%s: step %d has no name", path, i)
		}
		if step.Request.Method == "" || step.Request.Path == "" {
			t.Fatalf("%s: step %d (%s) requires method and path", path, i, step.Name)
		}
		if step.Expect.Status == 0 {
			t.Fatalf("%s: step %d (%s) requires expect.status", path, i, step.Name)
		}
	}
	return vec
}

// doStep issues one vector step and captures status plus decoded bodies.
func doStep(t *testing.T, ts *httptest.Server, step vectorStep) stepResult {
	t.Helper()
	var buf bytes.Buffer
	if step.Request.Body != nil {
		if err := json.NewEncoder(&buf).Encode(step.Request.Body); err != nil {
			t.Fatalf("encoding %s body: %v", step.Name, err)
		}
	}
	req, err := http.NewRequest(step.Request.Method, ts.URL+step.Request.Path, &buf)
	if err != nil {
		t.Fatalf("building %s: %v", step.Name, err)
	}
	if step.Request.Body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	if step.Request.Auth == nil || *step.Request.Auth {
		req.Header.Set("Authorization", "Bearer "+contractToken)
	}

	res, err := ts.Client().Do(req)
	if err != nil {
		t.Fatalf("%s: %v", step.Name, err)
	}
	defer res.Body.Close()

	var out stepResult
	out.status = res.StatusCode
	raw := new(bytes.Buffer)
	if _, err := raw.ReadFrom(res.Body); err != nil {
		t.Fatalf("%s: reading body: %v", step.Name, err)
	}
	out.body = raw.String()
	if out.status/100 == 2 {
		if err := json.Unmarshal(raw.Bytes(), &out.success); err != nil {
			t.Fatalf("%s: success body is not the contract shape: %v", step.Name, err)
		}
	} else {
		if err := json.Unmarshal(raw.Bytes(), &out.errBody); err != nil {
			t.Fatalf("%s: error body is not the contract shape: %v", step.Name, err)
		}
	}
	return out
}

// successShape mirrors action-response.schema.json's required keys.
type successShape struct {
	ActionID string `json:"action_id"`
	State    string `json:"state"`
	Evidence struct {
		AttachPoint string            `json:"attach_point"`
		Map         string            `json:"map"`
		MapSlot     int               `json:"map_slot"`
		Counters    map[string]uint64 `json:"counters"`
	} `json:"evidence"`
	ExpiresAt string `json:"expires_at"`
	Replayed  bool   `json:"replayed"`
}

// errorShape mirrors error-response.schema.json's required keys.
type errorShape struct {
	Error   string         `json:"error"`
	Message string         `json:"message"`
	Details map[string]any `json:"details"`
}

type stepResult struct {
	status  int
	body    string
	success successShape
	errBody errorShape
}

// validateSuccessShape checks a 2xx reply against the action-response
// contract's requirements.
func validateSuccessShape(t *testing.T, vecID string, i int, name, body string) {
	t.Helper()
	var m map[string]json.RawMessage
	if err := json.Unmarshal([]byte(body), &m); err != nil {
		t.Fatalf("vector %s step %d (%s): invalid JSON: %v", vecID, i, name, err)
	}
	for _, key := range []string{"action_id", "state", "evidence", "expires_at", "replayed"} {
		if _, ok := m[key]; !ok {
			t.Errorf("vector %s step %d (%s): success reply missing required key %q", vecID, i, name, key)
		}
	}
	var ev struct {
		AttachPoint string         `json:"attach_point"`
		Map         string         `json:"map"`
		MapSlot     *int           `json:"map_slot"`
		Counters    map[string]any `json:"counters"`
	}
	if raw, ok := m["evidence"]; ok {
		if err := json.Unmarshal(raw, &ev); err != nil {
			t.Fatalf("vector %s step %d (%s): evidence is not the contract shape: %v", vecID, i, name, err)
		}
		if ev.AttachPoint == "" {
			t.Errorf("vector %s step %d (%s): evidence.attach_point is empty", vecID, i, name)
		}
		if !strings.HasPrefix(ev.Map, "/sys/fs/bpf/vigil/") {
			t.Errorf("vector %s step %d (%s): evidence.map = %q, want under /sys/fs/bpf/vigil/", vecID, i, name, ev.Map)
		}
		if ev.MapSlot == nil {
			t.Errorf("vector %s step %d (%s): evidence.map_slot missing", vecID, i, name)
		}
		if ev.Counters == nil {
			t.Errorf("vector %s step %d (%s): evidence.counters missing — evidence without counters is a faked success", vecID, i, name)
		}
	}
	if raw, ok := m["expires_at"]; ok {
		var s string
		_ = json.Unmarshal(raw, &s)
		if !strings.HasSuffix(s, "Z") {
			t.Errorf("vector %s step %d (%s): expires_at = %q, want RFC 3339 UTC", vecID, i, name, s)
		}
	}
}
