//go:build linux

package enforce

import (
	"fmt"
	"os"
	"strings"
	"syscall"
	"testing"
	"time"
)

// mapKeyFor is the loader's key normalizer: engine-minimal keys in, fixed
// kernel map keys out. The redirect map pads a portless key to the
// wildcard-port form.
func TestMapKeyForNormalizesToFixedWidth(t *testing.T) {
	ip := make([]byte, 16)
	for i := range ip {
		ip[i] = byte(i)
	}
	port := []byte{0x11, 0x62} // 4444 big-endian

	got, err := mapKeyFor(KindSocketRedirect, ip)
	if err != nil {
		t.Fatalf("redirect key without port: %v", err)
	}
	if len(got) != 18 {
		t.Fatalf("redirect key without port: len = %d, want 18 (padded wildcard)", len(got))
	}
	for i := 16; i < 18; i++ {
		if got[i] != 0 {
			t.Errorf("padded port byte %d = %d, want 0", i, got[i])
		}
	}

	withPort := append(append([]byte{}, ip...), port...)
	got, err = mapKeyFor(KindSocketRedirect, withPort)
	if err != nil || string(got) != string(withPort) {
		t.Fatalf("redirect key with port: %v, % x", err, got)
	}

	if _, err := mapKeyFor(KindXDPDrop, withPort); err == nil {
		t.Error("xdp_drop must refuse a key that is not exactly 16 bytes")
	}
	if _, err := mapKeyFor(KindProcessInterdict, []byte{1, 2, 3}); err == nil {
		t.Error("process_interdict must refuse a key that is not exactly 8 bytes")
	}
	if _, err := mapKeyFor(Kind("nope"), ip); err == nil {
		t.Error("unknown kind must be refused")
	}
}

// expiryValue <-> decodeExpiry is the single encoding shared by the engine,
// the loader, and the faked kernel.
func TestExpiryRoundTripAndDecode(t *testing.T) {
	at := fixedNow.Add(90 * time.Second)
	got, err := decodeExpiry(expiryValue(at))
	if err != nil {
		t.Fatalf("decodeExpiry: %v", err)
	}
	if !got.Equal(at.Truncate(time.Second)) {
		t.Errorf("decoded expiry = %v, want %v", got, at.Truncate(time.Second))
	}
	if _, err := decodeExpiry([]byte{1, 2, 3}); err == nil {
		t.Error("a short value must be refused, not silently widened")
	}
}

// probeReason is what an operator reads in /healthz when a primitive is
// degraded — common failure classes get actionable reasons.
func TestProbeReasonMapsCommonFailures(t *testing.T) {
	cases := []struct {
		name string
		err  error
		want string
	}{
		{"missing object", os.ErrNotExist, "object not found"},
		{"no capabilities", fmt.Errorf("load: %w", syscall.EPERM), "insufficient capabilities"},
		{"permission denied", fmt.Errorf("attach: %w", os.ErrPermission), "insufficient capabilities"},
		{"verifier rejection", fmt.Errorf("load: %w", syscall.ENOSPC), "kernel rejected"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := probeReason(tc.err, "xdp_drop.o")
			if !strings.Contains(got, tc.want) {
				t.Errorf("probeReason(%v) = %q, want it to contain %q", tc.err, got, tc.want)
			}
		})
	}
	if got := probeReason(fmt.Errorf("mystery"), "xdp_drop.o"); !strings.Contains(got, "mystery") {
		t.Errorf("unknown failures must carry the underlying error, got %q", got)
	}
}

// expiredEntries uses the same boundary as the datapath: an entry is
// expired the instant now >= expiry.
func TestExpiredEntriesBoundary(t *testing.T) {
	entries := []MapEntry{
		{Key: []byte("expires-exactly-now"), Expiry: fixedNow},
		{Key: []byte("still-blocking"), Expiry: fixedNow.Add(time.Second)},
		{Key: []byte("long-gone"), Expiry: fixedNow.Add(-time.Hour)},
	}
	got := expiredEntries(entries, fixedNow)
	if len(got) != 2 {
		t.Fatalf("expired entries = %d, want 2", len(got))
	}
	if string(got[0].Key) != "expires-exactly-now" || string(got[1].Key) != "long-gone" {
		t.Errorf("expired keys = %v, want the exactly-now and long-gone entries", got)
	}
}
