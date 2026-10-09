// socket_redirect.c — Vigil's socket-level steer-to-sink primitive.
//
// Steers host-initiated TCP flows toward an enforced target into a sink
// socket (a tarpit or capture listener) instead of dropping them, so the
// traffic is preserved for forensics. Mechanics:
//
//   - socket_redir_v1: enforcement entries, keyed by the engine's 18-byte
//     {remote addr, remote port} shape (v4-mapped IPv6 for IPv4), value =
//     unix-seconds expiry — the same bytes the engine writes (expiryValue).
//   - sink_sockets: one sockmap, two roles. Index 0 is the sink, inserted
//     by the daemon from a connected socket to the configured sink address.
//     Indexes >= 1 are sockets enrolled by the sockops hook below.
//   - vigil_sock_enroll (sockops): when a host connection to an enforced
//     {ip, port} is established, enroll the socket into the sockmap.
//   - vigil_sk_msg_redirect (sk_msg): verdict program on enrolled sockets'
//     messages — matching flows are spliced to the sink via
//     bpf_msg_redirect_map (SOCKMAP at index 0); everything else passes.
//
// v1 scope: host-INITIATED flows only (ACTIVE_ESTABLISHED_CB). Steering
// inbound connections would key entries by (remote ip, local port) and
// needs the PASSIVE callback — a documented extension.
//
// Fail-open discipline: an expired entry, an empty map, or an unfed clock
// passes traffic unsteered — a bookkeeping failure must never blackhole a
// flow. The sink socket itself is unaffected: only enrolled member sockets'
// messages are candidates for redirection.
#include "vigil_common.h"

/* Stable UAPI values (asm-generic/socket.h); not pulled in by linux/bpf.h. */
#ifndef SOCK_STREAM
#define SOCK_STREAM 1
#endif
#ifndef AF_INET
#define AF_INET 2
#endif

/* Enforcement entries: {remote ip, remote port} -> expiry (unix seconds). */
struct {
	__uint(type, BPF_MAP_TYPE_LRU_HASH);
	__uint(max_entries, 65536);
	__type(key, struct vigil_ipport);
	__type(value, __u64);
} socket_redir_v1 SEC(".maps");

/* Index 0: sink (daemon-inserted). Indexes >= 1: enrolled sockets. */
struct {
	__uint(type, BPF_MAP_TYPE_SOCKMAP);
	__uint(max_entries, 64);
	__type(key, __u32);
	__type(value, int);
} sink_sockets SEC(".maps");

/* Per-CPU round-robin over member slots 1..max-1 (slot 0 is the sink). */
struct {
	__uint(type, BPF_MAP_TYPE_PERCPU_ARRAY);
	__uint(max_entries, 1);
	__type(key, __u32);
	__type(value, __u64);
} member_rr SEC(".maps");

/* Redirected-message counter — per-CPU, loader-read (redirected_packets). */
struct {
	__uint(type, BPF_MAP_TYPE_PERCPU_ARRAY);
	__uint(max_entries, 1);
	__type(key, __u32);
	__type(value, __u64);
} redirected_packets SEC(".maps");

static __always_inline int vigil_enforced(struct vigil_ipport *key)
{
	return vigil_blocked(&socket_redir_v1, key);
}

/* The engine's key: 16-byte address then the port's network-order bytes.
 * The port fields (bpf_sock_ops.remote_port, sk_msg_md.remote_port) are
 * "stored in network byte order" UAPI u32s — copying their first two bytes
 * is byte-exact for the __be16 key with no endianness arithmetic. */
static __always_inline void vigil_fill_key(struct vigil_ipport *k,
					   const __u8 *addr16, const void *port_be)
{
	__builtin_memcpy(k->ip, addr16, 16);
	__builtin_memcpy(&k->port, port_be, 2);
}

/* Round-robin member slot; collisions overwrite (benign: the verdict still
 * applies per-message, and the next enrollment re-enrolls the socket). */
static __always_inline __u32 vigil_next_slot(void)
{
	__u32 zero = 0;
	__u64 *rr = bpf_map_lookup_elem(&member_rr, &zero);
	if (!rr)
		return 1;
	__u64 n = *rr;
	*rr = n + 1;
	return 1 + (__u32)((n % (64 - 1)));
}

SEC("sockops")
int vigil_sock_enroll(struct bpf_sock_ops *skops)
{
	struct vigil_ipport k;
	__u8 addr[16];
	__u32 slot;

	if (skops->op != BPF_SOCK_OPS_ACTIVE_ESTABLISHED_CB)
		return 0;
	/* Sockmaps are stream-only; established callbacks fire on TCP only. */
	if (skops->family == AF_INET)
		vigil_v4_mapped((struct vigil_ip *)addr, skops->remote_ip4);
	else
		__builtin_memcpy(addr, skops->remote_ip6, 16);
	vigil_fill_key(&k, addr, &skops->remote_port);
	if (!vigil_enforced(&k))
		return 0;
	slot = vigil_next_slot();
	bpf_sock_map_update(skops, &sink_sockets, &slot, 0 /* BPF_ANY */);
	return 0;
}

SEC("sk_msg")
int vigil_sk_msg_redirect(struct sk_msg_md *msg)
{
	struct vigil_ipport k;
	__u8 addr[16];
	__u32 zero = 0;
	__u64 *drops;

	if (msg->family == AF_INET)
		vigil_v4_mapped((struct vigil_ip *)addr, msg->remote_ip4);
	else
		__builtin_memcpy(addr, msg->remote_ip6, 16);
	vigil_fill_key(&k, addr, &msg->remote_port);
	if (!vigil_enforced(&k))
		return SK_PASS;
	/* Redirect the message into the sink socket at index 0; SK_PASS is
	 * the verdict that forwards the (redirected) message. */
	bpf_msg_redirect_map(msg, &sink_sockets, zero, BPF_F_INGRESS);
	drops = bpf_map_lookup_elem(&redirected_packets, &zero);
	if (drops)
		__sync_fetch_and_add(drops, 1);
	return SK_PASS;
}

char LICENSE[] SEC("license") = "GPL";
