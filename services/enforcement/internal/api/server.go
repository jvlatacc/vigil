// Package api is the daemon's HTTP surface: the token-authed /v1
// enforcement API plus unauthenticated /healthz and /metrics. The listener
// binds loopback by default (spec: loopback-only binding; the ADR-0014
// shared-secret model covers the /v1 subtree).
package api

import (
	"crypto/subtle"
	"errors"
	"net/http"
	"strings"
	"sync/atomic"
	"time"

	"github.com/jvlatacc/vigil/services/enforcement/internal/enforce"
)

// MaxRequestBytes bounds every request body. The contract's largest legal
// request is a few hundred bytes; 64 KiB leaves room without becoming an
// amplifier.
const MaxRequestBytes = 64 << 10

// Server is the HTTP surface around an Enforcer.
type Server struct {
	token string
	enf   *enforce.Enforcer
	// kernelFaked is what /healthz reports in kernel_faked: non-empty only
	// on the faked kernel (dev/CI). An empty string means a real kernel
	// loader, per the contract.
	kernelFaked string
	started     time.Time

	enforcedTotal atomic.Uint64
	replayedTotal atomic.Uint64
	releasedTotal atomic.Uint64
	rejectedTotal atomic.Uint64
	errorTotal    atomic.Uint64
}

// New builds a Server. The token is required — the daemon fails closed
// rather than serving an unauthenticated enforcement API.
func New(token string, enf *enforce.Enforcer, kernelFaked string) (*Server, error) {
	if token == "" {
		return nil, errors.New("enforcement API requires a non-empty auth token")
	}
	return &Server{token: token, enf: enf, kernelFaked: kernelFaked, started: time.Now()}, nil
}

// Handler returns the routed mux. Go's method-pattern ServeMux answers 405
// on known paths hit with the wrong method and 404 elsewhere.
func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("POST /v1/actions", s.auth(s.handleEnforce))
	mux.HandleFunc("GET /v1/actions", s.auth(s.handleList))
	mux.HandleFunc("GET /v1/actions/{id}", s.auth(s.handleGet))
	mux.HandleFunc("DELETE /v1/actions/{id}", s.auth(s.handleRelease))
	// Health and metrics are deliberately unauthenticated: the daemon binds
	// loopback by default, k8s probes speak plain GET, and neither endpoint
	// carries secrets. Everything that can move the kernel sits behind auth.
	mux.HandleFunc("GET /healthz", s.handleHealthz)
	mux.HandleFunc("GET /metrics", s.handleMetrics)
	// Catch-all so no reply escapes the error contract's closed shape —
	// ServeMux's default 404 is plain text. Registering it shadows Go's
	// automatic 405 for known paths, so wrong-method hits on known routes
	// are reproduced here.
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		if knownRoutePath(r.URL.Path) {
			writeError(w, http.StatusMethodNotAllowed, enforce.ErrCodeInvalidRequest,
				"method not allowed on this route",
				map[string]any{"method": r.Method, "path": r.URL.Path})
			return
		}
		writeError(w, http.StatusNotFound, enforce.ErrCodeUnknownAction,
			"no such route", map[string]any{"path": r.URL.Path})
	})
	return mux
}

// knownRoutePath reports whether the path is a registered route — used by
// the catch-all to distinguish wrong-method (405) from no-such-route (404).
func knownRoutePath(path string) bool {
	return path == "/v1/actions" || path == "/healthz" || path == "/metrics" ||
		strings.HasPrefix(path, "/v1/actions/")
}

// auth gates the /v1 subtree on the shared secret. A missing header and a
// wrong token are equally 401; the comparison is constant-time.
func (s *Server) auth(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		got, ok := strings.CutPrefix(r.Header.Get("Authorization"), "Bearer ")
		if !ok || subtle.ConstantTimeCompare([]byte(got), []byte(s.token)) != 1 {
			s.rejectedTotal.Add(1)
			writeError(w, http.StatusUnauthorized, enforce.ErrCodeUnauthorized, "missing or invalid bearer token", nil)
			return
		}
		next(w, r)
	}
}
