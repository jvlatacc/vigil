//go:build linux

package enforce

import (
	"bytes"
	"encoding/binary"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"os"
	"os/exec"
	"strings"
	"syscall"
	"testing"
	"time"

	"golang.org/x/sys/unix"
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

// TestInterdictFallbackReasonClassifiesLSMFailures pins the fallback
// classifier: kernel LSM-availability errnos degrade to the signal
// fallback; anything else must surface as a plain load failure.
func TestInterdictFallbackReasonClassifiesLSMFailures(t *testing.T) {
	classified := []error{unix.EPERM, unix.EINVAL, unix.EOPNOTSUPP, unix.ENOTSUP}
	for _, err := range classified {
		wrapped := fmt.Errorf("load program: %w", err)
		if got := interdictFallbackReason(wrapped); got == "" {
			t.Errorf("interdictFallbackReason(%v) = \"\", want an LSM-unavailable reason", wrapped)
		}
	}
	unclassified := []error{
		errors.New("boom"),
		os.ErrNotExist,
		fmt.Errorf("open %s: %w", "/tmp/x", os.ErrPermission),
		unix.ESRCH,
	}
	for _, err := range unclassified {
		if got := interdictFallbackReason(err); got != "" {
			t.Errorf("interdictFallbackReason(%v) = %q, want \"\" (plain failure must not degrade)", err, got)
		}
	}
	// The observed live signature (cilium link attach on an lsm=-less
	// 6.1 kernel): the errno does not survive the wrap, the message does.
	live := fmt.Errorf("program vigil_interdict_connect: attach LSM/LSMMac: socket_connect LSM hook not supported")
	if got := interdictFallbackReason(live); got == "" {
		t.Errorf("interdictFallbackReason(live attach error) = \"\", want an LSM-unavailable reason")
	}
}

// TestEntriesUnloadedKindIsEmpty pins the reconciler-critical semantics of
// an unloaded primitive: no loaded state means NO enforcement entries — an
// empty set, not an error. A hard error here aborts the reconciler's whole
// sweep whenever any one optional kind is degraded (the observed failure:
// no sink configured → every 15s tick failed → expired XDP entries were
// never reclaimed and eviction receipts were suppressed).
func TestEntriesUnloadedKindIsEmpty(t *testing.T) {
	k := signalFallbackKernel() // kinds map empty: nothing loaded
	entries, err := k.Entries(KindSocketRedirect)
	if err != nil {
		t.Fatalf("Entries(unloaded kind) error = %v, want nil", err)
	}
	if len(entries) != 0 {
		t.Errorf("Entries(unloaded kind) = %d entries, want 0", len(entries))
	}
}

// TestParseCgroupV2IDExtractsInode covers the /proc/<pid>/cgroup parser
// against real directory inodes (v2), cgroup-v1 layouts, and garbage.
func TestParseCgroupV2ID(t *testing.T) {
	dir := t.TempDir()
	want := inodeOf(t, dir)

	cases := []struct {
		name    string
		content string
		wantID  uint64
		wantOK  bool
	}{
		{"v2 entry", fmt.Sprintf("0::%s\n", dir), want, true},
		{"v2 entry without trailing newline", fmt.Sprintf("0::%s", dir), want, true},
		{"v1 layout has no v2 line", "12:pids:/user.slice\n11:cpuset:/\n", 0, false},
		{"v2 path missing on disk", "0::/nonexistent-vigil-test-path\n", 0, false},
		{"garbage", "hello\nworld\n", 0, false},
		{"empty", "", 0, false},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got, ok := parseCgroupV2ID([]byte(tc.content))
			if ok != tc.wantOK || (ok && got != tc.wantID) {
				t.Errorf("parseCgroupV2ID = (%d, %v), want (%d, %v)", got, ok, tc.wantID, tc.wantOK)
			}
		})
	}
}

// inodeOf is the test's own inode lookup (same mechanism the parser
// relies on: the kernfs inode number is the cgroup id).
func inodeOf(t *testing.T, path string) uint64 {
	t.Helper()
	var st syscall.Stat_t
	if err := syscall.Stat(path, &st); err != nil {
		t.Fatalf("stat %s: %v", path, err)
	}
	return st.Ino
}

// signalFallbackKernel is a BPFKernel with no loaded collections: exactly
// the state installSignalFallback arms on an LSM-less host.
func signalFallbackKernel() *BPFKernel {
	return &BPFKernel{
		iface: "eth0",
		kinds: map[Kind]*bpfKindState{},
		caps:  map[Kind]Capability{},
	}
}

func discardLogger() *slog.Logger {
	return slog.New(slog.NewTextHandler(io.Discard, nil))
}

// TestSignalFallbackReportsDegradedMode checks the observable state after
// the fallback arms: the kind enforces through "signal" mode, stays
// supported-but-degraded with a reason, and reports zero denials with the
// truthful empty occupancy.
func TestSignalFallbackReportsDegradedMode(t *testing.T) {
	k := signalFallbackKernel()
	k.installSignalFallback("unit-test: LSM unavailable", discardLogger())

	if got := k.Mode(KindProcessInterdict); got != "signal" {
		t.Errorf("Mode = %q, want signal", got)
	}
	capability := k.Capability(KindProcessInterdict)
	if !capability.Supported || !capability.Degraded || capability.Reason == "" {
		t.Errorf("Capability = %+v, want supported degraded with a reason", capability)
	}
	stats, err := k.Stats(KindProcessInterdict)
	if err != nil {
		t.Fatalf("Stats: %v", err)
	}
	if got := stats.Counters["denied_ops"]; got != 0 {
		t.Errorf("denied_ops = %d, want 0 (no in-kernel counter exists in signal mode)", got)
	}
	if stats.Occupancy != 0 {
		t.Errorf("occupancy = %d, want 0", stats.Occupancy)
	}
	entries, err := k.Entries(KindProcessInterdict)
	if err != nil {
		t.Fatalf("Entries: %v", err)
	}
	if len(entries) != 0 {
		t.Errorf("entries = %d, want 0", len(entries))
	}
}

// TestSignalFallbackSuspendsAndResumesRealProcess exercises the fallback
// against a child process we own: SIGSTOP must freeze it (state T),
// release must resume it, and unknown releases must be quiet.
func TestSignalFallbackSuspendsAndResumesRealProcess(t *testing.T) {
	cmd := exec.Command("sleep", "30")
	if err := cmd.Start(); err != nil {
		t.Skipf("cannot start a child process here: %v", err)
	}
	t.Cleanup(func() {
		_ = cmd.Process.Kill()
		_ = cmd.Wait()
	})
	pid := cmd.Process.Pid

	k := signalFallbackKernel()
	k.installSignalFallback("unit-test", discardLogger())
	bk := k.kinds[KindProcessInterdict]

	expiry := fixedNow.Add(time.Hour)
	if err := k.suspend(bk, pid, expiry); err != nil {
		t.Fatalf("suspend: %v", err)
	}
	if state := pollState(t, pid, "T", 2*time.Second); state != "T" {
		t.Fatalf("child state after SIGSTOP = %q, want T (stopped)", state)
	}
	entries, err := k.Entries(KindProcessInterdict)
	if err != nil || len(entries) != 1 {
		t.Fatalf("Entries = (%d, %v), want 1 suspended entry", len(entries), err)
	}
	if !bytes.Equal(entries[0].Key, encodeEngineKeyPID(pid)) {
		t.Errorf("entry key = % x, want the engine's big-endian PID encoding % x", entries[0].Key, encodeEngineKeyPID(pid))
	}
	if !entries[0].Expiry.Equal(expiry) {
		t.Errorf("entry expiry = %v, want %v (the reconciler evicts by this deadline)", entries[0].Expiry, expiry)
	}

	// Releasing an unknown pid is quiet and must not signal our own
	// (running) test process.
	if err := k.resume(bk, os.Getpid()); err != nil {
		t.Errorf("resume of unknown pid: %v", err)
	}
	if state := pollState(t, pid, "T", 2*time.Second); state != "T" {
		t.Errorf("child state = %q, want T (unknown-pid resume must not have resumed it)", state)
	}

	if err := k.resume(bk, pid); err != nil {
		t.Fatalf("resume: %v", err)
	}
	if state := pollStateNot(t, pid, "T", 2*time.Second); state == "T" {
		t.Errorf("child state after resume = T, want a running state")
	}
}

// TestSignalFallbackSuspendRefusesNonPIDs pins target validation: a key
// that is not a PID is refused before any signal is sent.
func TestSignalFallbackSuspendRefusesNonPIDs(t *testing.T) {
	k := signalFallbackKernel()
	k.installSignalFallback("unit-test", discardLogger())
	bk := k.kinds[KindProcessInterdict]
	for _, pid := range []int{0, -1, maxPID + 1} {
		if err := k.suspend(bk, pid, fixedNow.Add(time.Hour)); err == nil {
			t.Errorf("suspend(pid=%d) = nil, want refusal", pid)
		}
	}
	if len(bk.suspended) != 0 {
		t.Errorf("suspended = %d entries, want 0 (refusals must not record)", len(bk.suspended))
	}
}

// TestGracefulShutdownResumesSuspended pins the shutdown contract: Close
// resumes every process the fallback froze.
func TestGracefulShutdownResumesSuspended(t *testing.T) {
	cmd := exec.Command("sleep", "30")
	if err := cmd.Start(); err != nil {
		t.Skipf("cannot start a child process here: %v", err)
	}
	t.Cleanup(func() {
		_ = cmd.Process.Kill()
		_ = cmd.Wait()
	})
	pid := cmd.Process.Pid

	k := signalFallbackKernel()
	k.installSignalFallback("unit-test", discardLogger())
	bk := k.kinds[KindProcessInterdict]
	if err := k.suspend(bk, pid, fixedNow.Add(time.Hour)); err != nil {
		t.Fatalf("suspend: %v", err)
	}

	if err := k.Close(); err != nil {
		t.Fatalf("Close: %v", err)
	}
	if state := pollStateNot(t, pid, "T", 2*time.Second); state == "T" {
		t.Errorf("child state after Close = T, want resumed (graceful shutdown must not leave processes frozen)")
	}
}

// procState reads /proc/<pid>/stat's state letter (field 3, after the
// parenthesized comm which may itself contain spaces).
func procState(t *testing.T, pid int) string {
	t.Helper()
	data, err := os.ReadFile(fmt.Sprintf("/proc/%d/stat", pid))
	if err != nil {
		t.Fatalf("reading /proc/%d/stat: %v", pid, err)
	}
	s := string(data)
	idx := strings.LastIndex(s, ")")
	if idx < 0 || idx+2 >= len(s) {
		t.Fatalf("unexpected stat format: %q", s)
	}
	// Field 3 (state) is the first token after the command name — the
	// remaining fields (ppid, pgrp, …) follow it on the same line.
	return strings.Fields(strings.TrimSpace(s[idx+2:]))[0]
}

// encodeEngineKeyPID is the engine's PID target encoding (big-endian u64)
// — the same bytes mapKeyFor passes through for the interdict kind.
func encodeEngineKeyPID(pid int) []byte {
	b := make([]byte, 8)
	binary.BigEndian.PutUint64(b, uint64(pid))
	return b
}

// pollState samples /proc state until it matches want or the timeout
// elapses, returning the last observed state. Signal delivery is
// asynchronous — the state change can trail kill(2) by a scheduler tick,
// and a freshly started child may sit in D (uninterruptible) while the
// kernel finishes exec — so a single read races the transition.
func pollState(t *testing.T, pid int, want string, d time.Duration) string {
	t.Helper()
	deadline := time.Now().Add(d)
	for {
		state := procState(t, pid)
		if state == want {
			return state
		}
		if time.Now().After(deadline) {
			return state
		}
		time.Sleep(20 * time.Millisecond)
	}
}

// pollStateNot samples /proc state until it LEAVES notWant or the timeout
// elapses, returning the last observed state — the resume-side twin of
// pollState (SIGCONT must be scheduled before the process runs again).
func pollStateNot(t *testing.T, pid int, notWant string, d time.Duration) string {
	t.Helper()
	deadline := time.Now().Add(d)
	for {
		state := procState(t, pid)
		if state != notWant {
			return state
		}
		if time.Now().After(deadline) {
			return state
		}
		time.Sleep(20 * time.Millisecond)
	}
}
