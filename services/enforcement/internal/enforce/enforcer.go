package enforce

import (
	"crypto/sha256"
	"encoding/binary"
	"fmt"
	"sync"
	"time"
)

// TTLFloor is the shortest containment the daemon accepts. An enforcement
// that outlives its reason is a new finding — 60s keeps a sub-floor TTL
// (effectively a no-op or a misconfiguration) from being recorded as enforced.
const TTLFloor = 60 * time.Second

// maxTTLSeconds is an overflow guard more than policy: a year of kernel state
// wants its own review. time.Duration arithmetic below it cannot wrap.
const maxTTLSeconds = 366 * 24 * 60 * 60

// Action states, mirroring the contract's state enum.
const (
	StateEnforced = "enforced"
	StateReleased = "released"
)

// Error-code vocabulary. The api layer maps these to HTTP status; the set is
// pinned by contract/error-response.schema.json.
const (
	ErrCodeUnauthorized         = "unauthorized"
	ErrCodeInvalidRequest       = "invalid_request"
	ErrCodeUnknownAction        = "unknown_action"
	ErrCodeActionIDConflict     = "action_id_conflict"
	ErrCodeUnsupportedKind      = "unsupported_kind"
	ErrCodeInvalidTarget        = "invalid_target"
	ErrCodeTTLBelowFloor        = "ttl_below_floor"
	ErrCodePrimitiveUnavailable = "primitive_unavailable"
	ErrCodeKernelError          = "kernel_error"
)

// Error is a structured refusal or failure. Message is for the operator;
// Code (and Details) are for the executor's mark_failed payload.
type Error struct {
	Code    string
	Message string
	Details map[string]any
}

func (e *Error) Error() string { return e.Code + ": " + e.Message }

// Input is one enforcement request. The target arrives unparsed — the
// Enforcer owns validation so idempotency, not the transport, decides
// whether a replay is answered from its stored record.
type Input struct {
	ActionID       string
	Kind           Kind
	IP             string // raw wire value, "" when absent
	Port           int    // 0 when absent
	PID            int    // 0 when absent
	TTLSeconds     int    // 0 → daemon default
	Reason         string
	IdempotencyKey string
}

// Evidence is the kernel-level proof returned with every action — Vigil's
// executor stores it verbatim via mark_executed.
type Evidence struct {
	AttachPoint string            `json:"attach_point"`
	Map         string            `json:"map"`
	MapSlot     int               `json:"map_slot"`
	Counters    map[string]uint64 `json:"counters"`
}

// Action is a full enforcement record — the status surface. The POST
// response is the contract subset (action_id, state, evidence, expires_at);
// Replayed marks a no-op answer to a duplicate delivery.
type Action struct {
	ActionID       string
	Kind           Kind
	Target         Target
	TTLSeconds     int
	Reason         string
	IdempotencyKey string
	State          string
	Evidence       Evidence
	ExpiresAt      time.Time
	CreatedAt      time.Time
	ReleasedAt     time.Time
	Fingerprint    [sha256.Size]byte
	Replayed       bool `json:"-"`
}

// Enforcer turns validated inputs into kernel state. It is the only writer:
// idempotency, the TTL floor and target refusal all sit in front of the
// Kernel, so a request that reaches the kernel has been refused-or-accepted
// exactly once.
type Enforcer struct {
	kernel     Kernel
	defaultTTL time.Duration
	now        func() time.Time

	mu      sync.Mutex
	records map[string]*Action
	order   []string // insertion order for List
}

// NewEnforcer builds an Enforcer over a Kernel. defaultTTL fills requests
// that omit ttl_seconds; it must be at least TTLFloor.
func NewEnforcer(kernel Kernel, defaultTTL time.Duration) *Enforcer {
	return &Enforcer{
		kernel:     kernel,
		defaultTTL: defaultTTL,
		now:        time.Now,
		records:    make(map[string]*Action),
	}
}

// Enforce applies the action, or answers a replay from its stored record.
// A replayed action_id never touches the kernel: same request returns the
// original evidence; a different request under the same action_id is a
// conflict, not an enforcement. A released action_id stays released —
// re-enforcing under a released id would silently re-open containment;
// issue a new action_id instead.
func (e *Enforcer) Enforce(in Input) (Action, *Error) {
	if in.ActionID == "" {
		return Action{}, &Error{Code: ErrCodeInvalidRequest, Message: "action_id is required", Details: map[string]any{"field": "action_id"}}
	}
	if in.Reason == "" {
		return Action{}, &Error{Code: ErrCodeInvalidRequest, Message: "reason is required", Details: map[string]any{"field": "reason"}}
	}
	if in.IdempotencyKey == "" {
		return Action{}, &Error{Code: ErrCodeInvalidRequest, Message: "idempotency_key is required", Details: map[string]any{"field": "idempotency_key"}}
	}
	if in.TTLSeconds > maxTTLSeconds {
		return Action{}, &Error{Code: ErrCodeInvalidRequest, Message: "ttl_seconds above ceiling", Details: map[string]any{"field": "ttl_seconds", "ttl_seconds": in.TTLSeconds}}
	}
	ttl := e.defaultTTL
	if in.TTLSeconds != 0 {
		ttl = time.Duration(in.TTLSeconds) * time.Second
	}
	fp := fingerprint(in, ttl)

	// Kernel calls run under the lock: idempotency must decide-before-act,
	// and the map ops the real loader will issue are single-digit microseconds.
	e.mu.Lock()
	defer e.mu.Unlock()

	if prev, ok := e.records[in.ActionID]; ok {
		if prev.Fingerprint != fp {
			return Action{}, &Error{
				Code:    ErrCodeActionIDConflict,
				Message: "action_id was already used for a different request",
				Details: map[string]any{"action_id": in.ActionID},
			}
		}
		out := *prev
		out.Replayed = true
		return out, nil
	}

	if !in.Kind.Valid() {
		return Action{}, &Error{Code: ErrCodeUnsupportedKind, Message: "unknown kind: " + string(in.Kind)}
	}
	target, terr := parseTarget(in.Kind, in.IP, in.Port, in.PID)
	if terr != nil {
		return Action{}, terr
	}
	if in.TTLSeconds != 0 && ttl < TTLFloor {
		return Action{}, &Error{
			Code:    ErrCodeTTLBelowFloor,
			Message: "ttl_seconds below the 60s floor",
			Details: map[string]any{"ttl_seconds": in.TTLSeconds, "floor_seconds": 60},
		}
	}

	capability := e.kernel.Capability(in.Kind)
	if !capability.Supported {
		return Action{}, &Error{
			Code:    ErrCodePrimitiveUnavailable,
			Message: "primitive unavailable on this host",
			Details: map[string]any{"kind": string(in.Kind), "reason": capability.Reason},
		}
	}

	attachPoint, err := e.kernel.Attach(in.Kind)
	if err != nil {
		return Action{}, kernelError("attach "+string(in.Kind), err)
	}
	// The map value is the expiry timestamp: enforcement self-expires in the
	// kernel even if Vigil (or this daemon) disappears mid-containment.
	expiresAt := e.now().Add(ttl)
	mapPath, slot, err := e.kernel.MapUpdate(in.Kind, target.key(), expiryValue(expiresAt))
	if err != nil {
		return Action{}, kernelError("map update "+string(in.Kind), err)
	}
	stats, err := e.kernel.Stats(in.Kind)
	if err != nil {
		// Evidence without counters would be a faked success — the contract
		// requires the counters object. Fail closed; the block is retriable.
		return Action{}, kernelError("stats "+string(in.Kind), err)
	}

	now := e.now()
	rec := &Action{
		ActionID:       in.ActionID,
		Kind:           in.Kind,
		Target:         target,
		TTLSeconds:     int(ttl / time.Second),
		Reason:         in.Reason,
		IdempotencyKey: in.IdempotencyKey,
		State:          StateEnforced,
		Evidence: Evidence{
			AttachPoint: attachPoint,
			Map:         mapPath,
			MapSlot:     slot,
			Counters:    stats.Counters,
		},
		ExpiresAt:   expiresAt.UTC().Truncate(time.Second),
		CreatedAt:   now.UTC().Truncate(time.Second),
		Fingerprint: fp,
	}
	e.records[in.ActionID] = rec
	e.order = append(e.order, in.ActionID)
	return *rec, nil
}

// Release removes the action's kernel state. Idempotent: releasing a released
// action returns its record unchanged.
func (e *Enforcer) Release(actionID string) (Action, *Error) {
	e.mu.Lock()
	defer e.mu.Unlock()
	rec, ok := e.records[actionID]
	if !ok {
		return Action{}, &Error{
			Code:    ErrCodeUnknownAction,
			Message: "no action with this id",
			Details: map[string]any{"action_id": actionID},
		}
	}
	if rec.State == StateEnforced {
		if err := e.kernel.Release(rec.Kind, rec.Target.key()); err != nil {
			return Action{}, kernelError("release "+string(rec.Kind), err)
		}
		rec.State = StateReleased
		rec.ReleasedAt = e.now().UTC().Truncate(time.Second)
	}
	return *rec, nil
}

// List returns every record in insertion order.
func (e *Enforcer) List() []Action {
	e.mu.Lock()
	defer e.mu.Unlock()
	out := make([]Action, 0, len(e.order))
	for _, id := range e.order {
		out = append(out, *e.records[id])
	}
	return out
}

// Get returns one record.
func (e *Enforcer) Get(actionID string) (Action, bool) {
	e.mu.Lock()
	defer e.mu.Unlock()
	rec, ok := e.records[actionID]
	if !ok {
		return Action{}, false
	}
	return *rec, true
}

// Capability and Stats forward kernel reads for /healthz and /metrics.
func (e *Enforcer) Capability(kind Kind) Capability { return e.kernel.Capability(kind) }
func (e *Enforcer) Stats(kind Kind) (Stats, error)  { return e.kernel.Stats(kind) }

// fingerprint identifies "the same request" for idempotency: kind, canonical
// target fields, the effective TTL, idempotency key and reason. A duplicate
// delivery hashes equal; a changed body under the same action_id does not.
func fingerprint(in Input, ttl time.Duration) [sha256.Size]byte {
	h := sha256.New()
	fmt.Fprintf(h, "%s\x00%s\x00%d\x00%d\x00%d\x00%s\x00%s",
		string(in.Kind), in.IP, in.Port, in.PID, int(ttl/time.Second), in.IdempotencyKey, in.Reason)
	var out [sha256.Size]byte
	copy(out[:], h.Sum(nil))
	return out
}

// expiryValue is the 8-byte big-endian unix timestamp stored in map values.
func expiryValue(t time.Time) []byte {
	b := make([]byte, 8)
	binary.BigEndian.PutUint64(b, uint64(t.Unix()))
	return b
}

func kernelError(op string, err error) *Error {
	return &Error{
		Code:    ErrCodeKernelError,
		Message: "kernel operation failed: " + op,
		Details: map[string]any{"cause": err.Error()},
	}
}
