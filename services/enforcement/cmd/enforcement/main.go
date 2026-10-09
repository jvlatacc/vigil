// Command enforcement is Vigil's per-host kernel enforcement daemon. It
// serves the token-authed /v1 enforcement API plus /healthz and /metrics.
//
// This skeleton runs on the faked kernel; the cilium/ebpf loader lands in
// the next PR behind the same internal/enforce.Kernel seam. Bind loopback by
// default — the API can move kernel state, so it must never face a network.
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

	kernel, loader := newKernel(log, iface)
	enf := enforce.NewEnforcer(kernel, defaultTTL(log))
	srv, err := api.New(token, enf)
	if err != nil {
		log.Error("daemon startup failed", "err", err)
		os.Exit(1)
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
		"kernel_loader", loader,
		"default_ttl_seconds", int(defaultTTL(log)/time.Second),
	)
	if err := httpSrv.ListenAndServe(); err != nil {
		log.Error("listener stopped", "err", err)
		os.Exit(1)
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

// newKernel returns the kernel seam implementation and a label for the
// startup log. The faked kernel is this PR's implementation; the real
// cilium/ebpf loader replaces this constructor in the next PR.
func newKernel(log *slog.Logger, iface string) (enforce.Kernel, string) {
	log.Info("using faked kernel — kernel enforcement is NOT active; loader lands in the next PR", "interface", iface)
	return enforce.NewFakeKernel(iface), "faked"
}
