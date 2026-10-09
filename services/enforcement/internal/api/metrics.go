package api

import (
	"fmt"
	"net/http"
	"sort"
	"strings"
	"time"

	"github.com/jvlatacc/vigil/services/enforcement/internal/enforce"
)

// healthzDoc is the /healthz payload: per-primitive capability fields as the
// spec requires, so degradation is observable before the first enforcement.
type healthzDoc struct {
	Status          string               `json:"status"`
	UptimeSeconds   int64                `json:"uptime_seconds"`
	Kernel          string               `json:"kernel_faked"`
	Primitives      map[string]primitive `json:"primitives"`
	ActionsEnforced uint64               `json:"actions_enforced"`
	ActionsReleased uint64               `json:"actions_released"`
}

type primitive struct {
	Supported bool   `json:"supported"`
	Reason    string `json:"reason,omitempty"`
}

// handleHealthz implements GET /healthz. Status is "ok" only while every
// primitive is supported; any unsupported primitive marks the daemon
// "degraded" — per-primitive degradation must be visible, never masked
// (spec: the daemon degrades per primitive instead of failing whole).
func (s *Server) handleHealthz(w http.ResponseWriter, r *http.Request) {
	prims := make(map[string]primitive, 3)
	allSupported := true
	for _, kind := range enforce.Kinds() {
		capability := s.enf.Capability(kind)
		prims[string(kind)] = primitive{Supported: capability.Supported, Reason: capability.Reason}
		if !capability.Supported {
			allSupported = false
		}
	}
	status := "ok"
	if !allSupported {
		status = "degraded"
	}
	writeJSON(w, http.StatusOK, healthzDoc{
		Status:          status,
		UptimeSeconds:   int64(time.Since(s.started) / time.Second),
		Kernel:          s.kernelFaked,
		Primitives:      prims,
		ActionsEnforced: s.enforcedTotal.Load(),
		ActionsReleased: s.releasedTotal.Load(),
	})
}

// handleMetrics implements GET /metrics in Prometheus text format, version
// 0.0.4. Per-kind drop/redirect counters and map occupancy are the spec's
// named series; they are also the "counter that ticks" proof of enforcement.
func (s *Server) handleMetrics(w http.ResponseWriter, r *http.Request) {
	var b strings.Builder
	seen := map[string]bool{}
	occupancy := []string{} // one labeled sample per kind, written once below
	for _, kind := range enforce.Kinds() {
		stats, err := s.enf.Stats(kind)
		if err != nil {
			// A kernel read failure must not fake zeroed counters; skip the
			// series and count the scrape error.
			s.errorTotal.Add(1)
			continue
		}
		names := make([]string, 0, len(stats.Counters))
		for name := range stats.Counters {
			names = append(names, name)
		}
		sort.Strings(names)
		for _, name := range names {
			series := fmt.Sprintf("vigil_enforcement_%s", name)
			if !seen[series] {
				seen[series] = true
				fmt.Fprintf(&b, "# HELP %s Data-path counter reported by the enforcement kernel.\n", series)
				fmt.Fprintf(&b, "# TYPE %s counter\n", series)
			}
			fmt.Fprintf(&b, "%s{kind=\"%s\"} %d\n", series, kind, stats.Counters[name])
		}
		occupancy = append(occupancy, fmt.Sprintf("vigil_enforcement_map_entries{kind=%q} %d\n", kind, stats.Occupancy))
	}
	// One HELP/TYPE block per metric name: a repeated definition is a
	// Prometheus scrape error, so all kinds' samples share one block.
	fmt.Fprintf(&b, "# HELP vigil_enforcement_map_entries Kernel map entries in use.\n")
	fmt.Fprintf(&b, "# TYPE vigil_enforcement_map_entries gauge\n")
	for _, line := range occupancy {
		b.WriteString(line)
	}
	fmt.Fprintf(&b, "# HELP vigil_enforcement_actions_enforced Enforcement actions applied.\n")
	fmt.Fprintf(&b, "# TYPE vigil_enforcement_actions_enforced counter\n")
	fmt.Fprintf(&b, "vigil_enforcement_actions_enforced %d\n", s.enforcedTotal.Load())
	fmt.Fprintf(&b, "# HELP vigil_enforcement_actions_replayed Idempotent replay responses served.\n")
	fmt.Fprintf(&b, "# TYPE vigil_enforcement_actions_replayed counter\n")
	fmt.Fprintf(&b, "vigil_enforcement_actions_replayed %d\n", s.replayedTotal.Load())
	fmt.Fprintf(&b, "# HELP vigil_enforcement_actions_released Enforcement actions released.\n")
	fmt.Fprintf(&b, "# TYPE vigil_enforcement_actions_released counter\n")
	fmt.Fprintf(&b, "vigil_enforcement_actions_released %d\n", s.releasedTotal.Load())
	fmt.Fprintf(&b, "# HELP vigil_enforcement_requests_rejected Requests refused (auth, validation, conflict).\n")
	fmt.Fprintf(&b, "# TYPE vigil_enforcement_requests_rejected counter\n")
	fmt.Fprintf(&b, "vigil_enforcement_requests_rejected %d\n", s.rejectedTotal.Load()+s.errorTotal.Load())
	w.Header().Set("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
	_, _ = w.Write([]byte(b.String()))
}
