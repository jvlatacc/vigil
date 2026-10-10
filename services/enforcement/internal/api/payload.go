package api

import "github.com/jvlatacc/vigil/services/enforcement/internal/enforce"

// timeLayout is RFC 3339 UTC, the timestamp format the contract uses.
const timeLayout = "2006-01-02T15:04:05Z"

// enforceRequest is the wire form of a POST /v1/actions body — the spec's
// contract sample. Absent optional numerics decode to 0, which the target
// validators treat as "absent" (0 is never a valid port or PID).
type enforceRequest struct {
	ActionID       string `json:"action_id"`
	Kind           string `json:"kind"`
	Target         target `json:"target"`
	TTLSeconds     int    `json:"ttl_seconds"`
	Reason         string `json:"reason"`
	IdempotencyKey string `json:"idempotency_key"`
}

type target struct {
	IP   string `json:"ip"`
	Port int    `json:"port"`
	PID  int    `json:"pid"`
}

// enforceResponse is the wire form of the POST reply — the contract subset:
// action_id, state, evidence, expires_at. Replayed marks a no-op answer to a
// duplicate delivery, so the executor can distinguish "applied now" from
// "already applied" without a new concept.
type enforceResponse struct {
	ActionID   string      `json:"action_id"`
	State      string      `json:"state"`
	Evidence   evidenceDTO `json:"evidence"`
	ExpiresAt  string      `json:"expires_at"`
	Replayed   bool        `json:"replayed"`
	ReleasedAt string      `json:"released_at,omitempty"`
}

type evidenceDTO struct {
	AttachPoint string            `json:"attach_point"`
	Map         string            `json:"map"`
	MapSlot     int               `json:"map_slot"`
	Counters    map[string]uint64 `json:"counters"`
}

type actionListResponse struct {
	Actions []enforceResponse `json:"actions"`
}

// toInput maps the wire request onto the engine Input. The IP string stays
// raw — the enforcer owns parsing and refusal.
func (r enforceRequest) toInput() enforce.Input {
	return enforce.Input{
		ActionID:       r.ActionID,
		Kind:           enforce.Kind(r.Kind),
		IP:             r.Target.IP,
		Port:           r.Target.Port,
		PID:            r.Target.PID,
		TTLSeconds:     r.TTLSeconds,
		Reason:         r.Reason,
		IdempotencyKey: r.IdempotencyKey,
	}
}

func toResponse(a enforce.Action) enforceResponse {
	out := enforceResponse{
		ActionID: a.ActionID,
		State:    a.State,
		Evidence: evidenceDTO{
			AttachPoint: a.Evidence.AttachPoint,
			Map:         a.Evidence.Map,
			MapSlot:     a.Evidence.MapSlot,
			Counters:    a.Evidence.Counters,
		},
		ExpiresAt: a.ExpiresAt.Format(timeLayout),
		Replayed:  a.Replayed,
	}
	if !a.ReleasedAt.IsZero() {
		out.ReleasedAt = a.ReleasedAt.Format(timeLayout)
	}
	return out
}
