#!/bin/sh
# Compiles Vigil's CO-RE BPF objects (bpf/*.c) into bpf/build/<name>.o —
# what the Go loader (internal/enforce/kernel_bpf.go) loads at runtime.
#
# Build-time requirements only; the protected host needs nothing:
#   clang >= 11 with the BPF backend, and libbpf headers for
#   bpf/bpf_helpers.h. On Debian/Ubuntu: apt install clang libbpf-dev.
# The enforcer Dockerfile's builder stage runs this script (packaging PR);
# the runtime image ships only the compiled objects — no clang, no kernel
# headers at runtime (spec).
set -eu
cd "$(dirname "$0")"

mkdir -p bpf/build

# Debian/Ubuntu put asm/types.h under a multiarch triplet; the BPF target
# needs it on the include path. Harmless when the directory is absent.
ARCH_INCLUDE="/usr/include/$(uname -m)-linux-gnu"
[ -d "$ARCH_INCLUDE" ] && ARCH_INCLUDE_FLAG="-I$ARCH_INCLUDE" || ARCH_INCLUDE_FLAG=""

for src in bpf/*.c; do
	out="bpf/build/$(basename "${src%.c}").o"
	echo "clang: $src -> $out"
	# -g keeps BTF, which the Go loader uses for map/program introspection;
	# the plain UAPI includes need no kernel build tree or vmlinux.h.
	clang -target bpf -O2 -g -Wall -Wextra -Wno-unused-parameter \
		$ARCH_INCLUDE_FLAG \
		-c "$src" -o "$out"
done
