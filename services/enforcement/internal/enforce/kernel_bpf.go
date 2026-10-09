//go:build linux

package enforce

import (
	"encoding/binary"
	"errors"
	"fmt"
	"log/slog"
	"net"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/cilium/ebpf"
	"github.com/cilium/ebpf/btf"
	"github.com/cilium/ebpf/link"
	"golang.org/x/sys/unix"
)

// BPFObjectFiles names the compiled CO-RE object per kind, built by
// build-bpf.sh into ObjectsDir (bpf/build/<name>.o). The Dockerfile builder
// stage for the enforcer runs the same script — objects are image content;
// nothing BPF-related is compiled on the target host.
var BPFObjectFiles = map[Kind]string{
	KindXDPDrop:          "xdp_drop.o",
	KindSocketRedirect:   "socket_redirect.o",
	KindProcessInterdict: "interdict.o",
}

// bpfCounterMaps names each object's per-CPU counter array. The names are
// the FakeKernel's counter vocabulary — /metrics series stay stable across
// the faked and real kernels.
var bpfCounterMaps = map[Kind]string{
	KindXDPDrop:          "dropped_packets",
	KindSocketRedirect:   "redirected_packets",
	KindProcessInterdict: "denied_ops",
}

// BPFConfig is the startup configuration for the real loader.
type BPFConfig struct {
	// Interface is the NIC the XDP program attaches to; attach-point
	// evidence reads "<iface>/xdp".
	Interface string
	// ObjectsDir holds the compiled CO-RE objects (build-bpf.sh output).
	ObjectsDir string
	// CgroupPath is a cgroupv2 directory for the redirect primitive's
	// sockops enrollment hook; empty means the cgroup root.
	CgroupPath string
}

type bpfKindState struct {
	coll        *ebpf.Collection
	mainMap     *ebpf.Map
	mainPinPath string
	keySize     int
	offsetMap   *ebpf.Map
	counterMap  *ebpf.Map
	counterName string
	link        link.Link
	// extraLinks are secondary attach points per kind (the redirect kind
	// attaches its sockops enrollment hook to a cgroup alongside the sk_msg
	// verdict on the sockmap).
	extraLinks  []link.Link
	sinkConn    net.Conn
	sinkFile    *os.File
	attachPoint string
	// mode is the enforcement mechanism in use: "bpf", or a degraded
	// mechanism (the process-interdict signal fallback). Reported via
	// /healthz primitives.
	mode string
	// suspended holds the signal fallback's live interdictions: pid ->
	// suspension deadline. Only used when mode is "signal" — the primitive
	// enforces by SIGSTOP instead of a BPF map, so its state is process
	// memory, not kernel state, and a daemon restart loses it.
	suspended map[int]time.Time
}

// BPFKernel implements Kernel against the host kernel via cilium/ebpf.
//
// Programs attach at startup with empty maps — the capability probe is
// truthful because attaching an empty map changes no verdicts, and the
// engine consults Capability before every dispatch. Enforcement state is map
// content only: a block lives in the pinned LRU map with its expiry as the
// value, so it survives a daemon restart (pinned maps are adopted, not
// shadowed) and self-expires even with the daemon gone (the BPF programs
// compare the expiry against the loader-fed clock offset).
type BPFKernel struct {
	iface      string
	objectsDir string
	cgroupPath string
	log        *slog.Logger

	mu    sync.Mutex
	kinds map[Kind]*bpfKindState
	caps  map[Kind]Capability
}

// NewBPFKernel loads every kind's object, attaches its programs, and pins
// its maps. Per-kind failures degrade that primitive's capability (visible
// in /healthz) instead of failing the daemon; only an environmental failure
// — bpffs not mounted, so no state could exist at all — is fatal.
func NewBPFKernel(cfg BPFConfig, log *slog.Logger) (*BPFKernel, error) {
	if err := os.MkdirAll(MapPinDir, 0o700); err != nil {
		return nil, fmt.Errorf("creating map pin dir %s: %w (bpffs must be mounted; VIGIL_ENFORCEMENT_KERNEL=fake serves a faked kernel for dev/CI)", MapPinDir, err)
	}
	k := &BPFKernel{
		iface:      cfg.Interface,
		objectsDir: cfg.ObjectsDir,
		cgroupPath: cfg.CgroupPath,
		log:        log,
		kinds:      make(map[Kind]*bpfKindState, len(AllKinds)),
		caps:       make(map[Kind]Capability, len(AllKinds)),
	}
	if k.cgroupPath == "" {
		k.cgroupPath = "/sys/fs/cgroup"
	}
	// One shared BTF cache across the three collection loads amortises
	// kernel BTF decoding.
	cache := btf.NewCache()
	for _, kind := range AllKinds {
		if err := k.loadKind(kind, cache); err != nil {
			if kind == KindProcessInterdict {
				if reason := interdictFallbackReason(err); reason != "" {
					k.installSignalFallback(reason, log)
					continue
				}
			}
			log.Warn("primitive failed to load; degrading", "kind", kind, "err", err)
			k.caps[kind] = Capability{Supported: false, Reason: probeReason(err, BPFObjectFiles[kind])}
			continue
		}
		log.Info("primitive loaded and attached", "kind", kind,
			"attach_point", k.kinds[kind].attachPoint, "mode", k.kinds[kind].mode)
	}
	return k, nil
}

func (k *BPFKernel) loadKind(kind Kind, cache *btf.Cache) error {
	objPath := filepath.Join(k.objectsDir, BPFObjectFiles[kind])
	spec, err := ebpf.LoadCollectionSpec(objPath)
	if err != nil {
		return err
	}
	// Adopt pinned maps from a previous run: enforcement state lives in the
	// kernel, so a restart must reuse it, not shadow it (spec).
	replacements := map[string]*ebpf.Map{}
	for name := range spec.Maps {
		if m, err := ebpf.LoadPinnedMap(filepath.Join(MapPinDir, name), nil); err == nil {
			replacements[name] = m
		}
	}
	coll, err := ebpf.NewCollectionWithOptions(spec, ebpf.CollectionOptions{
		MapReplacements: replacements,
		Cache:           cache,
	})
	if err != nil {
		return err
	}
	bk := &bpfKindState{coll: coll, mode: "bpf"}
	if err := k.populateMaps(kind, bk, spec); err != nil {
		coll.Close()
		return err
	}
	if err := k.attachKind(kind, bk); err != nil {
		coll.Close()
		return err
	}
	// Pin the maps this run created (adopted ones are already pinned).
	for name, m := range coll.Maps {
		if _, reused := replacements[name]; reused {
			continue
		}
		if err := m.Pin(filepath.Join(MapPinDir, name)); err != nil {
			coll.Close()
			return fmt.Errorf("pin map %s: %w", name, err)
		}
	}
	k.kinds[kind] = bk
	k.caps[kind] = Capability{Supported: true}
	return nil
}

// populateMaps wires the per-object maps the loader and engine touch: the
// kind's enforcement map, its clock-offset copy, and its counter array.
func (k *BPFKernel) populateMaps(kind Kind, bk *bpfKindState, spec *ebpf.CollectionSpec) error {
	name := kind.mapName()
	mapSpec, ok := spec.Maps[name]
	if !ok {
		return fmt.Errorf("object has no %s map", name)
	}
	mainMap, ok := bk.coll.Maps[name]
	if !ok {
		return fmt.Errorf("collection has no %s map", name)
	}
	offsetMap, ok := bk.coll.Maps["clock_offset"]
	if !ok {
		return fmt.Errorf("object has no clock_offset map")
	}
	counterName := bpfCounterMaps[kind]
	counterMap, ok := bk.coll.Maps[counterName]
	if !ok {
		return fmt.Errorf("object has no %s counter map", counterName)
	}
	bk.mainMap = mainMap
	bk.mainPinPath = MapPinDir + "/" + name
	bk.keySize = int(mapSpec.KeySize)
	bk.offsetMap = offsetMap
	bk.counterMap = counterMap
	bk.counterName = counterName
	return nil
}

func (k *BPFKernel) attachKind(kind Kind, bk *bpfKindState) error {
	switch kind {
	case KindXDPDrop:
		return k.attachXDP(bk)
	case KindSocketRedirect:
		return k.attachSKMsg(bk)
	case KindProcessInterdict:
		return k.attachLSM(bk)
	default:
		return fmt.Errorf("no attach implementation for kind %s", kind)
	}
}

func (k *BPFKernel) attachXDP(bk *bpfKindState) error {
	prog := bk.coll.Programs["vigil_xdp_drop"]
	if prog == nil {
		return errors.New("object has no vigil_xdp_drop program")
	}
	iface, err := net.InterfaceByName(k.iface)
	if err != nil {
		return fmt.Errorf("interface %s: %w", k.iface, err)
	}
	// Flags 0 = best effort (native/driver mode when the NIC offers it,
	// generic otherwise). An XDP link survives a daemon crash: a restart
	// replaces the program wholesale, and the runbook documents manual
	// cleanup (`ip link set dev <iface> xdp off`).
	l, err := link.AttachXDP(link.XDPOptions{Program: prog, Interface: iface.Index})
	if err != nil {
		return fmt.Errorf("xdp attach on %s: %w", k.iface, err)
	}
	bk.link = l
	bk.attachPoint = k.iface + "/xdp"
	return nil
}

// Attach returns the attach point recorded at startup — programs attach once
// (empty map, no verdict changes) and stay attached.
func (k *BPFKernel) Attach(kind Kind) (string, error) {
	bk, err := k.state(kind)
	if err != nil {
		return "", err
	}
	return bk.attachPoint, nil
}

// attachSKMsg attaches the redirect object's two programs: the sk_msg
// verdict to the sockmap (messages on enrolled sockets) and the sockops
// enrollment hook to a cgroup (sockets established toward enforced
// targets). The verdict attach is a raw attach — the kernel keeps no link
// for it; Close detaches best-effort via RawDetachProgram.
func (k *BPFKernel) attachSKMsg(bk *bpfKindState) error {
	prog := bk.coll.Programs["vigil_sk_msg_redirect"]
	if prog == nil {
		return errors.New("object has no vigil_sk_msg_redirect program")
	}
	enroll := bk.coll.Programs["vigil_sock_enroll"]
	if enroll == nil {
		return errors.New("object has no vigil_sock_enroll program")
	}
	sockmap := bk.coll.Maps["sink_sockets"]
	if sockmap == nil {
		return errors.New("object has no sink_sockets sockmap")
	}
	if err := link.RawAttachProgram(link.RawAttachProgramOptions{
		Target:  sockmap.FD(),
		Program: prog,
		Attach:  ebpf.AttachSkMsgVerdict,
	}); err != nil {
		return fmt.Errorf("sk_msg verdict attach: %w", err)
	}
	cg, err := link.AttachCgroup(link.CgroupOptions{
		Path:    k.cgroupPath,
		Program: enroll,
		Attach:  ebpf.AttachCGroupSockOps,
	})
	if err != nil {
		return fmt.Errorf("sockops enroll attach on %s: %w", k.cgroupPath, err)
	}
	bk.extraLinks = append(bk.extraLinks, cg)
	bk.attachPoint = k.iface + "/sockmap"
	return nil
}

// attachLSM attaches the interdict object's two LSM programs (connect
// denial and exec denial). Both attach as links; a collection that loaded
// but cannot attach is a degrade, not a fallback — the signal fallback is
// only for kernels that cannot load LSM BPF at all.
func (k *BPFKernel) attachLSM(bk *bpfKindState) error {
	connect := bk.coll.Programs["vigil_interdict_connect"]
	if connect == nil {
		return errors.New("object has no vigil_interdict_connect program")
	}
	exec := bk.coll.Programs["vigil_interdict_exec"]
	if exec == nil {
		return errors.New("object has no vigil_interdict_exec program")
	}
	for name, prog := range map[string]*ebpf.Program{
		"connect": connect,
		"exec":    exec,
	} {
		l, err := link.AttachLSM(link.LSMOptions{Program: prog})
		if err != nil {
			return fmt.Errorf("lsm %s attach: %w", name, err)
		}
		bk.extraLinks = append(bk.extraLinks, l)
	}
	bk.attachPoint = k.cgroupPath + "/lsm"
	return nil
}

// Mode reports the enforcement mechanism a kind uses (ModeReporter):
// "bpf" for the primary mechanism, "signal" for the interdict kind's
// degraded fallback, empty when the kind is not loaded at all.
func (k *BPFKernel) Mode(kind Kind) string {
	bk, err := k.state(kind)
	if err != nil {
		return ""
	}
	return bk.mode
}

// SetSink inserts the connected sink socket at sockmap index 0 — the
// redirect target for enrolled flows (SinkSetter).
func (k *BPFKernel) SetSink(conn net.Conn) error {
	tcp, ok := conn.(*net.TCPConn)
	if !ok {
		return fmt.Errorf("sink must be a TCP connection to the tarpit/capture listener, got %T", conn)
	}
	// File() dups the fd; keep both the dup and the original connection
	// referenced for the daemon's lifetime — the runtime finalizer closes
	// the dup otherwise, which would silently empty sockmap slot 0.
	file, err := tcp.File()
	if err != nil {
		return fmt.Errorf("sink fd: %w", err)
	}
	k.mu.Lock()
	defer k.mu.Unlock()
	bk, ok := k.kinds[KindSocketRedirect]
	if !ok {
		file.Close()
		return fmt.Errorf("%s: %w", KindSocketRedirect, errKindNotLoaded)
	}
	sockmap := bk.coll.Maps["sink_sockets"]
	if sockmap == nil {
		file.Close()
		return errors.New("object has no sink_sockets sockmap")
	}
	if err := sockmap.Update(uint32(0), uint32(file.Fd()), ebpf.UpdateAny); err != nil {
		file.Close()
		return fmt.Errorf("inserting sink socket into sockmap: %w", err)
	}
	bk.sinkConn = conn
	bk.sinkFile = file
	// Echo bridge: sk_msg redirection deposits payloads on THIS socket's
	// receive queue — the daemon's end of the sink connection — so
	// without a reader the bytes sit unread and the sink application
	// never sees them. Read them and write them straight back down the
	// wire: they then travel as ordinary TCP data to the configured
	// tarpit/capture listener. Teardown closes the connection, which
	// ends the bridge with a read error.
	go func() {
		buf := make([]byte, 4096)
		for {
			n, err := conn.Read(buf)
			if n > 0 {
				if _, werr := conn.Write(buf[:n]); werr != nil {
					k.log.Warn("sink bridge write failed; redirected payloads stop reaching the sink", "err", werr)
					return
				}
			}
			if err != nil {
				k.log.Info("sink bridge ended", "err", err)
				return
			}
		}
	}()
	return nil
}

// MarkDegraded withdraws a primitive's capability after startup (Degrader) —
// for example when the redirect sink proves unreachable: an entry in the map
// with nowhere to steer is not enforcement, and the engine must refuse the
// dispatch rather than report a hollow success.
func (k *BPFKernel) MarkDegraded(kind Kind, reason string) {
	k.mu.Lock()
	defer k.mu.Unlock()
	k.caps[kind] = Capability{Supported: false, Reason: reason}
}

// errNoTSUPP is the kernel-internal ENOTSUPP (524) — the errno behind
// "LSM hook not supported". x/sys/unix does not export it.
const errNoTSUPP = syscall.Errno(524)

// interdictFallbackReason reports why the process-interdict kind should
// degrade to the signal fallback, or "" when the error is not an LSM
// availability failure — a build or environment failure must degrade
// plainly, never silently change the enforcement mechanism.
func interdictFallbackReason(err error) string {
	switch {
	case errors.Is(err, unix.EPERM),
		errors.Is(err, unix.EINVAL),
		errors.Is(err, unix.EOPNOTSUPP),
		errors.Is(err, unix.ENOTSUP),
		errors.Is(err, errNoTSUPP):
		return "BPF LSM unavailable (needs CONFIG_BPF_LSM and \"bpf\" in the kernel's lsm= parameter): " + err.Error()
	}
	// The kernel surfaces an unsupported LSM hook (lsm= without "bpf",
	// CONFIG_BPF_LSM off) with ENOTSUPP — "LSM hook not supported" — and
	// cilium/ebpf's link error does not always preserve that errno for
	// errors.Is; the observed signature is classified by message too.
	if strings.Contains(err.Error(), "LSM hook not supported") {
		return "BPF LSM unavailable: kernel reports the hook unsupported (" + err.Error() + ")"
	}
	return ""
}

// installSignalFallback arms the process-interdict signal fallback: the
// host cannot load BPF LSM programs, so the primitive enforces by
// SIGSTOP-ing the target PID and resuming it on release or expiry — the
// degraded mechanism the spec designs for LSM-less kernels. The state is
// process memory, not kernel state: a graceful shutdown resumes suspended
// processes, but a crash cannot (documented limitation — the BPF path's
// "kernel state survives the daemon" property is exactly what the
// fallback trades away for availability).
func (k *BPFKernel) installSignalFallback(reason string, log *slog.Logger) {
	k.mu.Lock()
	defer k.mu.Unlock()
	k.kinds[KindProcessInterdict] = &bpfKindState{
		mode:        "signal",
		attachPoint: "pid/signal",
		suspended:   make(map[int]time.Time),
	}
	k.caps[KindProcessInterdict] = Capability{Supported: true, Degraded: true, Reason: reason}
	log.Warn("process interdiction degraded to signal-based suspension",
		"reason", reason,
		"note", "active suspensions do not survive a daemon restart; graceful shutdown resumes them")
}

// suspend SIGSTOPs the target PID and records the suspension deadline
// (signal mode). The SIGSTOP is sent before recording: a process that
// exits mid-suspension leaves a stale record the reconciler's resume
// handles quietly.
func (k *BPFKernel) suspend(bk *bpfKindState, pid int, expiry time.Time) error {
	if pid < 1 || pid > maxPID {
		return fmt.Errorf("interdict key is not a PID: %d", pid)
	}
	if err := unix.Kill(pid, unix.SIGSTOP); err != nil {
		return fmt.Errorf("SIGSTOP %d: %w", pid, err)
	}
	k.mu.Lock()
	defer k.mu.Unlock()
	bk.suspended[pid] = expiry
	return nil
}

// resume SIGCONTs a suspended PID and forgets it. Missing records are
// quiet — releases are idempotent, and a process that exited while
// suspended is already gone.
func (k *BPFKernel) resume(bk *bpfKindState, pid int) error {
	k.mu.Lock()
	_, known := bk.suspended[pid]
	delete(bk.suspended, pid)
	k.mu.Unlock()
	if !known {
		return nil
	}
	if err := unix.Kill(pid, unix.SIGCONT); err != nil && !errors.Is(err, unix.ESRCH) {
		return fmt.Errorf("SIGCONT %d: %w", pid, err)
	}
	return nil
}

// cgroupIDOf resolves the cgroup v2 id of the cgroup containing pid —
// the kernfs inode number bpf_get_current_cgroup_id() reports. Requires
// cgroup v2 and a /proc that shows the target process (in containers the
// daemon must run with the host PID namespace); cgroup v1 hosts degrade
// the LSM primitive at startup instead.
func cgroupIDOf(pid int) (uint64, error) {
	data, err := os.ReadFile(fmt.Sprintf("/proc/%d/cgroup", pid))
	if err != nil {
		return 0, err
	}
	cgid, ok := parseCgroupV2ID(data)
	if !ok {
		return 0, fmt.Errorf("pid %d has no cgroup v2 entry (cgroup v1 hosts are unsupported for the LSM primitive)", pid)
	}
	return cgid, nil
}

// parseCgroupV2ID extracts the cgroup id from /proc/<pid>/cgroup content —
// v2 lines read "0::<path>" with no controller fields; v1 lines name a
// controller in field 2. Pure so the parsing rules are testable without
// /proc.
func parseCgroupV2ID(data []byte) (uint64, bool) {
	for _, line := range strings.Split(string(data), "\n") {
		parts := strings.SplitN(line, ":", 3)
		if len(parts) == 3 && parts[0] == "0" && parts[1] == "" && parts[2] != "" {
			var st unix.Stat_t
			if err := unix.Stat(parts[2], &st); err != nil {
				return 0, false
			}
			return st.Ino, true
		}
	}
	return 0, false
}

// encodeNativeU64 renders a u64 in host byte order — what the BPF programs
// compare when they look up a register value (bpf_get_current_cgroup_id())
// in the map.
func encodeNativeU64(v uint64) []byte {
	b := make([]byte, 8)
	binary.NativeEndian.PutUint64(b, v)
	return b
}

func (k *BPFKernel) MapUpdate(kind Kind, key, value []byte) (string, int, error) {
	bk, err := k.state(kind)
	if err != nil {
		return "", 0, err
	}
	norm, err := mapKeyFor(kind, key)
	if err != nil {
		return "", 0, err
	}
	expiry, err := decodeExpiry(value)
	if err != nil {
		return "", 0, err
	}
	if bk.mode == "signal" {
		// Signal fallback: the "map" is process memory — suspend the
		// target PID and record the deadline for the reconciler.
		if err := k.suspend(bk, int(binary.BigEndian.Uint64(norm)), expiry); err != nil {
			return "", 0, err
		}
		return bk.attachPoint, 0, nil
	}
	if kind == KindProcessInterdict {
		// cgroup-scoped LSM enforcement: the map key is the target PID's
		// cgroup id — what the LSM programs compare against
		// bpf_get_current_cgroup_id() — written host-native.
		cgid, err := cgroupIDOf(int(binary.BigEndian.Uint64(norm)))
		if err != nil {
			return "", 0, fmt.Errorf("resolving cgroup for interdict: %w", err)
		}
		norm = encodeNativeU64(cgid)
	}
	if err := bk.mainMap.Update(norm, uint64(expiry.Unix()), ebpf.UpdateAny); err != nil {
		return "", 0, fmt.Errorf("update %s: %w", kind.mapName(), err)
	}
	// map_slot: LRU-hash entries are identified by key, not slot; the
	// contract's evidence shape carries the field, so hash-backed entries
	// report 0. The map path and counters carry the real proof.
	return bk.mainPinPath, 0, nil
}

func (k *BPFKernel) Release(kind Kind, key []byte) error {
	bk, err := k.state(kind)
	if err != nil {
		return err
	}
	norm, err := mapKeyFor(kind, key)
	if err != nil {
		return err
	}
	if bk.mode == "signal" {
		return k.resume(bk, int(binary.BigEndian.Uint64(norm)))
	}
	if kind == KindProcessInterdict {
		// Release re-resolves the PID: an unblock acts on the cgroup the
		// target lives in now. If the process died, resolution fails and
		// the release errors — the entry expires by TTL instead; the
		// reconciler path (Evict) deletes by raw map key with no
		// resolution, so expiry never depends on the process being alive.
		cgid, err := cgroupIDOf(int(binary.BigEndian.Uint64(norm)))
		if err != nil {
			return fmt.Errorf("resolving cgroup for interdict release: %w", err)
		}
		norm = encodeNativeU64(cgid)
	}
	if err := bk.mainMap.Delete(norm); err != nil && !errors.Is(err, ebpf.ErrKeyNotExist) {
		return fmt.Errorf("delete %s: %w", kind.mapName(), err)
	}
	// An absent key is quiet: releases are idempotent at the kernel level,
	// matching libbpf's ENOENT and the FakeKernel.
	return nil
}

func (k *BPFKernel) Capability(kind Kind) Capability {
	k.mu.Lock()
	defer k.mu.Unlock()
	return k.caps[kind]
}

func (k *BPFKernel) Stats(kind Kind) (Stats, error) {
	bk, err := k.state(kind)
	if err != nil {
		return Stats{}, err
	}
	if bk.mode == "signal" {
		// No in-kernel counter exists in signal mode — the truthful read
		// is zero denials; occupancy is the suspended-process count.
		k.mu.Lock()
		occupancy := len(bk.suspended)
		k.mu.Unlock()
		return Stats{
			Counters:  map[string]uint64{bpfCounterMaps[kind]: 0},
			Occupancy: occupancy,
		}, nil
	}
	var cpus []uint64
	if err := bk.counterMap.Lookup(uint32(0), &cpus); err != nil {
		return Stats{}, fmt.Errorf("read %s counter: %w", bk.counterName, err)
	}
	var total uint64
	for _, v := range cpus {
		total += v
	}
	occupancy, err := mapOccupancy(bk)
	if err != nil {
		return Stats{}, err
	}
	return Stats{
		Counters:  map[string]uint64{bk.counterName: total},
		Occupancy: occupancy,
	}, nil
}

// mapOccupancy counts the live entries in the kind's pinned map.
func mapOccupancy(bk *bpfKindState) (int, error) {
	it := bk.mainMap.Iterate()
	key := make([]byte, bk.keySize)
	var val uint64
	total := 0
	for it.Next(&key, &val) {
		total++
	}
	return total, it.Err()
}

// Entries implements mapStore over the real pinned maps.
func (k *BPFKernel) Entries(kind Kind) ([]MapEntry, error) {
	bk, err := k.state(kind)
	if err != nil {
		if errors.Is(err, errKindNotLoaded) {
			// An unloaded primitive holds no enforcement entries —
			// nothing to enumerate or evict. Returning an error here
			// aborts the reconciler's whole sweep whenever any one
			// optional kind is degraded (e.g. no sink configured).
			return []MapEntry{}, nil
		}
		return nil, err
	}
	if bk.mode == "signal" {
		// Signal fallback: the entries live in process memory; keys are
		// the engine's big-endian PID encoding, so Evict round-trips.
		k.mu.Lock()
		defer k.mu.Unlock()
		out := []MapEntry{}
		for pid, deadline := range bk.suspended {
			b := make([]byte, 8)
			binary.BigEndian.PutUint64(b, uint64(pid))
			out = append(out, MapEntry{Key: b, Expiry: deadline})
		}
		return out, nil
	}
	it := bk.mainMap.Iterate()
	out := []MapEntry{}
	key := make([]byte, bk.keySize)
	var val uint64
	for it.Next(&key, &val) {
		if val == 0 {
			return nil, fmt.Errorf("%s: entry with zero expiry", kind)
		}
		out = append(out, MapEntry{
			Key:    append([]byte(nil), key...),
			Expiry: time.Unix(int64(val), 0).UTC(),
		})
	}
	if err := it.Err(); err != nil {
		return nil, err
	}
	return out, nil
}

// Evict implements mapStore. For the interdict kind the reconciler hands
// back the raw map key — a cgroup id (BPF mode) or a PID (signal mode) —
// which must be evicted directly, never re-resolved from the engine's
// target encoding: expiry must not depend on the process being alive.
// For the other kinds eviction is a plain Release (keys are identical).
func (k *BPFKernel) Evict(kind Kind, key []byte) error {
	if kind != KindProcessInterdict {
		return k.Release(kind, key)
	}
	bk, err := k.state(kind)
	if err != nil {
		return err
	}
	if bk.mode == "signal" {
		return k.resume(bk, int(binary.BigEndian.Uint64(key)))
	}
	if err := bk.mainMap.Delete(key); err != nil && !errors.Is(err, ebpf.ErrKeyNotExist) {
		return fmt.Errorf("delete %s: %w", kind.mapName(), err)
	}
	return nil
}

// Reconcile refreshes the datapath clock and evicts expired entries. main
// runs it on a ticker; the interval only bounds capacity reclaim and clock
// drift — enforcement self-expires without it.
func (k *BPFKernel) Reconcile(now time.Time) (int, error) {
	if err := k.refreshClock(); err != nil {
		return 0, fmt.Errorf("clock refresh: %w", err)
	}
	return (&Reconciler{Store: k}).ReconcileExpired(now)
}

// refreshClock rewrites every loaded object's clock_offset. The BPF programs
// derive wall time as bpf_ktime_get_ns() + offset (both are CLOCK_MONOTONIC
// based), so a block's unix-seconds expiry stays comparable to the wall
// clock — including on a daemon that never ticks again.
func (k *BPFKernel) refreshClock() error {
	var ts unix.Timespec
	if err := unix.ClockGettime(unix.CLOCK_MONOTONIC, &ts); err != nil {
		return err
	}
	ktimeNS := ts.Sec*1_000_000_000 + int64(ts.Nsec)
	offset := uint64(int64(time.Now().UnixNano()) - ktimeNS)
	k.mu.Lock()
	defer k.mu.Unlock()
	for kind, bk := range k.kinds {
		if bk.offsetMap == nil {
			continue
		}
		if err := bk.offsetMap.Update(uint32(0), offset, ebpf.UpdateAny); err != nil {
			return fmt.Errorf("%s: %w", kind, err)
		}
	}
	return nil
}

// Close releases links and collections. Pinned maps persist — they are the
// kernel-side state a restart adopts. Closing the XDP link detaches the
// program on graceful shutdown; a crashed daemon leaves it attached, where
// map expiries (not the daemon) bound its effect.
func (k *BPFKernel) Close() error {
	k.mu.Lock()
	defer k.mu.Unlock()
	var errs []error
	for kind, bk := range k.kinds {
		if bk.coll == nil {
			// Signal fallback state: resume suspended processes — a
			// graceful shutdown must not leave them frozen. A crash
			// cannot resume; that limitation is documented at install.
			for pid := range bk.suspended {
				delete(bk.suspended, pid)
				if err := unix.Kill(pid, unix.SIGCONT); err != nil && !errors.Is(err, unix.ESRCH) {
					errs = append(errs, fmt.Errorf("%s: resuming pid %d: %w", kind, pid, err))
				}
			}
			continue
		}
		if bk.link != nil {
			if err := bk.link.Close(); err != nil {
				errs = append(errs, fmt.Errorf("%s: closing link: %w", kind, err))
			}
		}
		for _, l := range bk.extraLinks {
			if err := l.Close(); err != nil {
				errs = append(errs, fmt.Errorf("%s: closing link: %w", kind, err))
			}
		}
		if kind == KindSocketRedirect {
			// The sk_msg verdict attach is not a link; detach best-effort.
			if sockmap := bk.coll.Maps["sink_sockets"]; sockmap != nil {
				if err := link.RawDetachProgram(link.RawDetachProgramOptions{
					Target: sockmap.FD(), Attach: ebpf.AttachSkMsgVerdict,
				}); err != nil {
					errs = append(errs, fmt.Errorf("%s: detaching sk_msg verdict: %w", kind, err))
				}
			}
			if bk.sinkFile != nil {
				if err := bk.sinkFile.Close(); err != nil {
					errs = append(errs, fmt.Errorf("%s: closing sink fd: %w", kind, err))
				}
			}
			if bk.sinkConn != nil {
				if err := bk.sinkConn.Close(); err != nil {
					errs = append(errs, fmt.Errorf("%s: closing sink connection: %w", kind, err))
				}
			}
		}
		// Collection.Close frees the map/program fds; it returns nothing.
		bk.coll.Close()
	}
	return errors.Join(errs...)
}

func (k *BPFKernel) state(kind Kind) (*bpfKindState, error) {
	k.mu.Lock()
	defer k.mu.Unlock()
	bk, ok := k.kinds[kind]
	if !ok {
		return nil, fmt.Errorf("%s: %w", kind, errKindNotLoaded)
	}
	return bk, nil
}

var errKindNotLoaded = errors.New("primitive not loaded on this host")

// mapKeyFor normalizes the engine's key bytes to the kind's fixed map key
// width. The engine emits the minimal form (validate.go Target.key):
// 16-byte address, 16+2 with a port, 8-byte PID. A kernel map has one fixed
// key size, so the redirect map always carries 18 bytes — a 16-byte key pads
// to port 0, the wildcard.
func mapKeyFor(kind Kind, key []byte) ([]byte, error) {
	switch kind {
	case KindXDPDrop:
		if len(key) != 16 {
			return nil, fmt.Errorf("xdp_drop key is %d bytes, want 16", len(key))
		}
		return key, nil
	case KindSocketRedirect:
		switch len(key) {
		case 16:
			out := make([]byte, 18)
			copy(out, key)
			return out, nil
		case 18:
			return key, nil
		default:
			return nil, fmt.Errorf("socket_redirect key is %d bytes, want 16 or 18", len(key))
		}
	case KindProcessInterdict:
		if len(key) != 8 {
			return nil, fmt.Errorf("process_interdict key is %d bytes, want 8", len(key))
		}
		return key, nil
	}
	return nil, fmt.Errorf("unknown kind %s", kind)
}

// probeReason renders a load/attach failure as a capability reason — the
// string an operator sees in /healthz when a primitive is degraded.
func probeReason(err error, subject string) string {
	switch {
	case errors.Is(err, os.ErrNotExist):
		return subject + ": object not found (build with build-bpf.sh)"
	case errors.Is(err, unix.EPERM), errors.Is(err, os.ErrPermission):
		return subject + ": insufficient capabilities (needs CAP_BPF, CAP_NET_ADMIN, and CAP_SYS_ADMIN for BPF LSM)"
	case errors.Is(err, unix.ENOSPC):
		return subject + ": kernel rejected the program (verifier or map limits)"
	default:
		return subject + ": " + err.Error()
	}
}
