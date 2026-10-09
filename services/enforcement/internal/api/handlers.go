package api

import (
	"encoding/json"
	"net/http"

	"github.com/jvlatacc/vigil/services/enforcement/internal/enforce"
)

// statusFor maps engine error codes onto HTTP statuses. The mapping is the
// contract's — the Python executor will branch on error codes, not status,
// but a 4xx/5xx split that matches semantics keeps proxies honest.
func statusFor(code string) int {
	switch code {
	case enforce.ErrCodeUnauthorized:
		return http.StatusUnauthorized
	case enforce.ErrCodeInvalidRequest, enforce.ErrCodeInvalidTarget, enforce.ErrCodeTTLBelowFloor,
		enforce.ErrCodeUnsupportedKind, enforce.ErrCodeActionIDConflict:
		return http.StatusUnprocessableEntity
	case enforce.ErrCodeUnknownAction:
		return http.StatusNotFound
	case enforce.ErrCodePrimitiveUnavailable, enforce.ErrCodeKernelError:
		// The daemon's own state (capability probe, kernel op) failed — 503
		// tells the executor this is retriable, not a bad request.
		return http.StatusServiceUnavailable
	}
	return http.StatusInternalServerError
}

// errorBody is the wire form of every error reply.
type errorBody struct {
	Error   string         `json:"error"`
	Message string         `json:"message"`
	Details map[string]any `json:"details,omitempty"`
}

func writeError(w http.ResponseWriter, status int, code, message string, details map[string]any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(errorBody{Error: code, Message: message, Details: details})
}

// writeErr serialises an engine *Error with its mapped status.
func writeErr(w http.ResponseWriter, e *enforce.Error) {
	writeError(w, statusFor(e.Code), e.Code, e.Message, e.Details)
}

// handleEnforce implements POST /v1/actions. Success is 201 for a fresh
// enforcement and 200 for a replayed one — the body is identical either way.
func (s *Server) handleEnforce(w http.ResponseWriter, r *http.Request) {
	req, err := decode[enforceRequest](w, r)
	if err != nil {
		return // decode already wrote the 400
	}
	action, enforcerr := s.enf.Enforce(req.toInput())
	if enforcerr != nil {
		s.errorTotal.Add(1)
		writeErr(w, enforcerr)
		return
	}
	if action.Replayed {
		s.replayedTotal.Add(1)
		writeJSON(w, http.StatusOK, toResponse(action))
		return
	}
	s.enforcedTotal.Add(1)
	writeJSON(w, http.StatusCreated, toResponse(action))
}

// handleList implements GET /v1/actions.
func (s *Server) handleList(w http.ResponseWriter, r *http.Request) {
	records := s.enf.List()
	out := actionListResponse{Actions: make([]enforceResponse, 0, len(records))}
	for _, a := range records {
		out.Actions = append(out.Actions, toResponse(a))
	}
	writeJSON(w, http.StatusOK, out)
}

// handleGet implements GET /v1/actions/{id}.
func (s *Server) handleGet(w http.ResponseWriter, r *http.Request) {
	action, ok := s.enf.Get(r.PathValue("id"))
	if !ok {
		writeError(w, http.StatusNotFound, enforce.ErrCodeUnknownAction, "no action with this id",
			map[string]any{"action_id": r.PathValue("id")})
		return
	}
	writeJSON(w, http.StatusOK, toResponse(action))
}

// handleRelease implements DELETE /v1/actions/{id}.
func (s *Server) handleRelease(w http.ResponseWriter, r *http.Request) {
	action, enforcerr := s.enf.Release(r.PathValue("id"))
	if enforcerr != nil {
		s.errorTotal.Add(1)
		writeErr(w, enforcerr)
		return
	}
	s.releasedTotal.Add(1)
	writeJSON(w, http.StatusOK, toResponse(action))
}

// decode bounds and parses a JSON request body. Unknown fields are rejected:
// the surface is tiny and a typo'd field name should fail loudly, not land
// silently as an ignored no-op.
func decode[T any](w http.ResponseWriter, r *http.Request) (T, error) {
	var out T
	r.Body = http.MaxBytesReader(w, r.Body, MaxRequestBytes)
	dec := json.NewDecoder(r.Body)
	dec.DisallowUnknownFields()
	if err := dec.Decode(&out); err != nil {
		writeError(w, http.StatusBadRequest, "invalid_request", err.Error(), nil)
		return out, err
	}
	return out, nil
}

func writeJSON(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(body)
}
