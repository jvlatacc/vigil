// vigil_common.h — shared definitions for Vigil's CO-RE BPF programs.
//
// Conventions pinned by the Go engine (internal/enforce):
//   - Map keys: 16-byte address (IPv4 written v4-mapped ::ffff:a.b.c.d, so
//     one shape serves both families), 16+2 bytes when a port is present,
//     8-byte PID.
//   - Map values: 8-byte native-endian unix-seconds expiry — the same bytes
//     the engine writes (expiryValue); the datapath reads them directly.
//   - Every object embeds its own clock_offset map (key 0): the loader
//     refreshes it with unix_nanos - ktime_nanos, so the datapath derives
//     wall time as bpf_ktime_get_ns() + offset (both are CLOCK_MONOTONIC
//     based). A missing offset fails open — a bookkeeping failure must
//     never turn into an unbounded block.
//
// Programs compile with plain UAPI headers (linux/bpf.h et al.): every
// struct they touch is UAPI-stable, so no generated vmlinux.h is needed.
// build-bpf.sh owns the compile; objects are image content, never compiled
// on the protected host.
#ifndef VIGIL_COMMON_H
#define VIGIL_COMMON_H

#include <linux/bpf.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_endian.h>

/* 16-byte address key: IPv4 in v4-mapped form, IPv6 verbatim. */
struct vigil_ip {
	__u8 bytes[16];
};

/* IP + port for the socket-redirect map (18 bytes, the engine's key shape). */
struct vigil_ipport {
	__u8 ip[16];
	__be16 port;
};

/* The loader-fed wall clock: key 0 -> unix_nanos - ktime_nanos. */
struct {
	__uint(type, BPF_MAP_TYPE_ARRAY);
	__uint(max_entries, 1);
	__type(key, __u32);
	__type(value, __u64);
} clock_offset SEC(".maps");

/*
 * vigil_blocked reports whether the entry at @key is still in force: present
 * in the map and not past its expiry. An expired or missing entry, or an
 * unfed clock, returns 0 — the datapath passes and (for present-but-expired
 * entries) enforcement has self-expired without a controller.
 */
static __always_inline int vigil_blocked(void *map, const void *key)
{
	__u64 *expiry = bpf_map_lookup_elem(map, key);
	if (!expiry)
		return 0;
	__u32 zero = 0;
	__u64 *offset = bpf_map_lookup_elem(&clock_offset, &zero);
	if (!offset)
		return 0; /* no clock from the loader: fail open */
	__u64 now_unix_ns = bpf_ktime_get_ns() + *offset;
	/* unix seconds ~1.8e9 * 1e9 = 1.8e18, well inside u64. */
	return now_unix_ns < *expiry * 1000000000ULL;
}

/* vigil_v4_mapped renders an IPv4 source address in the engine's 16-byte
 * v4-mapped key form (a plain byte copy — saddr is already network order). */
static __always_inline void vigil_v4_mapped(struct vigil_ip *dst, __be32 saddr)
{
	__builtin_memset(dst, 0, sizeof(*dst));
	dst->bytes[10] = 0xff;
	dst->bytes[11] = 0xff;
	__builtin_memcpy(&dst->bytes[12], &saddr, 4);
}

#endif /* VIGIL_COMMON_H */
