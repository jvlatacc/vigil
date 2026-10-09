// Command enforcement is Vigil's per-host kernel enforcement daemon. It
// loads the CO-RE BPF objects with cilium/ebpf and serves the token-authed
// /v1 enforcement API plus /healthz and /metrics.
//
// The real loader is the default; VIGIL_ENFORCEMENT_KERNEL=fake serves the
// faked kernel for dev and CI. Bind loopback by default — the API can move
// kernel state, so it must never face a network.
package main

import (
	"log/slog"
	"net"
	"net/http"
	"os"
	"strconv"
	"time"

	"github.com/jvlatacc/vigil/services/enforcement/internal/api"
	"github.com/jvlatacc/vigil/services/enforcement/internal/enforce"
)

// defaultPort is loopback 6986 — no repo service uses it. The bind address
// override exists for deployments that front the API with a local proxy.
const defaultPort = 6986

// reconcileInterval bounds LRU-capacity reclaim and clock-offset drift. The
// BPF programs ignore expired entries on their own — this loop reclaims
// their slots and keeps the wall-clock offset fresh.
const reconcileInterval = 15 * time.Second

// reconciler is the ticker-facing shape of a kernel whose maps need
// maintenance (the real loader); the faked kernel does not implement it.
type reconciler interface {
	Reconcile(time.Time) (int, error)
}

func main() {
	log := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))

	token := os.Getenv("VIGIL_ENFORCEMENT_TOKEN")
	if token == "" {
		log.Error("VIGIL_ENFORCEMENT_TOKEN is not set — refusing to serve an unauthenticated enforcement API")
		os.Exit(1)
	}

	addr := net.JoinHostPort("127.0.0.1", strconv.Itoa(defaultPort))
	if raw := os.Getenv("VIGIL_ENFORCEMENT_BIND"); raw != "" {
		addr = raw
	}
	iface := os.Getenv("VIGIL_ENFORCEMENT_INTERFACE")
	if iface == "" {
		iface = "eth0"
	}
	objectsDir := os.Getenv("VIGIL_ENFORCEMENT_BPF_DIR")
	if objectsDir == "" {
		objectsDir = "bpf"
	}

	kernel, kernelFaked, closer := newKernel(log, iface, objectsDir)
	defer closer()
	enf := enforce.NewEnforcer(kernel, defaultTTL(log))
	srv, err := api.New(token, enf, kernelFaked)
	if err != nil {
		log.Error("daemon startup failed", "err", err)
		os.Exit(1)
	}

	stop := make(chan struct{})
	defer close(stop)
	if rec, ok := kernel.(reconciler); ok {
		go reconcileLoop(log, rec, stop)
	}

	httpSrv := &http.Server{
		Addr:              addr,
		Handler:           srv.Handler(),
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       10 * time.Second,
		WriteTimeout:      10 * time.Second,
		IdleTimeout:       60 * time.Second,
	}

	log.Info("enforcement daemon listening",
		"addr", addr,
		"interface", iface,
		"kernel_loader", loaderName(kernelFaked),
		"default_ttl_seconds", int(defaultTTL(log)/time.Second),
	)
	if err := httpSrv.ListenAndServe(); err != nil {
		log.Error("listener stopped", "err", err)
		os.Exit(1)
	}
}

// newKernel selects the kernel seam implementation: the real cilium/ebpf
// loader by default, the faked kernel only when explicitly requested
// (VIGIL_ENFORCEMENT_KERNEL=fake — dev and CI). kernelFaked is what
// /healthz reports in kernel_faked so a faked kernel can never be mistaken
// for enforcement; an empty label means a real loader. A loader that cannot
// reach the kernel at all (no bpffs) is fatal — faking it silently would
// serve an enforcement API that enforces nothing.
func newKernel(log *slog.Logger, iface, objectsDir string) (enforce.Kernel, string, func()) {
	switch os.Getenv("VIGIL_ENFORCEMENT_KERNEL") {
	case "fake", "faked":
		log.Warn("using faked kernel — kernel enforcement is NOT active (VIGIL_ENFORCEMENT_KERNEL=fake)", "interface", iface)
		return enforce.NewFakeKernel(iface), "faked", func() {}
	default:
		k, err := enforce.NewBPFKernel(enforce.BPFConfig{Interface: iface, ObjectsDir: objectsDir}, log)
		if err != nil {
			log.Error("kernel loader unavailable — refusing to serve an enforcement API without a kernel",
				"err", err,
				"hint", "VIGIL_ENFORCEMENT_KERNEL=fake serves a faked kernel for dev/CI")
			os.Exit(1)
		}
		return k, "", func() { _ = k.Close() }
	}
}

// loaderName renders the startup-log label; the healthz label stays empty
// for the real loader so faked enforcement is the only distinguishable case.
func loaderName(kernelFaked string) string {
	if kernelFaked != "" {
		return "faked"
	}
	return "bpf"
}

func reconcileLoop(log *slog.Logger, rec reconciler, stop <-chan struct{}) {
	t := time.NewTicker(reconcileInterval)
	defer t.Stop()
	for {
		select {
		case <-stop:
			return
		case now := <-t.C:
			evicted, err := rec.Reconcile(now)
			if err != nil {
				log.Warn("reconcile tick failed", "err", err)
				continue
			}
			if evicted > 0 {
				log.Info("evicted expired enforcement entries", "count", evicted)
			}
		}
	}
}

// defaultTTL fills requests that omit ttl_seconds — 1h, overridden by env.
func defaultTTL(log *slog.Logger) time.Duration {
	const fallback = 3600
	if raw := os.Getenv("VIGIL_ENFORCEMENT_DEFAULT_TTL_SECONDS"); raw != "" {
		if n, err := strconv.Atoi(raw); err == nil && n > 0 {
			return time.Duration(n) * time.Second
		}
		log.Warn("invalid VIGIL_ENFORCEMENT_DEFAULT_TTL_SECONDS; using default", "value", raw, "default_seconds", fallback)
	}
	return time.Duration(fallback) * time.Second
}
