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
}

// BPFKernel exists only so the !linux build has a return type; it can never
// enforce.
type BPFKernel struct{}

// NewBPFKernel is only implemented for Linux. Construction fails loudly
// rather than faking: a host that cannot reach the kernel must never serve
// an enforcement API that pretends it did.
func NewBPFKernel(cfg BPFConfig, log *slog.Logger) (*BPFKernel, error) {
	return nil, errors.New("the enforcement loader requires Linux")
}

// Close is a no-op on the non-Linux stub.
func (k *BPFKernel) Close() error { return nil }
