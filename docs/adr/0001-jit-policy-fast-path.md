# ADR 0001 — JIT policy fast path

Status: accepted

## Context

Every finding that reaches the daemon's enrich step pays the full LLM triage —
prompt build, model call, parse — even when a workflow has already resolved
this exact archetype many times, consistently, at recorded cost. The evidence
that a playbook has learned an archetype is durable in the operational schema
(completed run outcomes, case closure categories, analyst overrides), and spend
rolls up into `workflow_runs`. Nothing compiles that evidence into a form that
skips the model.

The temptation this ADR exists to bound: once decisions are cheap, where do
they come from, and who can tell?

## Decision

Three boundaries, all additive to what already governs the daemon.

**1. The compile-versus-memory boundary (ADR 0015 restated).** Episodic memory
"reorders the frontier and never decides" and a Recall "settles nothing" — the
operative rules are stated in `CONTEXT.md` (ADR 0015, cited by number there and
in `core/memory/recall.py`; the rules restated here are in-repo statements, not
quotes of an out-of-repo ADR text). The compiler respects that line from the
other side: **memory never feeds the compile.** The maturity job reads
operational tables only — `workflow_runs`, `findings`,
`finding_mitre_predictions`, cases and `case_closure_info` — and never
`episodic_*`. The fast path is not a second decider inside memory; it is a new
consumer of operational outcomes, evaluated at compile time. Compile-time reads
of memory would both violate ADR 0015's read-once-at-start discipline and let
asserted material shape what the daemon later trusts as measured.

**2. Policy-as-data security stance.** A compiled policy is data with a hash,
not code with a prompt:

- **Predicates bind only to evidence-anchored, pre-LLM fields** — `data_source`,
  ATT&CK technique predictions, entity-context key *types*, workflow identity.
  Free-text fields (`title`, `description`) are excluded by validation, so an
  adversary who can shape alert text cannot steer a compiled policy. This is
  the same alert-farming defense the prompt-injection scan (#87) applies to
  the LLM path.
- **Every decision names what was trusted**: policy id, version, and content
  hash, written to `compiled_policy_decisions` for every evaluation — hit or
  miss, shadow or active — plus the evaluation cost in microseconds. "What was
  trusted, and why" is reconstructable per finding, the audit rule the Ledger
  already sets for the rest of the system.
- **The artifact is exportable and inspectable**: one versioned JSON IR,
  projected to Rego, Snort, Suricata, and iptables by golden-file-pinned
  renderers. The IR evaluated in-process is the engine; the exports are
  projections, kept honest by tests, not a second evaluation runtime.

**3. No new autonomy in v1.** The fast path grants no unattended power the
daemon lacks. Policies decide triage — severity, confidence, recommended
action, category — and every containment action still routes through the
existing `ApprovalService` bands; policy-triaged actions stay `human_only=True`
(a policy's confidence is its own claim, which is exactly what `human_only`
exists for). Elevation is a future, separately-governed INTENT.md decision,
not a side effect of this one. The fast-path flag itself is a daemon autonomy
knob declared in INTENT.md frontmatter (`triage.jit_fast_path_enabled`) and
defaults off in every environment; no deployment gains the fast path by
upgrading, and no policy acts before an operator promotes it through shadow.

Lifecycle, in one line: candidate → shadow → active is human-gated; every
edge back (drift auto-brake to suspended, staleness or human action to
retired) is automatic or human-caused; suspended policies re-enter shadow
after review, never straight to active; retired is terminal and kept for
audit.

## Consequences

- Mature archetypes run at CPU speed before any LLM call; the savings are
  directly measurable from recorded spend, and per-inference latency becomes
  measurable from the new `evaluation_us` instrumentation going forward.
- Shadow mode pays double triage (policy + LLM) by design: it is the price of
  the agreement evidence, and it ends at promotion.
- IR↔Rego divergence is the standing drift risk of canonical-IR-plus-renderers;
  golden-file tests pin every renderer to the IR. If a deployment later runs
  OPA, evaluation can move to the rendered bundle without touching the
  maturity job, lifecycle, or storage.
- `core.policy_compiler` is a new capability domain, registered in both
  enumerated `.importlinter` contracts (versioned-api sources, tiers
  forbidden) on the day it exists.

This file starts the `docs/adr/` series. Numbering is sequential from 0001;
ADR numbers cited elsewhere in the repo (0015, 0016, 0009, 0012) predate this
directory and live in `CONTEXT.md` and code citations.
