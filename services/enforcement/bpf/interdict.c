// interdict.c — Vigil's process interdiction primitive (BPF LSM).
//
// Denies connect(2) and execve(2) for every process in an enforced
// cgroup: the daemon resolves the target PID's cgroup v2 ID (the kernfs
// inode bpf_get_current_cgroup_id() reports) and writes it as the map
// key, so the denial is cgroup-scoped — it covers threads and children
// in the same cgroup, and survives short PID reuse of the original
// target. Enforcement entries:
//
//   - interdict_v1: cgroup id (__u64, native order — both sides handle
//     the value as a register) -> unix-seconds expiry, the same value
//     bytes the engine writes (expiryValue) and the reconciler evicts.
//   - clock_offset + denied_ops follow the shared conventions.
//
// The programs hook the LSM BPF attach type (kernel sec "lsm/..."),
// which requires "bpf" in the kernel's lsm= boot parameter (and
// CONFIG_BPF_LSM). On hosts without it the collection fails to load and
// the loader falls back to signal-based suspension of the target PID —
// a degraded mechanism reported as mode "signal" in /healthz.
//
// Hosts must be cgroup v2 (v1 hybrids have no single cgroup id); the
// daemon resolves /proc/<pid>/cgroup from the host PID namespace.
#include "vigil_common.h"
#include <bpf/bpf_tracing.h> /* BPF_PROG (LSM context casts) */

/* Hook-argument types the programs never dereference. They are
 * kernel-internal (not UAPI), and generating vmlinux.h is deliberately
 * out of scope (vigil_common.h) — opaque forward declarations compile
 * because unused pointer parameters need no type body; the verifier
 * checks the context at load time. */
struct socket;
struct linux_binprm;

/* Stable UAPI errno (asm-generic/errno-base.h); not pulled in by linux/bpf.h. */
#ifndef EPERM
#define EPERM 1
#endif

/* Enforcement entries: cgroup id -> expiry (unix seconds). */
struct {
	__uint(type, BPF_MAP_TYPE_LRU_HASH);
	__uint(max_entries, 65536);
	__type(key, __u64);
	__type(value, __u64);
} interdict_v1 SEC(".maps");

/* Denied connect/exec verdicts — per-CPU, loader-read (denied_ops). */
struct {
	__uint(type, BPF_MAP_TYPE_PERCPU_ARRAY);
	__uint(max_entries, 1);
	__type(key, __u32);
	__type(value, __u64);
} denied_ops SEC(".maps");

static __always_inline int vigil_interdicted(void)
{
	__u64 cgid = bpf_get_current_cgroup_id();
	if (!vigil_blocked(&interdict_v1, &cgid))
		return 0;
	__u32 zero = 0;
	__u64 *denials = bpf_map_lookup_elem(&denied_ops, &zero);
	if (denials)
		__sync_fetch_and_add(denials, 1);
	return 1;
}

SEC("lsm/socket_connect")
int BPF_PROG(vigil_interdict_connect, struct socket *sock,
	     struct sockaddr *address, int addrlen, int flags)
{
	if (vigil_interdicted())
		return -EPERM;
	return 0;
}

SEC("lsm/bprm_check_security")
int BPF_PROG(vigil_interdict_exec, struct linux_binprm *bprm)
{
	if (vigil_interdicted())
		return -EPERM;
	return 0;
}

char LICENSE[] SEC("license") = "GPL";
