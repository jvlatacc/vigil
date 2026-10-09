package enforce

import (
	"encoding/binary"
	"fmt"
	"net/netip"
)

// Target is a parsed enforcement target. The zero value is invalid by
// construction — targets enter through parseTarget.
type Target struct {
	IP   netip.Addr
	Port int
	PID  int
}

// Refusal reasons carried in the invalid_target error payload
// (details.reason). The vocabulary is pinned by the error contract schema.
const (
	ReasonMissingIP      = "missing_ip"
	ReasonUnparseableIP  = "unparseable_ip"
	ReasonLoopback       = "loopback"
	ReasonMulticast      = "multicast"
	ReasonUnspecified    = "unspecified"
	ReasonBroadcast      = "broadcast"
	ReasonLinkLocal      = "link_local"
	ReasonMissingPID     = "missing_pid"
	ReasonBadPID         = "bad_pid"
	ReasonBadPort        = "bad_port"
	ReasonPortNotAllowed = "port_not_allowed"
	ReasonIPNotAllowed   = "ip_not_allowed"
	ReasonPIDNotAllowed  = "pid_not_allowed"
)

// maxPID mirrors Linux's default pid_max (4194304) — a larger PID cannot
// exist on the protected host.
const maxPID = 4 * 1024 * 1024

var v4Broadcast = netip.AddrFrom4([4]byte{255, 255, 255, 255})

// parseTarget builds a Target from raw wire fields and refuses invalid ones.
// ipRaw is the raw JSON string; port and pid arrive as 0 when absent — both
// are invalid as real values, so 0 encodes "absent" at the wire.
func parseTarget(kind Kind, ipRaw string, port, pid int) (Target, *Error) {
	t := Target{Port: port, PID: pid}
	if ipRaw != "" {
		addr, err := netip.ParseAddr(ipRaw)
		if err != nil {
			return Target{}, targetError(ReasonUnparseableIP, ipRaw)
		}
		t.IP = addr
	}
	if err := t.validate(kind); err != nil {
		return Target{}, err
	}
	return t, nil
}

// validate refuses targets that must never be enforced against. It mirrors
// the Python side's _actionable_ip — loopback/multicast/etc. — so a target
// Vigil's Responder would not act on is also refused at the kernel gate.
func (t Target) validate(kind Kind) *Error {
	switch kind {
	case KindXDPDrop, KindSocketRedirect:
		if !t.IP.IsValid() {
			return targetError(ReasonMissingIP, "")
		}
		if t.Port < 0 || t.Port > 65535 {
			return targetError(ReasonBadPort, fmt.Sprintf("%d", t.Port))
		}
		if t.PID != 0 {
			return targetError(ReasonPIDNotAllowed, fmt.Sprintf("%d", t.PID))
		}
		if kind == KindXDPDrop && t.Port != 0 {
			return targetError(ReasonPortNotAllowed, fmt.Sprintf("%d", t.Port))
		}
		if err := refuseNonRoutable(t.IP); err != nil {
			return err
		}
	case KindProcessInterdict:
		if t.PID == 0 {
			return targetError(ReasonMissingPID, "")
		}
		if t.PID < 1 || t.PID > maxPID {
			return targetError(ReasonBadPID, fmt.Sprintf("%d", t.PID))
		}
		if t.IP.IsValid() {
			return targetError(ReasonIPNotAllowed, t.IP.String())
		}
		if t.Port != 0 {
			return targetError(ReasonPortNotAllowed, fmt.Sprintf("%d", t.Port))
		}
	default:
		return &Error{Code: ErrCodeUnsupportedKind, Message: "unknown kind: " + string(kind)}
	}
	return nil
}

// refuseNonRoutable rejects the address classes where a block is either
// self-inflicted or meaningless.
func refuseNonRoutable(a netip.Addr) *Error {
	switch {
	case a.IsLoopback():
		return targetError(ReasonLoopback, a.String())
	case a.IsMulticast():
		return targetError(ReasonMulticast, a.String())
	case a.IsUnspecified():
		return targetError(ReasonUnspecified, a.String())
	case a.IsLinkLocalUnicast():
		return targetError(ReasonLinkLocal, a.String())
	case a == v4Broadcast:
		return targetError(ReasonBroadcast, a.String())
	}
	return nil
}

func targetError(reason, value string) *Error {
	details := map[string]any{"reason": reason}
	if value != "" {
		details["target"] = value
	}
	return &Error{Code: ErrCodeInvalidTarget, Message: "target refused: " + reason, Details: details}
}

// key is the map key the kind's pinned BPF map holds: the 16-byte IP form
// (plus a 2-byte port when set), or an 8-byte PID. The real loader reads the
// same bytes; keeping the encoding in one function is what makes that
// handoff reviewable.
func (t Target) key() []byte {
	if t.PID != 0 {
		b := make([]byte, 8)
		binary.BigEndian.PutUint64(b, uint64(t.PID))
		return b
	}
	b := make([]byte, 0, 18)
	if t.IP.IsValid() {
		a16 := t.IP.As16()
		b = append(b, a16[:]...)
	}
	if t.Port != 0 {
		b = binary.BigEndian.AppendUint16(b, uint16(t.Port))
	}
	return b
}
