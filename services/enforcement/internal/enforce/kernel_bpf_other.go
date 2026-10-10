//go:build !linux

package enforce

import (
	"errors"
	"log/slog"
)

// BPFConfig is shared with the Linux loader (see kernel_bpf.go).
type BPFConfig struct {
	// Interface is the NIC the XDP program attaches to.
	Interface string
	// ObjectsDir holds the compiled CO-RE objects (build-bpf.sh output).
	ObjectsDir string
	// CgroupPath is a cgroupv2 directory for the LSM/sockops hooks.
	CgroupPath string
}

var errNotLinux = errors.New("the enforcement loader requires Linux")

// BPFKernel exists only so the !linux build has a return type; it can never
// enforce.
type BPFKernel struct{}

// NewBPFKernel is only implemented for Linux. Construction fails loudly
// rather than faking: a host that cannot reach the kernel must never serve
// an enforcement API that pretends it did.
func NewBPFKernel(cfg BPFConfig, log *slog.Logger) (*BPFKernel, error) {
	return nil, errNotLinux
}

// The methods below make *BPFKernel satisfy enforce.Kernel on the !linux
// build. They are unreachable: NewBPFKernel always fails and the daemon
// exits before any enforcement path runs. Each fails loudly anyway — a
// silent success here would be enforcement that never happened.
func (k *BPFKernel) Attach(kind Kind) (string, error) { return "", errNotLinux }

func (k *BPFKernel) MapUpdate(kind Kind, key, value []byte) (string, int, error) {
	return "", 0, errNotLinux
}

func (k *BPFKernel) Release(kind Kind, key []byte) error { return errNotLinux }

func (k *BPFKernel) Capability(kind Kind) Capability {
	return Capability{Reason: "the enforcement loader requires Linux"}
}

func (k *BPFKernel) Stats(kind Kind) (Stats, error) { return Stats{}, errNotLinux }

// Close is a no-op on the non-Linux stub.
func (k *BPFKernel) Close() error { return nil }
