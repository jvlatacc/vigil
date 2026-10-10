package main

import (
	"log/slog"
	"net"
	"testing"

	"github.com/jvlatacc/vigil/services/enforcement/internal/enforce"
)

func testLogger() *slog.Logger {
	return slog.New(slog.NewTextHandler(testWriter{}, nil))
}

// testWriter discards slog output so wireSink's degradation warnings do not
// clutter test output.
type testWriter struct{}

func (testWriter) Write(p []byte) (int, error) { return len(p), nil }

// wireSink is the startup seam between the sink address and the kernel's
// optional SinkSetter/Degrader: no sink or an undialable sink degrades the
// redirect primitive instead of letting the engine report enforcement that
// steers nothing.
func TestWireSinkDegradesWithoutSink(t *testing.T) {
	fk := enforce.NewFakeKernel("eth0")
	wireSink(testLogger(), fk, "")

	cap := fk.Capability(enforce.KindSocketRedirect)
	if cap.Supported {
		t.Error("redirect must be degraded with no sink configured")
	}
	if fk.SinkConn() != nil {
		t.Error("no sink was configured, but the kernel holds a sink connection")
	}
}

func TestWireSinkConnectsAndSets(t *testing.T) {
	l, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listener: %v", err)
	}
	defer l.Close()
	go func() {
		for {
			conn, err := l.Accept()
			if err != nil {
				return
			}
			_ = conn.Close()
		}
	}()

	fk := enforce.NewFakeKernel("eth0")
	wireSink(testLogger(), fk, l.Addr().String())

	if fk.SinkConn() == nil {
		t.Fatal("wireSink did not hand the dialed connection to the kernel")
	}
	cap := fk.Capability(enforce.KindSocketRedirect)
	if !cap.Supported {
		t.Errorf("redirect capability = %+v, want supported", cap)
	}
}

func TestWireSinkDegradesWhenUnreachable(t *testing.T) {
	// Port 1 on loopback: nothing listens there.
	fk := enforce.NewFakeKernel("eth0")
	wireSink(testLogger(), fk, "127.0.0.1:1")

	cap := fk.Capability(enforce.KindSocketRedirect)
	if cap.Supported {
		t.Error("redirect must be degraded when the sink dial fails")
	}
	if fk.SinkConn() != nil {
		t.Error("the kernel must not hold a sink connection from a failed dial")
	}
}
