// xdp_drop.c — Vigil's XDP packet-drop primitive (kind xdp_drop).
//
// An LRU hash map holds the blocked source IPs (16-byte form) with an
// expiry timestamp as the value; the XDP program returns XDP_DROP in the
// driver for any packet whose source is blocked and unexpired, and
// XDP_PASS otherwise. Enforcement is entirely map-driven: attaching with an
// empty map changes no verdicts, and a block self-expires when its
// timestamp passes even if the daemon is gone (the Go TTL reconciler only
// reclaims the slot).
//
// No VLAN unwinding in v1: 802.1Q-tagged traffic passes unfiltered —
// documented in runbook.md.
#include <linux/bpf.h>
#include <linux/if_ether.h>
#include <linux/ip.h>
#include <linux/ipv6.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_endian.h>

#include "vigil_common.h"

/* xdp_block_v1: source IP (16-byte form) -> unix-seconds expiry. Pinned at
 * /sys/fs/bpf/vigil/xdp_block_v1 by the loader; adopted across restarts. */
struct {
	__uint(type, BPF_MAP_TYPE_LRU_HASH);
	__uint(max_entries, 65536);
	__type(key, struct vigil_ip);
	__type(value, __u64);
} xdp_block_v1 SEC(".maps");

/* Per-CPU drop counter: /metrics vigil_xdp_drop_dropped_packets_total. */
struct {
	__uint(type, BPF_MAP_TYPE_PERCPU_ARRAY);
	__uint(max_entries, 1);
	__type(key, __u32);
	__type(value, __u64);
} dropped_packets SEC(".maps");

static __always_inline void bump_drops(void)
{
	__u32 zero = 0;
	__u64 *drops = bpf_map_lookup_elem(&dropped_packets, &zero);
	if (drops)
		__sync_fetch_and_add(drops, 1);
}

SEC("xdp")
int vigil_xdp_drop(struct xdp_md *ctx)
{
	void *data = (void *)(long)ctx->data;
	void *data_end = (void *)(long)ctx->data_end;

	struct ethhdr *eth = data;
	if ((void *)(eth + 1) > data_end)
		return XDP_PASS;

	struct vigil_ip src;
	if (eth->h_proto == bpf_htons(ETH_P_IP)) {
		struct iphdr *ip = (void *)(eth + 1);
		if ((void *)(ip + 1) > data_end)
			return XDP_PASS;
		vigil_v4_mapped(&src, ip->saddr);
	} else if (eth->h_proto == bpf_htons(ETH_P_IPV6)) {
		struct ipv6hdr *ip6 = (void *)(eth + 1);
		if ((void *)(ip6 + 1) > data_end)
			return XDP_PASS;
		__builtin_memcpy(src.bytes, &ip6->saddr, sizeof(src.bytes));
	} else {
		return XDP_PASS;
	}

	if (vigil_blocked(&xdp_block_v1, &src)) {
		bump_drops();
		return XDP_DROP;
	}
	return XDP_PASS;
}

char LICENSE[] SEC("license") = "GPL";
