//go:build linux

package enforce

import (
	"errors"
	"fmt"
	"log/slog"
	"net"
	"os"
	"path/filepath"
	"sync"
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
	default:
		return fmt.Errorf("no attach implementation for kind %s (its object ships with a later primitive)", kind)
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
		return nil, err
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

// Evict implements mapStore; eviction at map level is a Release.
func (k *BPFKernel) Evict(kind Kind, key []byte) error {
	return k.Release(kind, key)
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
