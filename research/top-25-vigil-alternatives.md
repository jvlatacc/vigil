# Top 25 Alternatives to Vigil

**Competitive landscape research for vigilsoc.org / DeepTempo**
**Compiled:** 2026-10-09 · **Method:** five parallel research batches (A–E, five vendors each), one synthesis pass · **Status:** final draft for review

> **Delivery note.** This document is destined for `research/top-25-vigil-alternatives.md` in `jvlatacc/vigil` (single squash PR to `main`, owned by the coder step). The load-bearing premise, fixed in the research spec: a versioned, committed competitive-landscape file is useful as a durable, citable artifact the team can update — as opposed to a chat answer or a wiki page. If the intent had been a one-off internal summary, the research below would be unchanged; only the delivery step would differ.

## Methodology

**How the 25 were selected.** The 25 alternatives were fixed up front as a seed list in the research spec (five batches of five), chosen for **category coverage** rather than any single review-site ranking: Vigil competes across four overlapping categories — AI SOC analysts, agentic SOAR, SIEM/XDR suite copilots, and MDR services — so the list weights Vigil's closest categories (AI SOC analysts and agentic SOAR) and treats MDR services, a different buying motion, more lightly. Batch A covers profiles 1–5, B = 6–10, C = 11–15, D = 16–20, E = 21–25.

**Sources cross-checked.** Each vendor was checked against its own product/pricing pages plus at least two independent roundup or category sources. The roundup and category pages used across the batches (all accessed 2026-10-09):

- [D3 Security / Security Boulevard — The 12 Best Agentic SOC Platforms in 2026 (2026-07-27)](https://securityboulevard.com/2026/07/the-12-best-agentic-soc-platforms-in-2026-architectures-autonomy-levels-and-a-full-comparison/) — accessed 2026-10-09
- [Security Boulevard (Swimlane-authored) — The Best AI SOC Platforms in 2026: An Honest Comparison (2026-09)](https://securityboulevard.com/2026/09/the-best-ai-soc-platforms-in-2026-an-honest-comparison/) — accessed 2026-10-09
- [Expert Insights — Best 11 AI SOC Platforms for Business (updated 2026-10-08)](https://expertinsights.com/security-operations/top-ai-soc-platforms-for-business) — accessed 2026-10-09
- [Intezer — Top 16 AI SOC Tools for 2026 (2026-04-06)](https://intezer.com/blog/top-15-ai-soc-platforms-in-2026) — accessed 2026-10-09
- [UnderDefense — Agentic SOC platforms roundup (updated 2026-10-09)](https://underdefense.com/blog/agentic-soc-platforms/) — accessed 2026-10-09
- [UnderDefense — Best AI SOC for Enterprise (2026-03-13)](https://underdefense.com/blog/ai-soc-for-enterprise/) — accessed 2026-10-09
- [D3 Security — The Best AI SOC Platforms 2026 (2026-03)](https://d3security.com/blog/ai-soc-platforms-2026/) — accessed 2026-10-09
- [Panther — Best AI SOC Platforms (2026-06-29)](https://panther.com/blog/best-ai-soc-platforms) — accessed 2026-10-09
- [Palo Alto Networks Cyberpedia — AI SOC tools comparison](https://www.paloaltonetworks.com/cyberpedia/ai-soc-tools-comparison) — accessed 2026-10-09
- [TrustRadius — AI SOC Analyst Software category](https://www.trustradius.com/categories/ai-soc-analyst) — accessed 2026-10-09
- [Expert Insights — Best 10 SOC Automation Platforms](https://expertinsights.com/security-operations/best-soc-automation-platforms) — accessed 2026-10-09
- Plus per-vendor G2 / Gartner Peer Insights / PeerSpot / SoftwareReviews pages, AWS Marketplace listings, the Agentic Index vendor directory, trade press, and vendor first-party pages — all linked in the individual profile source lists.

Batch A additionally recorded a per-vendor roundup cross-check register:

| Vendor (final set) | Roundup/category source 1 | Roundup/category source 2 | Vendor site |
|---|---|---|---|
| Dropzone AI | D3 Security / Security Boulevard, 2026-07-27 | Expert Insights, updated 2026-10-08 (also UnderDefense 2026-10-09; Intezer Top 16 2026-04-06; TrustRadius category) | dropzone.ai |
| Prophet Security | Expert Insights, updated 2026-10-08 | D3 Security / Security Boulevard, 2026-07-27 (also TrustRadius category; Intezer Top 16) | prophetsecurity.ai |
| Intezer | D3 Security / Security Boulevard, 2026-07-27 | UnderDefense agentic roundup, updated 2026-10-09 (also UnderDefense enterprise 2026-03-13; TrustRadius category) | intezer.com |
| Qevlar AI | D3 Security "Also Tracking," 2026-07-27 | Intezer Top 16, 2026-04-06 | qevlar.com |
| ReliaQuest GreyMatter | Expert Insights, updated 2026-10-08 | Panther, 2026-06-29 (also G2 category presence) | reliaquest.com |
| Radiant Security (substituted out) | D3 / Security Boulevard 2026-07-27; Intezer Top 16 2026-04-06; UnderDefense 2026-10-09 | — | Acquisition verified via Cribl newsroom, SiliconANGLE, Paul Hastings (all 2026-08-19) |

**Substitutions (one).** **Radiant Security → ReliaQuest GreyMatter** (profile 5, promoted from the watchlist). Reason: on 2026-08-19, Cribl announced it had acquired the technology assets and intellectual property of Radiant Security, Inc., adapting that technology to run as an application on Cribl's telemetry platform ([SiliconANGLE, 2026-08-19](https://siliconangle.com/2026/08/19/cribl-buys-radiant-securitys-ai-soc-tech-in-second-security-deal-of-2026/); [Cribl newsroom, 2026-08-19](https://cribl.io/news/cribl-advances-ai-powered-security-operations-with-new-ai-soc-acquisition/); [Paul Hastings deal advisory, 2026-08-19](https://www.paulhastings.com/news/paul-hastings-advises-cribl-on-its-acquisition-of-radiant-securitys-technology-assets) — all accessed 2026-10-09). Radiant is therefore no longer procurable as an independent AI SOC alternative. GreyMatter was selected over the other watchlist candidates as the closest category fit: it performs agentic, autonomous Tier-1/Tier-2 investigation and containment over a customer's existing multi-vendor stack (Expert Insights classifies it as an "AI SecOps Platform" with autonomous triage and agentic AI; Panther's 2026 roundup credits it with "6 agentic personas … autonomous Tier 1 + Tier 2 investigation"). Vectra AI was considered and set aside: 2026 roundups categorize it as a detection platform rather than an AI SOC analyst (Intezer's Top 16 places Vectra under "Within a Platform"). Batches B, C, D, and E reported **no substitutions** — all five seed vendors in each batch were researchable on 2026-10-09.

**Radiant Security status note (substituted out).** Radiant Security built a focused AI SOC platform claiming triage of "100% of alerts, known and unknown types," with adaptive handling of novel alert types without pre-authored playbooks, explainable reasoning trails, 100+ data sources, and a flat per-employee annual pricing model with unlimited alert volume (Radiant site; D3 roundup, 2026-07-27: "Focused AI Analyst … Autonomy ceiling: AL3 … Integrations: 100+"). UnderDefense's roundup (2026-04-01) credited its "Adaptive AI" architecture and reported ~$21M total funding including a $15M Series A led by Next47; third-party pricing estimates ranged $60K–$300K+/year by org size (UnderDefense pricing analysis, 2026-07-28 — estimates, not list prices). Weaknesses noted in reviews: thin case-management maturity, small review base, and early-stage vendor risk (G2; UnderDefense). **Status:** Cribl acquired Radiant's technology assets and IP, announced 2026-08-19; terms undisclosed. Some roundup pages continued to list Radiant after the announcement (e.g., UnderDefense's 2026-10-09 edition), so readers should treat stale roundup entries cautiously.

**Sourcing protocol.** Public web only; every factual claim carries a citation (URL + accessed date; all sources accessed 2026-10-09). Vendor-claimed capabilities are prefixed "Vendor states" and never blended with independent findings. Pricing appears only where publicly listed or explicitly attributed; otherwise the profile says "Not publicly listed." Fields that could not be sourced are marked "Unverified." Two vendor-authored roundups are used with attribution and only for category framing: Security Boulevard's September 2026 "Best AI SOC Platforms" piece is Swimlane-authored and self-discloses its conflict of interest, and Palo Alto's Cyberpedia comparison is vendor-owned. Where a vendor has public pricing data points of varying currency (e.g., Dropzone's historical per-investigation pricing, Torq's AWS Marketplace contract listing), the profile reports the source and date rather than asserting a current price. One known staleness trap is documented above (roundups listing Radiant post-acquisition).

**Comparison axes.** Seven axes, applied identically in every profile: agentic autonomy, open-source license, self-hosting, detection engineering, integration surface, case management, and response actions.

## Vigil snapshot

Vigil is DeepTempo's open-source (Apache 2.0) agentic AI SOC: 13 specialized AI agents spanning triage, investigation, threat hunting, correlation, response, reporting, forensics, and ATT&CK mapping; 30+ integrations over MCP; 7,200+ detection rules across Sigma/ESCU/Elastic/KQL; Markdown-defined workflows; built-in case management; human-on-the-loop response; self-hosted or air-gapped deployment; an optional DeepTempo LogLM integration; built by the team behind StackStorm. (Positioning per the research spec, which draws on vigilsoc.org docs, the Vigil-SOC/vigil GitHub README, and DeepTempo materials; every batch's "Versus Vigil" sections reuse this same baseline.)

| Axis | Vigil |
|---|---|
| Agentic autonomy | 13 specialized AI agents (triage → investigation → hunting → correlation → response → reporting → forensics → ATT&CK mapping), human-on-the-loop response |
| Open-source license | Apache 2.0 |
| Self-hosting | Self-hosted or air-gapped deployment |
| Detection engineering | 7,200+ detection rules across Sigma/ESCU/Elastic/KQL |
| Integration surface | 30+ integrations over MCP |
| Case management | Built-in |
| Response actions | Human-on-the-loop |
| Workflow authoring | Markdown-defined (diffable in git, no vendor canvas) |
| Optional extras | DeepTempo LogLM integration; StackStorm heritage |

## Segment map

**AI SOC analysts (profiles 1–10).** Standalone agentic layers that investigate alerts end-to-end over the customer's existing tooling: Dropzone AI, Prophet Security, Intezer, Qevlar AI, ReliaQuest GreyMatter, Exaforce, 7AI, and Simbian, plus Darktrace's embedded Cyber AI Analyst. Independent roundups file most of these under "AI SOC analyst" or "agentic SOC" (Security Boulevard, July 2026; Expert Insights, October 2026; Intezer Top 16; TrustRadius category) — Darktrace is the exception, since AI-SOC roundups generally do not class it as a pure-play analyst: its analyst is embedded in an NDR/XDR-rooted platform (batch B cross-check note). Autonomy across the segment runs from bounded auto-containment to recommendation-only; none of it is open-source.

**MDR-adjacent (profile 10, plus the platform-plus-MDR option in profile 5).** UnderDefense MAXI wraps its agentic AI SOC platform in a 24/7 human-led MDR service, and ReliaQuest pairs GreyMatter with its own ~1,200-person operations staff. The buying motion is outsourced operations rather than tooling — the reason the list weights this segment lightly.

**Agentic SOAR / orchestration (profiles 11–15).** Automation platforms layering agentic capability onto workflow fabrics, and the axis that separates Vigil's closest competitor set. Batch C's spectrum analysis: Security Boulevard ranks D3 Morpheus first among agentic-SOC platforms (a single reasoning engine investigating every alert end-to-end, generating response playbooks at runtime); Torq is called the furthest-along workflow platform for agentic capability (Auto Triage writes a verdict on every alert; the Socrates analyst coordinates HyperAgents; the SOC Brain launch of 2026-07-28 pushed it further); Swimlane embeds agents inside deterministic playbooks; Tines and Cortex XSOAR are workflow/playbook-first with AI as embedded actions or assistance — and Palo Alto positioned AgentiX (announced 2025-10-28) as XSOAR's successor, delivered first in Cortex Cloud and XSIAM. All five author workflows in proprietary visual canvases; none offers Markdown-as-code authoring (batch C workflow-authoring note).

**Suite platforms (profiles 16–20).** Copilots and agents embedded in a vendor's broader platform: Cortex XSIAM/AgentiX, CrowdStrike Charlotte AI + Falcon Next-Gen SIEM, SentinelOne Purple AI, Microsoft Sentinel + Security Copilot, and Google SecOps with Gemini. Security Boulevard's architecture taxonomy classifies all five as ecosystem-native/platform-native agents — "zero-friction if you live in that ecosystem; third-party stack coverage is second-class" (batch D sourcing note) — and Microsoft is the only vendor of the five with public example rates (batch D pricing summary).

**SIEM / XDR / detection platforms (profiles 21–25).** Platform-first vendors where AI capability is embedded in, or sold beside, the detection stack: Splunk ES + SOAR, IBM QRadar Suite/watsonx, Stellar Cyber Open XDR, Hunters SOC Platform, and Panther. None of the five publishes a price list — licensing *models* only (batch E note). Panther carries the strongest open-affinity signal in the batch: the Apache-2.0 `panther-analysis` detections repo and an open-source MCP server, on an otherwise proprietary platform.

## Master comparison table

"Pricing model" reflects public posture on 2026-10-09: "Not publicly listed" means no public rate card was found, not that the product is free; where a public listing exists, it is named. Full sourcing per cell sits in the corresponding profile.

| # | Vendor — Product | Category | Autonomy | Open source | Deployment | Pricing model | Best fit |
|---|---|---|---|---|---|---|---|
| 1 | Dropzone AI — Dropzone AI SOC Analyst | AI SOC analyst | Agentic w/ bounded response | No | Cloud SaaS | Not publicly listed (historically ~$36K/yr for 4,000 investigations per D3's July 2026 roundup; 2026 tiers quote-based) | Lean SOCs and MSSPs, ~20–100 alerts/day, 24/7 autonomous triage without a platform project |
| 2 | Prophet Security — Prophet AI | AI SOC analyst | Agentic w/ bounded response | No | Cloud SaaS (single-tenant, BYOK) | Not publicly listed (quote- and investigation-volume-based; AWS Marketplace reference in profile) | Mid-market and SaaS-heavy enterprises wanting triage + hunting + detection engineering from one vendor |
| 3 | Intezer — Autonomous SOC / "Forensic AI SOC" | AI SOC analyst | Agentic w/ bounded response | No | Cloud SaaS | Not publicly listed (endpoint-based Starter/Complete packages) | Enterprise SOCs (1,000+ employees/endpoints, vendor states), malware/phishing/endpoint-heavy alert mixes |
| 4 | Qevlar AI — Qevlar AI SOC Platform | AI SOC analyst | Agentic w/ bounded response | No | Cloud SaaS (API overlay) | Not publicly listed | SOCs and MSSP/MDRs wanting an investigation + correlation layer over existing detection tooling |
| 5 | ReliaQuest — GreyMatter *(substitute for Radiant Security)* | AI SecOps platform (agentic, optional MDR) | Agentic w/ bounded response | No | Cloud SaaS (connects to on-prem/multi-cloud/hybrid) | Not publicly listed (G2: pricing not available) | Large enterprises rationalizing SIEM/SOC cost across multi-vendor stacks; platform-plus-MDR option |
| 6 | Exaforce — Agentic SOC Platform | AI SOC analyst | Agentic w/ bounded response | No | SaaS (self-operated or vendor-run MDR) | Not publicly listed | Cloud/SaaS-heavy teams cutting SIEM cost and alert load, or replacing an MSSP/legacy MDR |
| 7 | 7AI — Agentic Security Platform | AI SOC analyst | Agentic w/ bounded response | No | Cloud SaaS | Not publicly listed (AWS Marketplace shows a $50,000/yr 12-month entry) | Enterprises adopting autonomous, agent-driven SOC work without a platform prerequisite |
| 8 | Simbian — AI SOC Agent | AI SOC analyst (SOAR-replacement pitch) | Agentic w/ bounded response | No | SaaS (vendor's on-prem/in-cloud claim disputed — Unverified) | Public: usage-based, $10,000 per 1,000 investigated alerts (AWS Marketplace) | Lean teams replacing manual triage and SOAR scripting; MSSP/MDR partners |
| 9 | Darktrace — Cyber AI Analyst | XDR/NDR-rooted platform w/ embedded AI analyst | Agentic investigation w/ bounded containment | No | SaaS default; legacy on-prem appliances persist | Not publicly listed (custom subscription; third-party estimates exist) | Network-first behavioral detection across heterogeneous estates, incl. OT |
| 10 | UnderDefense — MAXI | MDR (agentic AI SOC platform + 24/7 service) | Agentic w/ bounded response | No | SaaS, customer cloud, or on-prem/air-gapped (Kubernetes) | Partially public: vendor-stated $11–$15 per endpoint/month, all-inclusive | Orgs without 24/7 SOC staff; regulated, sovereign, or air-gapped environments |
| 11 | Torq — HyperSOC | Agentic SOAR | Agentic w/ bounded response (Auto Triage + Socrates/HyperAgents) | No | SaaS | Not publicly listed (AWS Marketplace contract listing: $450,000 per 12-month plan tier) | Mid-size to large SOCs and MSSPs automating Tier-1 triage/closure over existing tools |
| 12 | Swimlane — Turbine | Agentic SOAR | Hybrid: AI agents inside deterministic playbooks | No | Both (cloud, on-prem, air-gapped) | Not publicly listed (action-volume tiers, quote-based; ~$47K/yr entry estimate per UnderDefense) | Enterprises and MSSPs, incl. regulated/government, needing auditable automation on-prem |
| 13 | D3 Security — Morpheus | Agentic SOAR | Agentic w/ bounded response (runtime-generated playbooks, guardrailed execution) | No | Both (SaaS, hybrid, on-prem, sovereign, air-gapped — vendor states) | Partially public: annual subscription sized to alert volume; no public rate card | Orgs incl. MSSPs wanting one unified agentic reasoning-and-orchestration engine, per-client tenancy |
| 14 | Tines — Stories / Tines 3B | Agentic SOAR | Workflow-first: AI Agent actions inside Stories; no autonomous-investigation claim | No | Both (SaaS; self-host reported for Business/Enterprise) | Public entry pricing: Community free; Starter $500/mo; Business/Enterprise quoted | Engineering-leaning teams wanting tool-agnostic automation they author and own |
| 15 | Palo Alto Networks — Cortex XSOAR | Agentic SOAR | Playbook-first with ML/GenAI assistance; AgentiX positioned as successor | No | Both (XSOAR 8 SaaS; XSOAR 8 on-premises; multi-tenant) | Not publicly listed (per-user annual SaaS license, quote-driven) | Large Palo Alto-committed SOCs and MSSPs needing mature orchestration |
| 16 | Palo Alto Networks — Cortex XSIAM / AgentiX | Suite copilot | Agentic w/ bounded response (role/permission-governed) | No | Vendor-hosted cloud SaaS | Not publicly listed (usage-based, per-GB plus per-user per Security Boulevard) | Enterprises standardized on the Palo Alto/Cortex estate consolidating the SOC on XSIAM |
| 17 | CrowdStrike — Charlotte AI + Falcon Next-Gen SIEM | Suite copilot | Agentic w/ bounded response (configurable per workflow) | No | Cloud SaaS (Falcon platform) | Not publicly listed (Charlotte AI: 50 free monthly credits for qualifying Falcon customers; credit-based Agentic SOAR) | Organizations standardized on Falcon wanting agentic triage on Falcon telemetry |
| 18 | SentinelOne — Purple AI | Suite copilot | Agentic w/ bounded response (AL3 per Security Boulevard) | No | Cloud SaaS (Singularity console) | Not publicly listed (add-on module on tiered licensing) | Existing SentinelOne customers, esp. endpoint-centric SOCs expanding to agentic ops |
| 19 | Microsoft — Sentinel + Security Copilot | Suite copilot | Copilot → agentic agents with scoped, permission-bounded actions | No | Azure cloud service | Public model: pay-as-you-go per GB (region-specific) + commitment tiers from 100 GB/day; Security Copilot via agents/usage | Microsoft-consolidated enterprises (M365 E5/E7, Defender, Entra, Azure) |
| 20 | Google — Security Operations (Chronicle + SOAR + Gemini) | Suite copilot | Copilot + deterministic SOAR automation, trending agentic | No | Google Cloud-hosted SaaS | Not publicly listed (Standard/Enterprise/Enterprise Plus editions, "contact sales") | Google Cloud-native organizations (GCP, Workspace, Mandiant) |
| 21 | Cisco (Splunk) — Enterprise Security + SOAR | SIEM + SOAR (suite copilot) | Copilot + playbook-driven ("assisted automation with analyst oversight") | No | Both (Splunk Cloud on AWS, or on-premises Splunk Enterprise) | Not publicly listed (four documented pricing models: ingest/workload/entity/activity) | Large enterprises with Splunk estates and dedicated detection-engineering staff |
| 22 | IBM — QRadar Suite / watsonx | SIEM (suite copilot) | Copilot (analyst-assistive) | No | Both (on-prem appliances; IBM SaaS SIEM path ended — SaaS retired 2025) | Not publicly listed (EPS/FPM or MVS licensing metrics) | Regulated/on-prem environments with existing QRadar estates; IBM shops |
| 23 | Stellar Cyber — Open XDR Platform | Open XDR (AI-native SecOps) | Copilot default; agentic w/ bounded response via paid Autonomous SOC Add-on | No ("Open" = integrations, not source) | Both claimed (cloud + on-prem sensors; multi-tenant) | Not publicly listed (single-license model per secondary reporting) | Mid-market teams and MSSPs/MDRs consolidating SIEM/NDR/XDR without rip-and-replace |
| 24 | Hunters — SOC Platform (Next-Gen SIEM) | Next-Gen SIEM / SOC platform | High automation of triage/investigation; agentic capabilities vendor-announced | No | SaaS | Not publicly listed (quote-based) | Lean/small SecOps teams wanting vendor-managed detection engineering |
| 25 | Panther — AI SOC Platform (Cloud SIEM) | Cloud SIEM (detection platform) | Agentic investigation w/ bounded actions | Partial (Apache-2.0 `panther-analysis` detections repo, PAT, MCP server) | SaaS or bring-your-own AWS + data lake | Not publicly listed (subscription/usage-based; Panther Cloud vs BYO-data-lake options) | Engineering-led SOCs and detection-as-code teams (GitHub/CI-CD practices, AWS-heavy) |

## Open-source adjacency: where the OSS angle sits

No profiled alternative is an open-source SOC platform. The only open-source overlap among the 25 is partial: Panther's detection content and tooling — the Apache-2.0 `panther-analysis` detections repo, the open-source Panther Analysis Tool (PAT) CLI, and an open-source MCP server — are open while the platform itself is proprietary (profile 25). That leaves Vigil as the only Apache-2.0, self-hostable/air-gappable agentic SOC in this set, which is the recurring "Versus Vigil" contrast across all five batches: licensing, deployment model, open detection formats, and Markdown-defined workflows.

**The StackStorm heritage angle.** Vigil is built by the team behind StackStorm (spec positioning, repeated in every batch's Vigil baseline), and several profiles turn that heritage into a concrete differentiator rather than a slogan: Dropzone's limited response execution and orchestration relative to platform-class products is flagged as "an area where Vigil's StackStorm heritage is directly relevant" (profile 1), and batch C's workflow-authoring comparison notes that all five SOAR competitors author workflows in proprietary visual canvases, while Vigil's Markdown-defined workflows review like documentation — diffable in pull requests, no vendor canvas required, self-hostable in git.

**Scope note on OSS SOAR.** The research spec's structure names Shuffle and other open-source SOAR projects as adjacent context for this section. No batch profiled any OSS SOAR vendor in this round, so this document makes no factual claims about them; they remain candidates for the watchlist in a future update of this file.

## Watchlist — adjacent players outside the top 25

The research spec names seven adjacent players to monitor. Batch retrieval covered two of them; the rest were not researched this round and carry no claims here.

| Vendor | Status in this edition |
|---|---|
| ReliaQuest GreyMatter | Promoted into the top 25: replaces Radiant Security at profile 5 (see Methodology — Substitutions). |
| Vectra AI | Considered for the profile-5 substitution and set aside: 2026 roundups categorize it as a detection platform rather than an AI SOC analyst (Intezer's Top 16 places Vectra under "Within a Platform"). Batch B cites a Darktrace-vs-Vectra-vs-SentinelOne comparison among its Darktrace sources. |
| Expel | Not covered by batch retrieval this round; retained for monitoring. |
| FortiSOAR | Not covered by batch retrieval this round; retained for monitoring. |
| Rapid7 InsightConnect | Not covered by batch retrieval this round; retained for monitoring. |
| ServiceNow SecOps | Not covered by batch retrieval this round; retained for monitoring. (Adjacent sourced data point: GreyMatter's 2026 releases add ServiceNow ticket sync — profile 5.) |
| LimaCharlie | Not covered by batch retrieval this round; retained for monitoring. |

## Vendor profiles

The 25 profiles follow, grouped by research batch in the order the batches were produced. Every profile uses the same template — field table (Category / What it is / Autonomy / Open source / Deployment / Pricing / Best fit), Key capabilities, Strengths / weaknesses, Versus Vigil, Sources — and one citation style: [Title](URL) — accessed 2026-10-09.

## Batch A — AI SOC Analysts I (profiles 1–5)

### 1. Dropzone AI — Dropzone AI SOC Analyst

| Field | Value |
|---|---|
| Category | AI SOC analyst (focused autonomous alert investigation) |
| What it is | A cloud-hosted autonomous AI SOC analyst that investigates every alert end-to-end across a customer's existing security tools and returns evidence-backed, decision-ready reports (vendor product page; D3 Security roundup). |
| Autonomy | Agentic with bounded response. Investigations start on alert intake without a human driving each step; response is configurable in three modes — fully automated for low-risk actions, human approval for higher-risk actions (e.g., account disable, host isolation), or recommendation-only (Vendor states; [Dropzone configuration guide, 2026-05-07](https://www.dropzone.ai/blog/blog-customize-ai-soc-analyst)). D3 scores production autonomy AL2–AL3. Note: Expert Insights' taxonomy table marks Dropzone "Agentic AI: No" under its stricter definition, while still reporting confirmed-threat auto-containment — a taxonomy tension worth noting. |
| Open source | No — closed-source commercial product. |
| Deployment | Cloud SaaS connecting to existing tools via APIs; no data migration or log normalization required (Vendor states). No self-hosted or air-gapped option is documented in public materials. |
| Pricing | Historically listed from ~$36K/year for 4,000 investigations (~$9 per investigation) — D3's July 2026 roundup, sourcing Dropzone's 2025 pricing page; September 2026 third-party reporting indicates 2026 tiers (Base/Enterprise/MSSP) moved to sales quotes ([tech-insider comparison, 2026-09-13](https://tech-insider.org/prophet-security-vs-dropzone-ai-vs-radiant-security-2026/)). Current: **Not publicly listed** on the vendor site. |
| Best fit | Lean SOCs and MSSPs with steady alert volume — D3: SOCs handling roughly 20–100 alerts/day needing 24/7 autonomous triage without a platform project. Vendor claims 300+ organizations; Expert Insights counts "over 100 enterprises including CBTS, UiPath, and Zapier." |

**Key capabilities:**
- Autonomous end-to-end investigation: agents query SIEM, EDR, identity, cloud, network, and threat-intel systems, correlate evidence, and return a verdict with an evidence locker and structured report (vendor product page; D3 roundup).
- 90+ integrations (Splunk, CrowdStrike, Microsoft Defender, Sentinel, Google SecOps, Panther, Cortex XSIAM, Elastic named) with no playbook authoring required to start (Vendor states 90+; D3 confirms "Integrations: 90+").
- Configurable bounded response: auto-execute low-risk actions, approval-gate high-risk actions, or recommend only; connector permissions scope agent tool access (Vendor states, configuration guide 2026-05-07).
- "Glass box" audit trail in plain English — every question asked, tool queried, and finding surfaced is recorded (Expert Insights, updated 2026-10-08).
- Expanding agent fleet: Vendor states the AI Threat Hunter and AI Threat Intel Analyst run federated hypothesis-driven hunts and advisory triage alongside the SOC Analyst (dropzone.ai product/eBook pages).

**Strengths / weaknesses:**
- *Strengths:* fast time-to-value with no-playbook onboarding; investigation write-ups analysts trust; published pricing "in a category that mostly hides it" (D3, 2026-07-27); Gartner Peer Insights 4.8/5 (5 reviews at retrieval); support responsiveness praised across team sizes (Expert Insights).
- *Weaknesses:* per-investigation pricing "creates a structural incentive to filter alerts before ingestion — a security decision disguised as a cost decision" (D3); reporting layer less mature than the investigation engine and upfront tuning takes meaningful time (Expert Insights); thin independent review base (Gartner Peer Insights 5 reviews; TrustRadius listing shows 0 reviews as of 2026-10-09); response execution and orchestration limited relative to platform-class products (D3).

**Versus Vigil:**
*Overlap:* both are agentic investigation layers that reason over existing tooling, produce evidence-backed verdicts, and keep humans on the loop for consequential actions. *Differences (factual):* Vigil is open-source under Apache 2.0 and deploys self-hosted or air-gapped; Dropzone is closed-source cloud SaaS with no documented self-host option. Vigil ships 7,200+ detection rules across Sigma/ESCU/Elastic/KQL and Markdown-defined workflows; Dropzone positions against playbook authoring entirely and public sources do not document a shipped detection-rule library. Dropzone advertises 90+ integrations versus Vigil's 30+ MCP integrations (different counting bases — vendor claims both). D3 flags Dropzone's response execution and orchestration as limited versus platform-class products, an area where Vigil's StackStorm heritage is directly relevant. Vigil's open-source cost model contrasts with Dropzone's per-investigation commercial pricing.

**Sources:**
- [Dropzone AI — AI SOC Analyst product page](https://www.dropzone.ai/ai-soc-analyst) — accessed 2026-10-09
- [Dropzone AI — How to Customize Your AI SOC Analyst (2026-05-07)](https://www.dropzone.ai/blog/blog-customize-ai-soc-analyst) — accessed 2026-10-09
- [D3 Security — The 12 Best Agentic SOC Platforms in 2026 (2026-07-27, syndicated to Security Boulevard)](https://securityboulevard.com/2026/07/the-12-best-agentic-soc-platforms-in-2026-architectures-autonomy-levels-and-a-full-comparison/) — accessed 2026-10-09
- [Expert Insights — Best 11 AI SOC Platforms for Business (updated 2026-10-08)](https://expertinsights.com/security-operations/top-ai-soc-platforms-for-business) — accessed 2026-10-09
- [tech-insider.org — Prophet vs Dropzone vs Radiant Security: AI SOC 2026 (2026-09-13)](https://tech-insider.org/prophet-security-vs-dropzone-ai-vs-radiant-security-2026/) — accessed 2026-10-09
- [Gartner Peer Insights — Dropzone AI reviews](https://www.gartner.com/reviews/vendor/dropzone-ai) — accessed 2026-10-09

### 2. Prophet Security — Prophet AI

| Field | Value |
|---|---|
| Category | AI SOC analyst (multi-agent triage, hunting, and detection engineering) |
| What it is | An agentic AI SOC platform whose agents autonomously triage and investigate every alert, gather evidence across the customer's existing stack, and return auditable dispositions; positioned around three coordinated agents — AI SOC Analyst, AI Threat Hunter, and AI Detection Engineer (vendor site; D3 names the trio "SOC Analyst, Threat Hunter, Detection Advisor"). |
| Autonomy | Agentic with bounded response. Vendor states agents plan investigative questions, query connected systems, and reach a verdict; high-confidence benign alerts may auto-resolve while malicious/inconclusive cases escalate with evidence; consequential actions run through scoped "Agent Actions" that can be autonomous or analyst-approved (vendor site and ["What is Agentic SOC?" blog, 2026-10-07](https://www.prophetsecurity.ai/blog/what-is-agentic-soc)). D3 scores production autonomy AL3. Expert Insights' taxonomy marks it "Agentic AI: No" under its stricter definition while rating autonomous triage "Yes." |
| Open source | No — closed-source commercial product. |
| Deployment | SaaS as a dedicated single-tenant deployment with bring-your-own-key option; vendor states it does not train AI models on customer data. No self-hosted or air-gapped option is documented in public materials. |
| Pricing | **Not publicly listed** on the vendor site; described as quote-based and investigation-volume-based. Third-party roundups report an AWS Marketplace reference of ~$50,000/year for 5,000 investigations ([Expert Insights](https://expertinsights.com/security-operations/top-ai-soc-platforms-for-business); [tech-insider, 2026-09-13](https://tech-insider.org/prophet-security-vs-dropzone-ai-vs-radiant-security-2026/)); D3's table lists the model as "Per-environment (vendor-stated, 2025, unaudited)." |
| Best fit | Mid-market and SaaS-heavy enterprise environments that want triage plus proactive hunting and detection-engineering coverage from one vendor (Expert Insights: "SaaS-heavy enterprise environments"; D3: "mid-market teams … who can tolerate growth-stage vendor risk"). |

**Key capabilities:**
- Autonomous investigation with visible reasoning: per alert, Prophet summarizes, plans dynamic investigative questions, gathers context from SIEM/EDR/identity/email/cloud/network/TI sources, builds a timeline, and writes notes back into customer workflows (vendor blog; Expert Insights: "mimics how a human analyst actually works").
- Vendor states 200+ out-of-the-box integrations (FAQ); D3's July 2026 roundup counts 80+ — the discrepancy is unresolved in public sources and both figures are vendor/roundup claims.
- AI Detection Engineer: Vendor states it builds a live MITRE ATT&CK coverage map from the customer's own investigations, then authors and backtests detections to close gaps (vendor blog, 2026-07-30).
- Bounded autonomous response via scoped Agent Actions with approval controls; case studies describe high-confidence benign auto-resolution with review queues for the rest (vendor site; case study pages).
- Vendor case studies (unaudited): 11,065 alerts investigated over three months at a national health provider; 4,407 investigations in 60 days with mean time to investigate under four minutes at JB Poindexter & Co.

**Strengths / weaknesses:**
- *Strengths:* deep, human-like investigation workflow praised by Expert Insights; hunting and detection-engineering agents cover SOC work pure triage products ignore (D3); auditable evidence trails and policy-controlled response; strong funding momentum — $30M Series A led by Accel (July 2025) plus strategic investments from American Express Ventures and Citi Ventures (February 2026) per Expert Insights and tech-insider.
- *Weaknesses:* essentially no independent review footprint — a February 2026 aggregation reports no public reviews on G2, Capterra, TrustRadius, Gartner Peer Insights, or Reddit ([checkthat.ai](https://checkthat.ai/brands/prophet-security)); D3 flags early-stage vendor risk for a platform this central to operations and notes claims are vendor-stated and unaudited; headline metrics (e.g., 92% autonomous completion, 96% false-positive reduction) come from vendor-authored case studies; D3 counts 80+ integrations versus the vendor's 200+ claim.

**Versus Vigil:**
*Overlap:* both use multiple specialized AI agents for triage and investigation, emphasize evidence-backed auditability, and keep humans approving consequential actions. Prophet extends into AI threat hunting and detection engineering, paralleling Vigil's hunting/forensics/detection agents. *Differences (factual):* Vigil is Apache-2.0 open-source and self-hostable/air-gapped; Prophet is closed-source single-tenant SaaS with no documented self-host option. Vigil ships a curated 7,200+ rule library (Sigma/ESCU/Elastic/KQL); Prophet's Detection Engineer generates and backtests detections from the customer's own investigations — a generative rather than library approach. Prophet claims 200+ integrations (vendor) vs Vigil's 30+ MCP integrations. Vigil's case management is built in and open-source; Prophet writes dispositions back into customers' existing case/ITSM systems rather than replacing them.

**Sources:**
- [Prophet Security — homepage / agentic AI SOC platform](https://www.prophetsecurity.ai/) — accessed 2026-10-09
- [Prophet Security — FAQ (integrations, autonomy description)](https://www.prophetsecurity.ai/prophet-security-faq) — accessed 2026-10-09
- [Prophet Security — What is Agentic SOC? (2026-10-07)](https://www.prophetsecurity.ai/blog/what-is-agentic-soc) — accessed 2026-10-09
- [Expert Insights — Best 11 AI SOC Platforms for Business (updated 2026-10-08)](https://expertinsights.com/security-operations/top-ai-soc-platforms-for-business) — accessed 2026-10-09
- [D3 Security — The 12 Best Agentic SOC Platforms in 2026 (2026-07-27)](https://securityboulevard.com/2026/07/the-12-best-agentic-soc-platforms-in-2026-architectures-autonomy-levels-and-a-full-comparison/) — accessed 2026-10-09
- [tech-insider.org — Prophet vs Dropzone vs Radiant Security (2026-09-13)](https://tech-insider.org/prophet-security-vs-dropzone-ai-vs-radiant-security-2026/) — accessed 2026-10-09

### 3. Intezer — Intezer Autonomous SOC / "Forensic AI SOC"

| Field | Value |
|---|---|
| Category | AI SOC analyst (forensic-grade autonomous triage and investigation) |
| What it is | A SaaS platform that autonomously triages and investigates every alert — including low-severity ones — by combining agentic AI reasoning with deterministic forensics: endpoint forensics, memory scanning, reverse engineering, sandboxing, and network-artifact analysis (vendor product page; UnderDefense calls this combination "ForensicAI™"). |
| Autonomy | Agentic with bounded response. Vendor states the platform resolves most alerts autonomously and escalates the rest with context and recommended actions; response (e.g., disable user, isolate device) executes via API/webhook or routes for analyst review. Escalation-rate claims vary by source: "fewer than 2%" (Intezer's own 2026 roundup), ~4% (Microsoft Marketplace listing / G2 description) — treat as vendor claims. D3 scores autonomy AL3 for file-centric verdicts. |
| Open source | No — closed-source commercial product. |
| Deployment | Cloud SaaS; distributed through Azure Marketplace as a SaaS offering. No self-hosted or air-gapped option is documented in public materials. |
| Pricing | **Not publicly listed** as dollar figures. Vendor publishes endpoint-based Starter and Complete packages without prices and argues endpoint-based pricing avoids an "alert tax"; G2 lists two editions with pricing by quote and no free trial; TrustRadius shows a starting figure of $2,400 with unclear period; UnderDefense estimates mid-five to six-figure annual commitments (third-party estimate, not a list price). |
| Best fit | Enterprise SOCs (vendor states focus on organizations of 1,000+ employees / 1,000+ endpoints) with malware-, phishing-, and endpoint-heavy alert mixes; regulated teams that need forensically defensible, audit-ready verdicts (D3; UnderDefense enterprise roundup). |

**Key capabilities:**
- Forensic investigation depth: automatic analysis of files, logs, command lines, memory images, and URLs, with sandboxing and code-level analysis grounding verdicts (vendor product page; D3: "structurally eliminates the hallucination class of error for file- and code-centric alerts").
- Broad alert-source coverage: endpoint (CrowdStrike, SentinelOne, Defender), identity (Entra ID, Okta), reported phishing (Office 365, Proofpoint), SIEM (Splunk, Sentinel, Sumo Logic, Elastic), and cloud (Wiz) triage; vendor states 100+ integrations.
- 100% alert coverage claim including low-severity alerts, with detection-engineering feedback loop tracking coverage against MITRE ATT&CK (vendor roundup, April 2026).
- Response actions executed automatically or routed for review; on-demand access to Intezer experts for complex incidents (vendor pages).
- Vendor performance claims (unaudited): median investigation 15 seconds, sub-minute triage, <2% escalation (Intezer/UnderDefense), 126% net revenue retention in 2025 (UnderDefense citing vendor).

**Strengths / weaknesses:**
- *Strengths:* verdict reliability on malware/phishing/endpoint alerts is "the best-evidenced in the focused-analyst class" thanks to deterministic grounding (D3); highest-scored focused analyst in UnderDefense's weighted roundup (78/100, 2nd of 10, ahead of Dropzone's 75); G2 4.5/5 with 193 reviews per UnderDefense's March 2026 enterprise roundup — the deepest independent review base in this batch; predictable endpoint-based pricing model.
- *Weaknesses:* no public dollar pricing (G2: quote required; TrustRadius figure ambiguous); the deterministic advantage is strongest on file/code-centric alerts — identity, cloud-control-plane, and business-logic alerts "lean back on conventional reasoning" (D3); orchestration and response are "not the product's center of gravity" (D3); vendor states it requires mature customer telemetry and focuses on enterprises with 1,000+ employees, and vendor-acknowledges realistic ATT&CK coverage ceilings of 60–70%; Intezer's own roundup ranks itself first — weigh self-promotional sourcing accordingly.

**Versus Vigil:**
*Overlap:* both investigate every alert autonomously, escalate only what needs humans, map to MITRE ATT&CK, and treat detection engineering as a feedback loop. *Differences (factual):* Vigil is Apache-2.0 open-source and self-hostable/air-gapped; Intezer is closed-source cloud SaaS (Azure Marketplace). Intezer's differentiator is deterministic forensic tooling (memory scanning, reverse engineering, code genetics) that public roundups say produces the most defensible file-centric verdicts in the class; Vigil's 13 agents and 30+ MCP integrations are broader in orchestration surface, and Vigil's StackStorm lineage directly addresses the response/orchestration area D3 flags as not Intezer's strength. Vigil's 7,200+ open detection rules contrast with Intezer's endpoint-priced, closed platform. Intezer has the largest verified review base in this batch (G2 4.5/5, 193 reviews per UnderDefense), which Vigil, as an open-source project, does not accumulate on commercial review sites.

**Sources:**
- [Intezer — AI SOC product page](https://intezer.com/product/ai-soc) — accessed 2026-10-09
- [Intezer — Forensic AI SOC pricing page](https://intezer.com/product/pricing) — accessed 2026-10-09
- [Intezer — Top 16 AI SOC Tools for 2026 (2026-04-06; vendor-authored roundup)](https://intezer.com/blog/top-15-ai-soc-platforms-in-2026) — accessed 2026-10-09
- [UnderDefense — 8/10 Best Agentic AI SOC Platforms for 2026 (updated 2026-10-09)](https://underdefense.com/blog/agentic-soc-platforms/) — accessed 2026-10-09
- [UnderDefense — 9 Best AI SOC for Enterprise (2026-03-13)](https://underdefense.com/blog/ai-soc-for-enterprise/) — accessed 2026-10-09
- [D3 Security — The 12 Best Agentic SOC Platforms in 2026 (2026-07-27)](https://securityboulevard.com/2026/07/the-12-best-agentic-soc-platforms-in-2026-architectures-autonomy-levels-and-a-full-comparison/) — accessed 2026-10-09
- [Microsoft Azure Marketplace — Intezer Autonomous SOC listing](https://marketplace.microsoft.com/en-us/product/saas/intezerlabsinc.autonomous-soc-platform2?tab=overview) — accessed 2026-10-09
- [TrustRadius — Best AI SOC Analyst Software 2026 category (Intezer listing)](https://www.trustradius.com/categories/ai-soc-analyst) — accessed 2026-10-09

### 4. Qevlar AI — Qevlar AI SOC Platform

| Field | Value |
|---|---|
| Category | AI SOC analyst (autonomous investigation and incident-correlation overlay) |
| What it is | A vendor-agnostic platform, founded in Paris in 2023, that connects to an existing detection stack via API and autonomously investigates alerts end to end — enriching, correlating related activity into incidents, reaching verdicts, and recommending remediation (vendor site; Cyber Vendor Guide profile). |
| Autonomy | Agentic with bounded response. Vendor states a "deterministic graph orchestrator" investigates every alert end to end and can auto-close benign alerts subject to customer configuration, while analysts validate malicious verdicts and drive response; Qevlar has stated that in some deployments over 80% of cases are handled autonomously (vendor blog, 2025). No evidence in public sources of unrestricted autonomous response. |
| Open source | No — closed-source commercial product. |
| Deployment | API-connected overlay on the existing stack (SIEM, EDR/XDR, SOAR, identity, email, cloud, TI); vendor materials describe connecting the stack "in hours" but do not clearly document SaaS vs private-cloud vs on-premises hosting — hosting specifics: Unverified/not documented in public materials. |
| Pricing | **Not publicly listed.** No public price list, tiers, or rates were identified in vendor materials or third-party sources; model is inferred to be sales-led (inference, not a sourced price structure). |
| Best fit | SOCs and MSSP/MDR providers that want an investigation layer over existing detection tooling, with incident-level correlation and reuse of past investigations; documented MSSP deployments include Atos (2025-10-07 press release) and Sopra Steria (vendor blog). |

**Key capabilities:**
- Autonomous end-to-end investigation per alert with verdicts (malicious / benign / inconclusive), confidence, and evidence reports; Vendor states average investigation time of ~3 minutes — independently echoed by D3's shortlist ("single-purpose autonomous investigation with consistent ~3-minute case turnaround," attribution to vendor claims).
- Incident correlation: "Qevlar Incidents" groups related malicious activity across any source into one prioritized investigation with blast-radius mapping (vendor blog/product pages).
- Graph-orchestrated reasoning that reuses past investigations, so investigation quality compounds over time (Intezer's Top 16 characterization of Qevlar; vendor positioning).
- MSSP/MDR operating-model support with multi-environment use; Atos embeds Qevlar as a "virtual SOC analyst" for routine and intermediate analysis and alert scoring by criticality and blast radius (Atos press release, 2025-10-07).
- Vendor performance claims (unaudited): investigation time reduced from 30–40 minutes to ~3 minutes (~10x), up to 99.8% classification accuracy, 90% reduction in L1/L2 investigation time.

**Strengths / weaknesses:**
- *Strengths:* funding momentum — $14M total commitments announced in 2025 (company announcement) and a $30M round in March 2026 led by Partech and Forgepoint Capital International with EQT Ventures participating ([Qevlar press release, 2026-03](https://www.qevlar.com/press/qevlar-ai-raises-30m); [Security Brief, 2026-03-11](https://securitybrief.co.uk/story/qevlar-ai-raises-usd-30m-to-expand-autonomous-ai-soc)); named MSSP/MDR deployments (Atos, Sopra Steria); incident-level correlation differentiates it from alert-by-alert triage tools; covered in two independent 2026 roundups (D3 shortlist; Intezer Top 16 under "Emerging / Specialized").
- *Weaknesses:* no public pricing; no substantive independent review base surfaced in retrieval (Cyber Vendor Guide notes coverage relies heavily on vendor claims and funding coverage); headline metrics (3-minute investigations, 99.8% accuracy) are vendor-reported without independent benchmarks; hosting/residency options are not clearly documented; response autonomy is not fully specified in public materials.

**Versus Vigil:**
*Overlap:* both autonomously investigate alerts from an existing stack, correlate related activity, and produce evidence-backed verdicts for human validation. *Differences (factual):* Vigil is Apache-2.0 open-source, self-hostable/air-gapped, with 30+ MCP integrations and 7,200+ open detection rules; Qevlar is closed-source, discloses no hosting details, publishes no pricing, and public sources do not document a shipped detection-rule library. Vigil's differentiators are transparency (open workflows, self-hosting) and detection engineering depth; Qevlar's are incident correlation, investigation reuse, and established MSSP/MDR channel deployments (Atos, Sopra Steria). Qevlar's MSSP orientation matches a buying motion Vigil's open-source model can also serve, but with radically different commercial mechanics.

**Sources:**
- [Qevlar AI — AI SOC platform page](https://www.qevlar.com/ai-soc) — accessed 2026-10-09
- [Qevlar AI — $30M funding press release (March 2026)](https://www.qevlar.com/press/qevlar-ai-raises-30m) — accessed 2026-10-09
- [Qevlar AI — $14M funding announcement (2025)](https://www.qevlar.com/post/qevlar-ai-raises-14m-to-supercharge-security-operations-centres-with-agentic-ai) — accessed 2026-10-09
- [Atos — press release on Qevlar-powered virtual SOC analyst (2025-10-07)](https://atos.net/en/2025/press-release_2025_10_07/atos-further-augments-the-ai-tooling-of-its-cybersecurity-teams-with-virtual-soc-analyst-powered-by-qevlar-ai) — accessed 2026-10-09
- [Intezer — Top 16 AI SOC Tools for 2026 (2026-04-06; Qevlar listed under Emerging/Specialized)](https://intezer.com/blog/top-15-ai-soc-platforms-in-2026) — accessed 2026-10-09
- [D3 Security — The 12 Best Agentic SOC Platforms in 2026, "Also Tracking" shortlist (2026-07-27)](https://securityboulevard.com/2026/07/the-12-best-agentic-soc-platforms-in-2026-architectures-autonomy-levels-and-a-full-comparison/) — accessed 2026-10-09
- [Cyber Vendor Guide — Qevlar AI profile](https://www.cybervendorguide.com/tools/qevlar-ai) — accessed 2026-10-09

### 5. ReliaQuest — GreyMatter *(substitute for Radiant Security — see Methodology)*

| Field | Value |
|---|---|
| Category | AI SecOps platform (agentic security operations with optional MDR); adjacent to AI SOC analyst |
| What it is | An enterprise, cloud-native security operations platform that unifies multi-vendor telemetry across SIEM, endpoint, identity, network, cloud, and email, and runs agentic AI detection, investigation, and containment — usable standalone or with ReliaQuest's 24/7 MDR (vendor integrations page; Expert Insights; AWS Marketplace listing). |
| Autonomy | Agentic with bounded response. G2's product description states GreyMatter "orchestrates 6 agentic AI personas with 200+ agent skills"; Panther's roundup credits "autonomous Tier 1 + Tier 2 investigation." Vendor claims containment in under 5 minutes and elimination of routine Tier 1/2 work — vendor-stated, not independently verified. Actual response autonomy depends on configured playbooks, permissions, and approval controls. |
| Open source | No — closed-source commercial product. |
| Deployment | Cloud-native SaaS connecting to customers' existing on-premises, multi-cloud, and hybrid environments (vendor; AWS Marketplace). No self-hosted or air-gapped option is documented in public materials. |
| Pricing | **Not publicly listed** — G2 explicitly states pricing details are not available; enterprise sales with variables including telemetry scope, integrations, and whether MDR is included. |
| Best fit | Large enterprises pursuing SIEM rationalization and SOC headcount-cost reduction across multi-vendor stacks, and buyers who want a platform-plus-MDR operating model (Panther: "Enterprises reducing SOC headcount costs; SIEM rationalization projects"; Expert Insights: "Multi-vendor stack unification and containment"). |

**Key capabilities:**
- Vendor-neutral unification: GreyMatter "Universal Translator" normalizes fields from connected technologies into the OCSF schema; ReliaQuest material cites 250–300+ technologies (counts vary by page) while Panther's roundup cites 400+ integrations — treat exact counts as vendor-claimed and variable.
- Six agentic AI personas ("Teammates") with 200+ agent skills and 400+ AI tools coordinating detection, investigation, hunting, and response (G2 description; vendor integrations page).
- Bidirectional response across connected tools — isolating endpoints, disabling identities/devices, blocking indicators — with 2026 releases adding Google SecOps SOAR and ServiceNow ticket sync, Entra ID response actions, and more (vendor product-release notes, June/August 2026).
- Hybrid platform + MDR model: ReliaQuest's ~1,200-person operations staff provide 24/7 monitoring, investigation, and escalation on the same platform (LeadIQ company profile; vendor materials).
- Vendor performance claims (unaudited): containment under 5 minutes; Panther's roundup cites "$3.5M average SIEM cost reduction."

**Strengths / weaknesses:**
- *Strengths:* broad integration and interoperability plus centralized visibility are the top G2 review themes; automation reduces analyst workload (G2 pros summary); strong support and MDR collaboration per reviewers; G2 average 4.7/5 across 20 reviews (as of retrieval); enterprise scale — founded 2007, Tampa FL, ~1,200 employees, 1,000+ customers (source counts vary, ~1,300–1,500 per secondary profiles).
- *Weaknesses:* G2 review summaries flag alert delays, slow report loading, and a clunky mobile experience; some reviewers cite configuration complexity and tuning burden; small review base (20 G2 reviews) for a vendor of this size; pricing opacity; platform value is entangled with the quality of the accompanying MDR service, complicating product-only evaluations.

**Versus Vigil:**
*Overlap:* both run agentic detection/investigation/response across a customer's existing multi-vendor stack rather than forcing a rip-and-replace, and both emphasize case/workflow management and response actions. *Differences (factual):* Vigil is Apache-2.0 open-source, self-hostable/air-gapped, with 30+ MCP integrations, 7,200+ open detection rules, and Markdown-defined workflows; GreyMatter is a closed-source enterprise platform with OCSF-based telemetry normalization, hundreds of vendor-claimed integrations, and an embedded global MDR service — an operating model Vigil does not offer. GreyMatter's strengths (scale, services wrap, integration breadth) address large-enterprise procurement; Vigil's strengths (open licensing, self-hosting, transparent open detection content) address teams that must keep data and logic in-house. GreyMatter's pricing is quote-only at enterprise scale; Vigil carries software cost only in the form of self-managed operations.

**Sources:**
- [ReliaQuest — GreyMatter integrations / agentic AI platform page (updated 2026-10-08)](https://reliaquest.com/integrations/) — accessed 2026-10-09
- [G2 — ReliaQuest GreyMatter reviews and product description](https://www.g2.com/products/reliaquest-greymatter/reviews) — accessed 2026-10-09
- [Panther — 10 Best AI SOC Platforms: Features & Use Cases (2026-06-29, GreyMatter row)](https://panther.com/blog/best-ai-soc-platforms) — accessed 2026-10-09
- [Expert Insights — Best 11 AI SOC Platforms for Business (updated 2026-10-08)](https://expertinsights.com/security-operations/top-ai-soc-platforms-for-business) — accessed 2026-10-09
- [AWS Marketplace — ReliaQuest GreyMatter listing and reviews](https://aws.amazon.com/marketplace/reviews/reviews-list/prodview-bk276y2eevzd2) — accessed 2026-10-09
- [LeadIQ — ReliaQuest company overview (2026-08-25)](https://leadiq.com/c/reliaquest/5a1d86fe2400002400612066) — accessed 2026-10-09

## Batch B — AI SOC Analysts II + MDR-Adjacent (profiles 6–10)

### 6. Exaforce — Exaforce Agentic SOC Platform

| Field | Value |
|---|---|
| Category | AI SOC analyst — an agentic SOC platform; TrustRadius lists "Exaforce Platform" in its AI SOC Analyst category, and Intezer's 2026 roundup files it under "Enterprise AI SOC" [2][3] |
| What it is | A cloud agentic SOC platform that pairs a unified security data layer (SIEM-replacement data store plus real-time knowledge graph) with four AI agents — Exabot Detect, Triage, Investigate, Respond — sold either as self-operated software or as an Exaforce-run MDR [1][3] |
| Autonomy | Agentic w/ bounded response — vendor states Exabots run in "copilot or autopilot mode" depending on delegated autonomy; Intezer describes response executed "with analyst oversight" [1][3] |
| Open source | No (proprietary) [1] |
| Deployment | SaaS; operated by the customer's own team or by Exaforce as MDR "same architecture, same Exabots" [1][2][3]. No on-premises option documented in public sources (Unverified) |
| Pricing | Not publicly listed — G2 states pricing is not publicly available [4]; Intezer's roundup: "Pricing not published" [3] |
| Best fit | Cloud/SaaS-heavy security teams trying to cut SIEM cost and alert load, or replacing an MSSP/legacy MDR contract [3][1] |

**Key capabilities**

- Unified data layer and real-time knowledge graph feeding a multi-model AI engine (semantic, behavioral/ML, and LLM models combined so reasoning does not rely on a single LLM) [3][1]
- Four specialized Exabots covering the detection-to-response lifecycle across identity, IaaS, SaaS, endpoint, email, and insider-threat surfaces [1][3]
- Ingests logs and configuration from 100+ sources, including developer sources most platforms miss (GitHub, Google Workspace) [1]
- Dual operating model: self-operate with the in-house team, or Exaforce runs it as 24/7 MDR with the same platform and full decision visibility [1][2]
- Vendor states customer outcomes of >$600K average savings versus traditional SOC stacks, 90% false-positive reduction, 95% reduction in mean time to investigate, and <30 min average alert-to-response — vendor-published figures, not independently validated [1]

**Company:** founded 2023 [3]. Raised a $75M Series A in April 2025 led by Khosla Ventures, Mayfield, and Thomvest Ventures [5][6]; a $125M Series B was announced May 12, 2026 [7][8].

**Strengths / weaknesses.** G2 reviewers (4.9/5 across a small base of ~7 reviews) praise automated triage and investigation before escalation, cross-source correlation across AWS/GCP/Defender/Entra, and small-team leverage — "like several additional analysts" [4]. Intezer's verdict: best for "cloud and SaaS-heavy teams cutting SIEM cost and load," with the caveat that Exaforce is "the newest entrant with limited independent validation so far" [3]. A G2 reviewer flags permissions management and out-of-the-box data-source coverage as areas needing improvement [4]. Security Boulevard's 2026 roundup tracks Exaforce outside its main 12, in the shortlist section [9].

**Versus Vigil.** Overlap: both run multi-agent agentic pipelines over the full alert lifecycle (detect → triage → investigate → respond) and both chase alert-overload economics. The architecture differs structurally: Exaforce brings its own proprietary data layer and positions itself as a SIEM replacement [1][3], while Vigil is an overlay that works through 30+ MCP integrations on the customer's existing stack without a proprietary data plane. Exaforce is closed-source SaaS with quote-based pricing; Vigil is Apache 2.0 with self-hosted/air-gapped deployment and no license cost. On detection engineering, Exaforce markets "rule-free detection" (vendor's framing [1]) where Vigil ships 7,200+ curated rules in open Sigma/ESCU/Elastic/KQL formats and Markdown-defined, inspectable workflows. Where Exaforce wins: a funded, vendor-run MDR option on the same platform, a unified data platform at scale, and commercial support with enterprise references. Where Vigil wins: licensing cost and transparency, air-gapped deployment, open detection-rule formats, and the StackStorm-lineage automation heritage.

**Sources:**

- **[1]** [Exaforce — Agentic SOC and MDR (exaforce.com)](https://www.exaforce.com) — accessed 2026-10-09
- **[2]** [TrustRadius, Best AI SOC Analyst Software 2026 (category listing)](https://www.trustradius.com/categories/ai-soc-analyst) — accessed 2026-10-09
- **[3]** [Intezer, "Top 16 AI SOC Tools for 2026: SOC Automation Compared"](https://intezer.com/blog/top-15-ai-soc-platforms-in-2026) — accessed 2026-10-09
- **[4]** [G2, Exaforce Reviews](https://www.g2.com/products/exaforce/reviews) — accessed 2026-10-09
- **[5]** [Latio vendor profile, Exaforce Reviews 2026](https://www.latio.com/vendor/exaforce) — accessed 2026-10-09
- **[6]** [Beri (The Daily Brief), Exaforce overview](https://www.beri.net/tools/exaforce) — accessed 2026-10-09
- **[7]** [TechCrunch, "Exaforce raises $125M Series B…" (May 12, 2026)](https://techcrunch.com/2026/05/12/exaforce-raises-125m-series-b-to-build-ai-for-catching-and-stopping-cyberattacks-as-they-happen/) — accessed 2026-10-09
- **[8]** [Business Wire, "Exaforce Raises $125M Series B to Combat AI-Powered Attacks…" (May 12, 2026)](https://www.businesswire.com/news/home/20260512993333/en/Exaforce-Raises-%24125M-Series-B-to-Combat-AI-Powered-Attacks-with-Real-Time-Security-Reasoning) — accessed 2026-10-09
- **[9]** [Security Boulevard, "The 12 Best Agentic SOC Platforms in 2026"](https://securityboulevard.com/2026/07/the-12-best-agentic-soc-platforms-in-2026-architectures-autonomy-levels-and-a-full-comparison/) — accessed 2026-10-09

### 7. 7AI — 7AI Agentic Security Platform

| Field | Value |
|---|---|
| Category | AI SOC analyst — an agentic security platform; TrustRadius lists "7AI Platform" in its AI SOC Analyst category and Intezer files it under "Enterprise AI SOC" [2][3] |
| What it is | An agentic security platform of swarming, domain-specialized AI agents (cloud, email, identity, endpoint) that detect, investigate, respond, and hunt "with humans on the loop" — founded 2024 by Cybereason co-founders Lior Div (CEO) and Yonatan Striem-Amit (CTO), out of stealth February 2025 [1][2] |
| Autonomy | Agentic w/ bounded response — conclusion-driven response actions "with one-click approval and human-in-the-loop options" [3]; vendor states humans remain on the loop [1] |
| Open source | No (proprietary) [1] |
| Deployment | Cloud SaaS that integrates with the existing stack via APIs; available through AWS Marketplace, which lists typical deployment in about seven days [3][4]. On-premises/air-gapped option: not documented in public sources (Unverified) |
| Pricing | Not publicly listed as a standard price card — 7AI's own 2026 comparison states pricing is "not published" [5]; AWS Marketplace shows a 12-month platform entry at $50,000, described as custom pricing with environment-specific quotes [4] |
| Best fit | Enterprises adopting autonomous, agent-driven SOC work without a platform prerequisite [3] |

**Key capabilities**

- Swarming investigation agents, specialized by domain, that enrich data, query the environment, correlate across systems, and reach conclusions with a full evidence trail [3]
- Conclusion-driven response — endpoint isolation, account disabling, IP blocking driven by investigation conclusions, with one-click approval and human-in-the-loop options [3]
- Unified case management: investigations, evidence, and collaboration in one case, with auto-populated summaries and audit trail [3]
- Proactive threat hunting (cross-system correlation, IOC extraction, historical analysis) plus a no-code workflow builder [3]
- Vendor states every deployment includes "dedicated AI Security Engineers" who configure and tune the platform (AWS Marketplace listing) — a service component bundled with the software [4]

**Company and funding:** founded 2024; public launch February 2025 with a $36M seed backed by Greylock Partners, Spark Capital, and CRV [1][6]; $130M Series A led by Index Ventures announced December 2025; vendor states $166M total funding from investors including Index Ventures and Blackstone [1][6]. CRN named 7AI among "The 10 Hottest Cybersecurity Startups of 2026 (So Far)," reporting that it aims to offer a complete agentic AI platform for the SOC [7].

**Strengths / weaknesses.** Intezer credits the swarming agents with covering "the full detection-to-response cycle" and highlights that no SIEM or platform prerequisite is required [3]. Documented weaknesses come from the same roundup: a shorter enterprise track record (founded 2024, launched 2025), multi-agent architectures that "can require fine-tuning before teams rely on them for consistent production results," and sparse third-party verified reviews [3]. Security Boulevard's 2026 roundup tracks 7AI in its "also tracking" shortlist rather than the main 12 [8].

**Versus Vigil.** Overlap: the closest architectural analog in this batch — multiple specialized agents, autonomous investigation to a conclusion, response with human approval gates, case management, and threat hunting, with no required SIEM [1][3]. Differentiators: 7AI is proprietary SaaS with quote-based pricing and a bundled services element ("dedicated AI Security Engineers" [4]); Vigil is Apache 2.0 software, self-hosted or air-gapped, with no per-seat or per-alert metering. Vigil's workflows are Markdown-defined and its detection rules ship in open formats a team can read and fork; 7AI's reasoning and playbooks live inside a closed platform. 7AI's integrations connect to the existing stack over APIs (cross-stack, per its own comparison table [5]); Vigil standardizes on 30+ MCP integrations. Where Vigil wins: licensing and cost transparency, air-gapped/self-hosted control, and inspectable workflows/rules. Where 7AI wins: funding depth ($166M), an enterprise sales motion with AWS Marketplace procurement, and vendor-supplied tuning staff that a pure software project does not include.

**Sources:**

- **[1]** [7AI — Company page (7ai.com)](https://7ai.com/company) — accessed 2026-10-09
- **[2]** [TrustRadius, Best AI SOC Analyst Software 2026 (category listing)](https://www.trustradius.com/categories/ai-soc-analyst) — accessed 2026-10-09
- **[3]** [Intezer, "Top 16 AI SOC Tools for 2026: SOC Automation Compared"](https://intezer.com/blog/top-15-ai-soc-platforms-in-2026) — accessed 2026-10-09
- **[4]** [AWS Marketplace, 7AI Agentic SOC Platform listing](https://aws.amazon.com/marketplace/pp/prodview-2bhzh7e2dlc7k) — accessed 2026-10-09
- **[5]** [7AI blog, "Top AI SOC Platforms in 2026" comparison (vendor-authored)](https://blog.7ai.com/top-ai-soc-platforms-in-2026) — accessed 2026-10-09
- **[6]** [Index Ventures, "Security's Agentic Era Starts Here: Our Investment in 7AI" (Dec 2025)](https://www.indexventures.com/perspectives/securitys-agentic-era-starts-here-our-investment-in-7ai/) — accessed 2026-10-09
- **[7]** [CRN, "The 10 Hottest Cybersecurity Startups of 2026 (So Far)"](https://www.crn.com/news/security/2026/the-10-hottest-cybersecurity-startups-of-2026-so-far) — accessed 2026-10-09
- **[8]** [Security Boulevard, "The 12 Best Agentic SOC Platforms in 2026"](https://securityboulevard.com/2026/07/the-12-best-agentic-soc-platforms-in-2026-architectures-autonomy-levels-and-a-full-comparison/) — accessed 2026-10-09

### 8. Simbian — Simbian AI SOC Agent (Self-Improving Defense platform)

| Field | Value |
|---|---|
| Category | AI SOC analyst — Security Boulevard's 2026 roundup lists Simbian as "autonomous AI SOC agent positioned as a direct SOAR replacement" [3]; the vendor positions a broader multi-agent platform (SOC, Threat Hunt, Pentest, NetSecOps agents on a shared Context Lake) [1] |
| What it is | A reasoning-based AI SOC agent that investigates every alert to a verdict and acts back into the customer's existing tools (EDR, cloud, Active Directory), part of a self-improving defense platform that reads 100+ sources and writes detection rules in the SIEM's own query language [1][2] |
| Autonomy | Agentic w/ bounded response — vendor states "95% of the actions Simbian proposes are approved by your own team" and markets a "Human in Control / You Keep the Gate" model [1] |
| Open source | No (proprietary) [1] |
| Deployment | SaaS; the vendor's AWS Marketplace listing states on-premise or in-cloud deployment options that keep data within the customer's trust boundary [2], while the Agentic Index directory reports SaaS deployment with "no self host or VPC residency option documented" in Simbian's docs — the self-hosting scope is disputed; treat as Unverified and confirm contractually [4] |
| Pricing | Publicly listed on AWS Marketplace as usage-based: $10,000 per 1,000 investigated alerts on a 12-month contract, billed per alert investigated regardless of whether it is a true or false positive [2]. A complete public price sheet (minimums, other products, enterprise terms) is not established [4] |
| Best fit | Lean security teams replacing manual triage and SOAR scripting with a reasoning agent; MSSP/MDR partners extending capacity (customer quotes on the vendor site include MSSP/MDR operators) [1] |

**Key capabilities**

- Reasoning-based investigation of every alert to a verdict — vendor and reviewers emphasize dynamic reasoning over pre-authored playbooks ("no alert ≠ safe," "an alert ≠ a threat" framing) [1][3]
- Acts back into existing infrastructure: takes action in the customer's EDR, cloud, and Active Directory, and writes detection rules in the SIEM's own query language [1]
- Persistent organizational memory ("Context Lake") shared across offensive and defensive agents — SOC, Threat Hunt, Pentest, and NetSecOps — with a TrustedLLM layer; vendor states data never leaves the customer's tenant [1]
- Vendor states automatic resolution of 92% of incoming alerts (AWS Marketplace listing) and "in production across 300+ enterprise environments" (vendor site) — vendor-published figures [1][2]
- Reads security-adjacent context beyond alerts: vulnerability feeds, threat-hunt and pentest reports, ITSM tickets, and runbook PDFs [1]

**Company:** co-founder and CEO Ambuj Kumar; Mountain View, CA address per company profiles [5]. A $10M oversubscribed seed round was reported in 2024, with investors including Gokul Rajaram, Cota Capital, Icon Ventures, Firebolt, and Rain Capital (secondary reporting; no later round verified) [5].

**Strengths / weaknesses.** G2 reviewers (4.5/5) praise 24/7 autonomous triage, elimination of "playbook fatigue," natural-language incident summaries, and integration across SIEM/EDR/identity/cloud tools [6]. Criticisms in reviews and directories: remediation-confidence thresholds need careful initial calibration so automation does not disrupt legitimate business activity; custom connectors may be needed for nonstandard systems; AI decision logs can be cumbersome to audit during initial integration [6]. Deployment claims conflict between the vendor's marketplace listing and third-party documentation (above) [2][4]. Simbian does not appear in Intezer's Top 16 or TrustRadius's AI SOC Analyst category pages; its independent roundup anchor is the Security Boulevard Top 12 entry [3].

**Versus Vigil.** Overlap: both reject rigid playbook automation in favor of reasoning agents, both act into the customer's existing tools, and both gate consequential actions behind human approval (Simbian's "you keep the gate" vs Vigil's human-on-the-loop response). Differentiators: Simbian is proprietary with metered per-1,000-alert pricing (public at $10,000/1,000 alerts on AWS Marketplace [2]); Vigil is Apache 2.0 with no per-alert fees — at high alert volume the commercial models diverge sharply. On detection engineering, Simbian writes rules into the customer's SIEM [1], while Vigil ships 7,200+ curated rules in open Sigma/ESCU/Elastic/KQL formats plus Markdown-defined workflows; on transparency, Vigil's open-source code and inspection-readable workflows have no Simbian equivalent. Deployment: Vigil documents self-hosted/air-gapped operation; Simbian's self-hosting claim is disputed in third-party documentation [2][4]. Where Simbian wins: the offensive-defensive loop (a Pentest agent that validates exploit paths against the live environment, feeding findings back to defense), persistent cross-agent memory, and commercial support with named enterprise references. Where Vigil wins: license, transparency, air-gap, and cost structure at scale.

**Sources:**

- **[1]** [Simbian.ai — "Self-Improving Defense" (vendor site)](https://simbian.ai) — accessed 2026-10-09
- **[2]** [AWS Marketplace, Simbian AI SOC Agent listing](https://aws.amazon.com/marketplace/pp/prodview-77rory5w3laek) — accessed 2026-10-09
- **[3]** [Security Boulevard, "The 12 Best Agentic SOC Platforms in 2026"](https://securityboulevard.com/2026/07/the-12-best-agentic-soc-platforms-in-2026-architectures-autonomy-levels-and-a-full-comparison/) — accessed 2026-10-09
- **[4]** [Agentic Index, Simbian vendor profile](https://agenticindex.io/vendors/simbian) — accessed 2026-10-09
- **[5]** [AGENCCY, Simbian company profile](https://agenccy.ai/catalogue/simbian/) — accessed 2026-10-09
- **[6]** [G2, Simbian reviews](https://www.g2.com/products/simbian/reviews) — accessed 2026-10-09

### 9. Darktrace — Cyber AI Analyst (Darktrace Behavioral Defense Platform)

> **Buying-motion note:** Darktrace is not bought as a standalone AI SOC analyst. The purchase is an NDR-rooted behavioral detection platform (network-first, expanding to email, cloud, OT, identity, SaaS), and Cyber AI Analyst is an embedded investigation capability inside it [1][2][3]. Consistent with that, Darktrace does not appear in TrustRadius's AI SOC Analyst category or Intezer's AI SOC roundup; it is covered in NDR/XDR and AI-threat-detection roundups instead [2][3][4].

| Field | Value |
|---|---|
| Category | XDR / NDR-rooted platform with an embedded AI SOC analyst capability [1][2][3] |
| What it is | A self-learning behavioral AI platform whose Cyber AI Analyst autonomously investigates alerts — including alerts from third-party security tools — mirrors the human investigative process, and produces natural-language summaries and recommended actions [1] |
| Autonomy | Agentic investigation w/ bounded containment — investigation is autonomous and continuous; autonomous response is a separate but integrated platform capability that the vendor states halts malicious activity "while allowing business to continue" [1] |
| Open source | No (proprietary) [1] |
| Deployment | SaaS is the default in 2026; legacy on-premises appliances (DCIP series) still exist per third-party reporting; per-module scope varies [3] |
| Pricing | Not publicly listed — no published price list; custom subscription pricing [2][3]. A third-party pricing guide published by UnderDefense (an MDR provider — treat as a competitor estimate) reports mid-market 500–2,000-device deployments at roughly $150K–$500K ACV and legacy appliances at $24K–$270K per appliance per year [3] |
| Best fit | Organizations that want network-rooted behavioral detection across heterogeneous environments (including OT) with embedded AI investigation — and have SOC capacity to absorb the baseline-period alerting [2][4] |

**Key capabilities**

- Cyber AI Analyst autonomously investigates all alerts, including third-party tool alerts, and re-investigates as new telemetry arrives; each investigation produces detailed natural-language summaries with decision logic and recommended actions [1]
- Vendor states new ML models DEMIST-2 (subtle attacker behavior detection) and DIGEST (escalation prediction) drive "deeper analysis and smarter prioritization" [1]
- Customizable investigative workflows can be triggered from third-party alerts and ingest logs from SIEM, SOAR, log-management, and vulnerability-management systems [1]
- Vendor states fewer than 4% of investigations require human review and positions the capability as "the equivalent of 30 extra analysts" — vendor-published figures, not independently validated [1]
- Platform footprint spans network, email, cloud, OT, identity, and SaaS; vendor states 10,000 customers [1]

**Company:** acquired by Thoma Bravo, with the acquisition formally completed October 1, 2024 [5]. Darktrace acquired cloud-forensics vendor Cado Security in 2025 [6] and network-traffic-visibility vendor Mira Security in July 2025 [7].

**Strengths / weaknesses.** Strengths per independent reviews: broad behavioral visibility across heterogeneous estates, self-learning baselines rather than static signatures, useful threat visualization, and strong enterprise support footprint [2][4]. Criticisms: self-learning detection surfaces anomalies that are not necessarily malicious, creating alert noise and an ongoing tuning burden; a baselining period of roughly two to four weeks before models mature; opaque pricing that complicates budgeting; comparative commentary characterizes Darktrace as broad but less precise than focused NDR and weaker on ATT&CK-oriented detection depth [2][3][4]. Vendor performance figures (the <4% human-review rate) are not independently validated [1].

**Versus Vigil.** The buying motion is the headline difference: Darktrace is sold as a behavioral detection platform rooted in self-learning network telemetry, with the AI analyst embedded; Vigil is an open-source agentic SOC layer that runs on top of a stack the customer already owns. Overlap: both autonomously investigate every alert (including third-party alerts), produce natural-language investigative reports, and offer automated response with human oversight points. Differentiators: Darktrace's detection rests on proprietary self-learning models with a mandatory baseline period [2][3], while Vigil ships 7,200+ curated detection rules in open Sigma/ESCU/Elastic/KQL formats — rules an enterprise can read, audit, and extend, plus optional DeepTempo LogLM. Licensing and deployment: Apache 2.0, self-hosted or air-gapped (Vigil) vs proprietary subscription, SaaS-default with legacy appliances (Darktrace). Response philosophy: Darktrace's design assumes autonomous containment in bounded conditions [1]; Vigil is human-on-the-loop by design. Where Darktrace wins: network telemetry depth, cross-domain breadth including OT, and a mature commercial footprint at 10,000-customer scale. Where Vigil wins: transparency, license cost, air-gapped deployment, and detection engineering that stays inspectable.

**Sources:**

- **[1]** [Darktrace, Cyber AI Analyst product page (vendor)](https://www.darktrace.com/cyber-ai-analyst) — accessed 2026-10-09
- **[2]** [Digital by Default, "Darktrace Review 2026: Does the AI Immune System Actually Work?"](https://digitalbydefault.ai/blog/darktrace-ai-cybersecurity-review-2026) — accessed 2026-10-09
- **[3]** [UnderDefense, "Darktrace Pricing Guide 2026: Real Costs, Hidden Fees" (third-party, competitor-published estimates)](https://underdefense.com/blog/darktrace-pricing-guide/) — accessed 2026-10-09
- **[4]** [Cybersecurity Essentials, "Darktrace vs Vectra AI vs SentinelOne Purple AI" comparison](https://www.cybersecurityessential.com/ai-security/ai-defence/darktrace-vectra-sentinelone-ai-platforms-compared/) — accessed 2026-10-09
- **[5]** [Thoma Bravo, "Thoma Bravo Completes Acquisition of Darktrace" (Oct 1, 2024)](https://www.thomabravo.com/press-releases/thoma-bravo-completes-acquisition-of-darktrace) — accessed 2026-10-09
- **[6]** [The Cyber Throne, "Biggest GoldRush: Major Security Acquisitions in 2025" (Darktrace → Cado Security, ~$150M)](https://thecyberthrone.in/2025/12/29/biggest-goldrush-major-security-acquisitions-in-2025/) — accessed 2026-10-09
- **[7]** [Thoma Bravo, "Darktrace Announces Acquisition of Mira Security" (Jul 21, 2025)](https://www.thomabravo.com/press-releases/darktrace-announces-acquisition-of-mira-security-a-leading-provider-of-network-traffic-visibility-solutions) — accessed 2026-10-09

### 10. UnderDefense — UnderDefense MAXI (Agentic AI SOC platform + MDR service)

> **Buying-motion note:** UnderDefense is first an MDR provider: the flagship offering is 24/7 human-led detection and response, with MAXI as the agentic AI platform layer inside that service [1][2][3]. TrustRadius categorizes UnderDefense as "a managed security service that provides agentic SOC operations and compliance automation" [4]. A self-serve, platform-led entry exists — the vendor states "Start free on the MAXI platform, no sales call required" — but the fully documented operational offering is the managed service, and the free tier's scope versus full MDR is not established in public sources [1][2].

| Field | Value |
|---|---|
| Category | MDR — an agentic AI SOC platform wrapped by a 24/7 human-led MDR service [1][2][3][4] |
| What it is | An agentic AI SOC platform (MAXI) that runs on top of the customer's existing SIEM/XDR without rip-and-replace, auto-triages and investigates every alert, verifies context with users via chat, and pairs with a 24/7 concierge analyst team that owns the last mile of verification and response [2][3] |
| Autonomy | Agentic w/ bounded response — vendor states a tiered model: high-confidence actions (IOC blocking, enrichment) auto-executed; medium-confidence actions (account suspension, endpoint isolation) use recommend-and-confirm; sensitive actions require a human decision [3] |
| Open source | No (proprietary) [2] |
| Deployment | SaaS, the customer's own cloud, or fully on-premises/air-gapped on Kubernetes, with sovereign and bring-your-own model support (Azure AI Foundry, AWS Bedrock, or self-hosted open-source models) per vendor and Intezer [2][3] |
| Pricing | Partially public — vendor states an all-inclusive $11–$15 per endpoint per month covering AI SOC, MDR response, compliance automation, and vCISO advisory (mid-market guide) [5]; a third-party directory lists MDR from $11 per device per month, annual contracts, with a free 14-day trial [6]; G2 lists pricing as not available [7]. Treat figures as vendor-published indicative ranges, not a quote |
| Best fit | Organizations without 24/7 in-house SOC staffing that want outsourced response plus compliance automation; regulated, sovereign, or air-gapped environments (per vendor positioning) [1][2][3] |

**Key capabilities**

- Automated alert investigation: context collection, multi-system correlation, and verification producing structured investigation reports, assigning a verdict to every alert across 250+ integrations (Splunk, Sentinel, Google SecOps, CrowdStrike, Elastic, etc.) [2]
- ChatOps user verification: reaches affected users directly via Slack, Microsoft Teams, email, or SMS to confirm anomalous activity — context fully autonomous systems cannot gather [2]
- Concierge analyst response: a 24/7 analyst team handles hands-on containment and incident response through the same channels [2]
- Detection logic as code: detection rules written in Python, versioned, unit-tested, and deployed through CI/CD, keeping investigative logic observable [2]
- Built-in compliance: maps the same telemetry to SOC 2, HIPAA, PCI-DSS, GDPR, NIS2, DORA, and ISO 27001, with an executive/auditor copilot [2]
- Vendor states ~2-minute alert-to-triage, containment inside 15 minutes for its MDR operation, and automatic closure of 70–85% of confirmed false positives — vendor-published service claims, not independently verified [1][3]. A Unified MAXI Workspace release consolidating the portfolio was announced August 5, 2026 [8]

**Strengths / weaknesses.** G2 reviewers praise the agentic triage ("automatically triage, context-verify, and filter out noise in real time") and seamless integration across cloud infrastructure [7]. Intezer's roundup strengths: vendor-agnostic investigation plus concierge analysts, with per-asset pricing published openly [2]. Weaknesses reported by users on G2 and surfaced by Intezer: onboarding setup effort before the platform is tuned; limits connecting less common or highly customized tools; and "shared control of automation" — because response leans on the provider's concierge analyst team, some control over automated actions sits with the vendor rather than fully in-house [2]. Pricing presentation is inconsistent across the vendor's own channels and directories ($11–$15 range vs "pricing unavailable" on G2) [5][6][7].

**Versus Vigil.** This is the highest-overlap profile in the batch: an overlay architecture on the existing stack, on-premises/air-gapped deployment, bring-your-own model support, tiered human-gated response, and detection-as-code. Differentiators: UnderDefense sells a proprietary platform plus a human service wrap — per-endpoint subscription pricing with the vendor's concierge analysts owning containment [1][2][5] — while Vigil is Apache 2.0 software the customer's team runs, with no per-endpoint fees, 13 specialized agents, 30+ MCP integrations, 7,200+ open-format detection rules, and Markdown-defined workflows the customer owns end to end. Where MAXI wins: organizations that need outsourced 24/7 staffing, built-in compliance automation, and vendor-operated response commitments rather than a toolkit. Where Vigil wins: license and cost structure, full control of detection logic and workflows in open formats, and no dependence on a vendor's analyst team for the response last mile.

**Sources:**

- **[1]** [UnderDefense, Managed Detection and Response (MDR) Services page (vendor)](https://underdefense.com/services/managed-detection-and-response/) — accessed 2026-10-09
- **[2]** [Intezer, "Top 16 AI SOC Tools for 2026: SOC Automation Compared"](https://intezer.com/blog/top-15-ai-soc-platforms-in-2026) — accessed 2026-10-09
- **[3]** [UnderDefense, "AI SOC Guide: Architecture, Capabilities, Pricing, and Migration" (vendor blog)](https://underdefense.com/blog/ai-soc/) — accessed 2026-10-09
- **[4]** [TrustRadius, Best AI SOC Analyst Software 2026 (category listing)](https://www.trustradius.com/categories/ai-soc-analyst) — accessed 2026-10-09
- **[5]** [UnderDefense, "Best AI SOC for Mid-Market: 8 Providers Scored, Priced" (vendor blog; $11–$15/endpoint/month range)](https://underdefense.com/blog/ai-soc-for-mid-market/) — accessed 2026-10-09
- **[6]** [Agentic Index, UnderDefense vendor profile](https://agenticindex.io/vendors/underdefense) — accessed 2026-10-09
- **[7]** [G2, UnderDefense MAXI reviews](https://www.g2.com/products/underdefense-maxi/reviews) — accessed 2026-10-09
- **[8]** [UnderDefense press release, "UnderDefense Launches Unified MAXI Workspace…" (Aug 5, 2026)](https://underdefense.com/company-news/underdefense-launches-unified-maxi-workspace-one-platform-for-agentic-ai-soc-compliance-ai-and-ciso-intelligence-at-enterprise-scale/) — accessed 2026-10-09

## Batch C — Agentic SOAR / Orchestration (profiles 11–15)

### 11. Torq — HyperSOC

| Field | Value |
|---|---|
| Category | Agentic SOAR |
| What it is | Cloud-delivered AI-native SOC platform that layers a multi-agent AI system (the Socrates "omniagent" coordinating specialized HyperAgents) on top of Torq's no-code hyperautomation workflow fabric, covering triage, investigation, response, and case management. |
| Autonomy | Agentic w/ bounded response over a deterministic base: Auto Triage runs on every incoming alert and writes a verdict; Socrates can run the case, calling specialist agents, while approval-gated response steps stay blocked until an analyst confirms (SecureCoding first-party-docs comparison). Vendor states autonomous resolution of up to 95% of alerts (launch materials; not independently audited — Tech-Insider). |
| Open source | No — proprietary SaaS; no open-source license identified in any source reviewed. |
| Deployment | SaaS (deployed as a cloud service — CybersecTools; SecureCoding). |
| Pricing | No official rate card. AWS Marketplace's public contract listing shows $450,000 for each 12-month plan tier (Essential, Enterprise, Elite) with unit-based billing (AWS Marketplace; SecureCoding notes the posted line is a contract figure, not a confirmed all-in invoice). A third-party 2026 comparison reports entry points near $300/month for small deployments, scaling with workflow volume and integrations (Tech-Insider). |
| Best fit | Mid-size to large enterprises and MSSPs with high alert volumes that want Tier-1 triage and case closure automated on top of an existing multi-vendor security stack (checkthat.ai; UnderDefense). |

**Key capabilities:**

- **Auto Triage verdict engine:** enriches alerts, normalizes to OCSF, applies deterministic rules for critical assets/users, then writes true/false-positive, urgency, risk, evidence, MITRE ATT&CK mapping, and suggested actions (SecureCoding).
- **Multi-agent investigation:** Socrates coordinates runbook, investigation, remediation, and case-management agents; HyperAgents work across triage, investigation, and response; customers can embed AI Agent/AI Task steps in workflows running on models they select via their own OpenAI/Azure OpenAI/Vertex AI keys (Agentic Index).
- **Native MCP support:** HyperSOC-2o is described as a multi-agent system with native Model Context Protocol support, pulling context mid-investigation through MCP-connected tools (Tech-Insider).
- **Integration breadth:** Vendor states 300+ prebuilt integrations and 4,000+ workflow steps (Torq blog); AWS Marketplace lists 500+ third-party tools; independent launch coverage cited 200+ supported security tools — counts vary by source and edition (Tech-Insider).
- **Case management with "SOC memory":** malicious verdicts promote into cases; confirmations, overrides, closure reasons, and escalation paths feed subsequent triage (SecureCoding).

**Strengths / weaknesses:**
Ratings: Vendor-relayed Gartner Peer Insights 4.8/5 across 51 SOAR-market reviews as of 2026-02-17 (torq.io); AWS Marketplace aggregate 4.8 from 172 ratings; an independent directory review scores Torq 7.3/10 overall with Value-for-money 6/10 (Recatools). Praised: no-code/low-code workflow building, integration breadth, and responsive support (Recatools; torq.io customer reviews). Criticized: a steep learning curve for advanced workflow construction (Security Boulevard, "An Honest Comparison"); a PeerSpot reviewer reports integration throttling, dropped events, and message-processing backlogs under load (PeerSpot); a high contract floor relative to open-source options ($450K posted listing, AWS Marketplace).

**Versus Vigil:**
Overlap: both run multi-agent agentic triage and investigation over an alert-to-case lifecycle with case management and human approval gates, and both speak MCP — Vigil's 30+ integrations are MCP-based, while HyperSOC-2o supports MCP natively. Differentiators: Vigil is Apache-2.0 open source, self-hostable, and air-gappable; HyperSOC is proprietary cloud-only SaaS. Authoring: Torq uses a no-code visual builder; Vigil defines workflows in Markdown, reviewable as diffs in git. Detection engineering: Vigil ships 7,200+ detection rules (Sigma/ESCU/Elastic/KQL); no Torq source reviewed mentions a shipped detection-rule library. Where Vigil wins: licensing and cost structure, self-hosting/air-gap, workflow-as-code reviewability, detection-rule coverage, and agent transparency (13 open-source agents vs closed HyperAgents). Where Torq wins: integration breadth (300+ vs 30+), enterprise deployment maturity, turnkey SaaS operation, and market validation (Gartner PI 4.8/51 vendor-relayed; named enterprise customers including Carvana, PepsiCo, Siemens, Uber, Marriott per strike48).

**Sources:**

- [Torq — The Torq AI SOC Platform](https://torq.io/ai-soc-platform/) — accessed 2026-10-09
- [Agentic Index — Torq Features & Pricing](https://agenticindex.io/vendors/torq) — accessed 2026-10-09
- [SecureCoding — Tines vs Torq: story-built cases or agentic alert triage?](https://www.securecoding.com/compare/tines-vs-torq/) — accessed 2026-10-09
- [Tech-Insider — Torq vs Tines vs Cortex XSIAM: SOAR Platform Compared (2026)](https://tech-insider.org/torq-vs-tines-vs-cortex-xsiam-2026/) — accessed 2026-10-09
- [Security Boulevard — The Best AI SOC Platforms in 2026: An Honest Comparison](https://securityboulevard.com/2026/09/the-best-ai-soc-platforms-in-2026-an-honest-comparison/) — accessed 2026-10-09
- [Security Boulevard — The 12 Best Agentic SOC Platforms in 2026](https://securityboulevard.com/2026/07/the-12-best-agentic-soc-platforms-in-2026-architectures-autonomy-levels-and-a-full-comparison/) — accessed 2026-10-09
- [AWS Marketplace — Torq HyperSOC listing and reviews](https://aws.amazon.com/marketplace/pp/prodview-2c4o6nqsvkxhy) — accessed 2026-10-09
- [Recatools — Torq Review: No-Code Security Automation](https://recatools.com/ai-directory/torq/) — accessed 2026-10-09
- [PeerSpot — What advice do you have for others considering Torq?](https://www.peerspot.com/questions/what-advice-do-you-have-for-others-considering-torq) — accessed 2026-10-09
- [CybersecTools — Torq HyperSOC](https://cybersectools.com/tools/torq-hypersoc) — accessed 2026-10-09
- [strike48 — Torq competitors](https://www.strike48.com/post/torq-competitors) — accessed 2026-10-09

### 12. Swimlane — Turbine

| Field | Value |
|---|---|
| Category | Agentic SOAR |
| What it is | Low-code security automation platform combining deterministic drag-and-drop playbooks with Swimlane's Hero AI agent capabilities for alert investigation, triage, response orchestration, vulnerability management, and compliance workflows (Swimlane; Security Boulevard). |
| Autonomy | Hybrid — AI agents inside deterministic playbooks: Turbine playbooks are triggers, logic, actions, components, inputs, and outputs built visually in Turbine Canvas, and can include AI-agent actions (Swimlane docs). Vendor states intelligent routing assigns deterministic automation, AI-assisted workflows, or fully agentic investigation by alert complexity, with analyst approval required for actions like endpoint isolation; roundups classify Turbine as low-code SOAR with the Hero AI agent fleet layered on a playbook foundation, not an autonomous AI SOC (Security Boulevard). |
| Open source | No — proprietary commercial platform; no open-source license identified in sources reviewed. |
| Deployment | Both — Vendor states Turbine runs in Swimlane Cloud, self-hosted on-premises, and air-gapped environments (Swimlane enterprise packaging; Turbine overview datasheet). |
| Pricing | Action-volume-based, quote-backed. Vendor publishes five enterprise tiers (Starter, Core, Plus, Premium, Elite) banded by average daily automated actions, with entry volumes around 50,000 actions/day scaling toward 500,000+, Hero AI packaged via credits/prompt packs, and dollar pricing by quote (Swimlane enterprise packaging). UnderDefense's 2025 comparison estimates a starter Turbine deployment at roughly $47,000–$47,250/year for five users — an external estimate, not a price list (UnderDefense). |
| Best fit | Enterprises and MSSPs, including regulated or government environments, that need auditable automation with on-prem or air-gapped deployment and want to move gradually from fixed playbooks toward agentic operation (Security Boulevard). |

**Key capabilities:**

- **Turbine Canvas:** low-code visual playbook development with drag-and-drop actions, triggers, and reusable components (Swimlane docs, Playbooks Overview).
- **Hero AI agents:** Vendor states specialized agents for playbook generation, data ingestion, visualization, investigation, and decision support; customers can select the AI model per agent including BYOM (AWS Bedrock, Anthropic) and disable Hero AI per account (swimlane.com AI SOC page).
- **Marketplace breadth:** Vendor states thousands of pre-built playbooks, components, and AI agents available through the Swimlane Marketplace (swimlane.com; docs.swimlane.com).
- **MSSP multi-tenancy:** Vendor states per-client isolated tenants with tiers aggregating daily actions across clients, tenants, and regions (Swimlane MSSP packaging).
- **App Builder:** Vendor states low-code creation of custom interfaces and applications on the platform (Swimlane enterprise packaging).

**Strengths / weaknesses:**
Ratings: G2 4.5/5 from 45 reviews (G2; rating metadata updated 2026-09-29); TrustRadius 10/10 but from only 2 reviews — low evidentiary weight (TrustRadius); SoftwareReviews 7.6/10 composite across 36 reviews (SoftwareReviews). Praised (G2): robust reporting, case management, dashboards, customizable playbooks, automation of triage/enrichment, reduced analyst workload, and flexibility. Criticized (G2): resource-intensive deployment and playbook design, need for engineering expertise, connector/API maintenance, and occasional slowness or outages; SoftwareReviews separately cites "higher pricing structure" and "complex setup and user interface" among dislikes.

**Versus Vigil:**
The closest deployment-parity competitor in this batch: like Vigil, Swimlane offers on-premises and air-gapped deployment alongside cloud, and both combine deterministic automation with agentic AI. Differentiators: licensing (Apache-2.0 vs proprietary), authoring (Turbine Canvas drag-and-drop and proprietary playbook objects vs Vigil's Markdown-as-code diffable in git), commercial model (action-volume tiers plus AI credit packs vs free open-source self-hosting), integration approach (large proprietary marketplace vs Vigil's 30+ MCP integrations), and detection engineering (Vigil ships 7,200+ detection rules; no Swimlane source reviewed mentions a shipped detection-rule library). Where Vigil wins: open license, no per-action metering or AI credit packs, code-reviewable workflows, detection rules included, and transparency of the agent stack. Where Swimlane wins: enterprise and MSSP maturity at scale, marketplace breadth, native dashboards/App Builder, and a regulated-sector track record that roundups single out.

**Sources:**

- [Swimlane — Turbine, the Agentic AI Automation Platform](https://swimlane.com/swimlane-turbine/) — accessed 2026-10-09
- [Swimlane — Enterprise Pricing and Packaging](https://swimlane.com/platform/enterprise-packaging/) — accessed 2026-10-09
- [Swimlane — AI SOC powered by Swimlane Turbine](https://swimlane.com/product/ai-soc/) — accessed 2026-10-09
- [Swimlane docs — Playbooks Overview](https://docs.swimlane.com/playbooks-overview) — accessed 2026-10-09
- [Swimlane — Turbine Overview datasheet (deployment models)](https://45377644.fs1.hubspotusercontent-na1.net/hubfs/45377644/2025%20Sponsor%20Assets/Turbine%20Overview%20-%20Swimlane.pdf) — accessed 2026-10-09
- [UnderDefense — Andesite vs. Swimlane: AI SOC Showdown for 2025](https://underdefense.com/blog/andesite-vs-swimlane-the-2025-ai-soc-dilemma/) — accessed 2026-10-09
- [G2 — Swimlane Reviews](https://www.g2.com/products/swimlane/reviews) — accessed 2026-10-09
- [SoftwareReviews — Swimlane reviews](https://www.softwarereviews.com/products/swimlane?c_id=218) — accessed 2026-10-09
- [TrustRadius — Swimlane](https://www.trustradius.com/products/swimlane) — accessed 2026-10-09
- [Security Boulevard — The 10 Best Splunk SOAR Alternatives in 2026](https://securityboulevard.com/2026/08/the-10-best-splunk-soar-alternatives-in-2026-compared-before-the-python-playbook-migration/) — accessed 2026-10-09

### 13. D3 Security — Morpheus

| Field | Value |
|---|---|
| Category | Agentic SOAR |
| What it is | AI SOC platform unveiled March 2025 (GA planned for August 2025) that ingests alerts from an existing security stack, performs AI-led investigation and attack-path discovery, generates a response playbook at runtime for each incident, and executes response through a built-in deterministic orchestration engine with case management and an audit trail (MSSP Alert; d3security.com FAQ). |
| Autonomy | Agentic w/ bounded response — the most aggressively agentic positioning in this batch. Investigation and planning are AI-led and runtime-generated (Attack Path Discovery, Adaptive Tasking); execution runs through a deterministic engine inside hard guardrails with configurable autonomy modes; Vendor states that when Morpheus is uncertain it defers to a human (d3security.com; d3security.com/enterprise). Security Boulevard's 2026 roundup ranks D3 Morpheus first among agentic SOC platforms as the "unified-engine" reference implementation. |
| Open source | No — proprietary commercial platform with annual subscription licensing; no open-source license identified in sources reviewed. |
| Deployment | Both — Vendor states SaaS, hybrid, on-premises, sovereign-region, and fully air-gapped options, with SaaS connecting to on-prem SIEM/EDR via a D3 proxy agent and cloud running on Azure (d3security.com/enterprise; d3security.com/ai-soc-platform). These are vendor-stated options; independent feature-parity verification across deployment modes was not found. |
| Pricing | Partially public. Vendor states an annual platform subscription sized to the SOC's alert-volume envelope with AI included (no token costs or usage meter), 800+ integrations included, and per-alert overage published in advance (d3security.com/agentic-soc-platform; d3security.com/enterprise); a vendor marketing page advertises $0.27 per alert investigated as a comparison claim (d3security.com/ai-soc-platform). No standard public rate card. |
| Best fit | Organizations — including MSSPs needing per-client tenant isolation — that want one unified agentic reasoning-and-orchestration engine over an existing stack, with accountability-grade audit trails (Security Boulevard; d3security.com). |

**Key capabilities:**

- **Attack Path Discovery:** Vendor states full L2-depth attack-path analysis on every alert, horizontal and vertical, feeding a structured case file with attack narrative, risk score, blast radius, MITRE ATT&CK mapping, entity relationships, and timelines (d3security.com FAQ).
- **Runtime-generated response playbooks:** response plans tailored to the specific incident, environment, and available tools rather than pre-authored playbooks (d3security.com; echoed by Security Boulevard's roundup as D3's differentiator).
- **Bounded agentic task nodes:** Vendor states limits on iteration, tools, cost, and approval gates, with a deterministic engine that "executes exactly what your team approved" inside the autonomy mode set per alert type (d3security.com/morpheus/agentic-soc/swimlane; d3security.com/enterprise).
- **Unified platform:** Vendor states built-in SOAR, case management, orchestration, and audit trail as one product, with 800+ integrations included (d3security.com FAQ).
- **Conversational threat hunting and dynamic playbook generation** (G2 seller page for D3 Security).

**Strengths / weaknesses:**
G2 seller reviews (71 reviews) highlight integration flexibility — one reviewer built a Python API to integrate an unsupported SIEM — and a unified investigation/hunting/playbook-generation/response workspace (G2). Weaknesses: a young product — unveiled 2025-03-19 with general availability planned for August 2025 (MSSP Alert) — so independent production evidence is thin; nearly all performance claims (sub-two-minute investigation, 80% MTTR reduction, self-healing integrations) are vendor-sourced; and pricing is opaque beyond the model description.

**Versus Vigil:**
The sharpest architectural contrast in this batch: D3 generates the response plan at runtime from live evidence, while Vigil's 13 specialized agents operate over Markdown-defined workflows; both keep humans in the loop and both offer air-gapped deployment (Vigil by design, D3 vendor-stated). Differentiators: licensing (Apache-2.0 vs proprietary subscription), integration breadth (D3's vendor-claimed 800+ vs Vigil's 30+ MCP), detection engineering (Vigil ships 7,200+ rules across Sigma/ESCU/Elastic/KQL; no D3 detection-rule library appears in sources reviewed), and transparency (Vigil's open agent stack and optional DeepTempo LogLM vs D3's proprietary single-LLM "Unified Intelligence Model"). Where Vigil wins: open licensing and self-hosting economics, code-defined workflow reviewability, detection rules included, and an auditable open-source trail. Where D3 wins: claimed depth of automated per-alert L2 investigation, MSSP multi-tenancy with per-client policy isolation, and consolidation of SOAR + case management + audit into one vendor platform.

**Sources:**

- [D3 Security — Morpheus FAQ](https://d3security.com/faq/) — accessed 2026-10-09
- [D3 Security — The Accountable Agentic SOC Platform](https://d3security.com/) — accessed 2026-10-09
- [D3 Security — Morpheus for the Enterprise SOC](https://d3security.com/morpheus/enterprise/) — accessed 2026-10-09
- [D3 Security — Agentic SOC Platform](https://d3security.com/agentic-soc-platform/) — accessed 2026-10-09
- [D3 Security — AI SOC Platform ($0.27/alert comparison)](https://d3security.com/ai-soc-platform/) — accessed 2026-10-09
- [MSSP Alert — D3 Security Unveils Morpheus (2025-03-19)](https://www.msspalert.com/news/d3-security-unveils-morpheus-its-ai-powered-autonomous-soc) — accessed 2026-10-09
- [G2 — D3 Security Management Systems seller reviews](https://www.g2.com/sellers/d3-security-management-systems) — accessed 2026-10-09
- [Security Boulevard — The 12 Best Agentic SOC Platforms in 2026](https://securityboulevard.com/2026/07/the-12-best-agentic-soc-platforms-in-2026-architectures-autonomy-levels-and-a-full-comparison/) — accessed 2026-10-09

### 14. Tines — Stories / Tines 3B

| Field | Value |
|---|---|
| Category | Agentic SOAR |
| What it is | No-code workflow-automation platform for security and IT: visual "Stories" connect tools, APIs, approvals, and cases, with AI embedded as actions (AI Agent Action, June 2025) rather than as an autonomous SOC-analyst layer (tines.com; Tech-Insider). |
| Autonomy | Workflow-first with embedded AI: builders place AI Agent actions inside Stories they version and debug, and no published autonomous-investigation percentage exists; roundups position Tines as a workflow authoring platform rather than an autonomous SOC (Security Boulevard; SecureCoding). Tines 3B, launched 2025-07-31, is a separate AI-native environment where a builder describes a process in plain language and Tines generates, runs, and monitors the resulting apps, agents, and automations — explorable by existing customers at no extra charge (SecureCoding; cybercompanyprofiles). |
| Open source | No — proprietary commercial platform; no open-source license identified in sources reviewed. |
| Deployment | Both (reported): SaaS cloud tenant as the core model; SecureCoding's first-party-docs comparison reports Business and Enterprise editions can self-host. Confirm self-hosting entitlement contractually before relying on it. |
| Pricing | The most transparent entry pricing in this batch: Community Edition free (1 builder, 3 flows, 25,000 events/month, unlimited viewers, SSO); Starter $500/month for 2 builders (per Tech-Insider citing Tines' pricing page and G2); Business and Enterprise quoted — independent 2026 breakdowns put typical enterprise deployments at $50,000+/year (Tech-Insider). Cases are a paid add-on that also unlocks records and dashboards (SecureCoding). |
| Best fit | Engineering-leaning security teams that want tool-agnostic automation they author, own, and debug long-term — including SOC-adjacent IT and business workflows — without being locked into a vendor connector catalog (Tech-Insider; Security Boulevard). |

**Key capabilities:**

- **Stories:** visual no-code workflows built from webhooks, HTTP/JSON actions, Pages for human approvals, and schedules — connecting to any tool with an API rather than a counted connector catalog (tines.com case studies; Tech-Insider).
- **Cases (paid add-on):** group related security activity, investigation context, tasks, and workflow outputs; the add-on also unlocks records and dashboards (SecureCoding).
- **AI Agent Action:** teams can define and distribute agents that operate inside existing Tines processes (Tines blog, 2025-06-24).
- **Tines 3B:** a separate AI-native environment for agents, apps, and automations, with paid plans scaling "Tines units" at 150k/300k/600k per month and dollar rates quote-only (SecureCoding; cybercompanyprofiles).
- **Audit and versioning:** replayable story runs, version history, audit logs, and SCIM provisioning via the platform API (apis.io; SecureCoding).

**Strengths / weaknesses:**
Ratings: G2 4.7/5 across 397 reviews — among the strongest review bases in the category (G2; checkthat.ai). Praised (G2): ease of use without programming expertise, automation power, integration of security tools, time savings, and support. Criticized (G2): a learning curve for new automation users, documentation gaps, debugging complex workflows and tracing events across actions, complex data transformations requiring API familiarity, missing functionality and occasional bugs, and expense in some reviews.

**Versus Vigil:**
The authoring contrast is the heart of this comparison: Tines optimizes for analyst-readable Stories inside a proprietary visual canvas; Vigil's Markdown-as-code achieves the same human readability as plain text under git — reviewable in pull requests, diffable, with no canvas lock-in. Functionally, Tines makes no autonomous-investigation claim — third-party coverage frames it as the human-designed-workflow bet — while Vigil runs 13 specialized agents for triage, investigation, hunting, correlation, and forensics. Tines' generic HTTP/API connectivity model contrasts with Vigil's 30+ MCP integrations, and Tines ships no detection-rule library (Vigil: 7,200+ across Sigma/ESCU/Elastic/KQL). Where Vigil wins: agentic investigation depth, detection engineering, open-source licensing, self-host/air-gap without edition gates, and case management not gated as a paid add-on. Where Tines wins: usability maturity at scale (G2 4.7/397), breadth beyond SOC into IT and business automation, a free Community tier for prototyping, and a large named-customer base (Databricks, GitLab, Coinbase, Elastic, Reddit per Tech-Insider).

**Sources:**

- [Tines — Introducing the AI Agent Action (2025-06-24)](https://www.tines.com/blog/introducing-ai-agents/) — accessed 2026-10-09
- [Tines — Turo case study](https://www.tines.com/case-studies/turo/) — accessed 2026-10-09
- [SecureCoding — Tines vs Torq (includes Tines editions, 3B, Cases)](https://www.securecoding.com/compare/tines-vs-torq/) — accessed 2026-10-09
- [Tech-Insider — Torq vs Tines vs Cortex XSIAM (2026)](https://tech-insider.org/torq-vs-tines-vs-cortex-xsiam-2026/) — accessed 2026-10-09
- [G2 — Tines Reviews (4.7/5, 397 reviews)](https://www.g2.com/it/products/tines/reviews) — accessed 2026-10-09
- [checkthat.ai — Best SOAR tools (Tines rating corroboration)](https://checkthat.ai/answers/what-are-the-best-soar-tools-available) — accessed 2026-10-09
- [apis.io — Tines API provider profile](https://apis.io/providers/tines/) — accessed 2026-10-09
- [Security Boulevard — Best SOAR Alternatives in 2026: The Agentic Platforms Replacing Legacy SOAR](https://securityboulevard.com/2026/07/best-soar-alternatives-in-2026-the-agentic-platforms-replacing-legacy-soar/) — accessed 2026-10-09
- [cybercompanyprofiles — Tines: Funding, Competitors and Strategy](https://cybercompanyprofiles.com/companies/tines) — accessed 2026-10-09

### 15. Palo Alto Networks — Cortex XSOAR

| Field | Value |
|---|---|
| Category | Agentic SOAR |
| What it is | Palo Alto Networks' enterprise SOAR platform: visual playbooks orchestrate integrations, incident management, investigation, and threat-intelligence operations across the security stack, backed by a large content-pack marketplace (PANW documentation; Tech-Insider). |
| Autonomy | Playbook-first with AI assistance — the deterministic anchor of this batch. The core operating model is predefined visual playbooks (conditions, approvals, branching, scripts) with human decisions at designated points; an ML-driven assistant learns from analyst actions and offers guidance on assignments and commands, and GenAI capabilities assist summarization and guidance (PANW datasheet). Palo Alto named Cortex AgentiX the next-generation successor to XSOAR (announced 2025-10-28), delivered first in Cortex Cloud and XSIAM with a standalone platform following in early 2026 — the vendor's agentic investment sits beyond classic XSOAR (Security Boulevard). |
| Open source | No — proprietary; integrations, playbooks, scripts, and content packs are distributed under commercial terms. Git-based content development is a workflow mechanism, not an open-source license (PANW docs). |
| Deployment | Both: XSOAR 8 SaaS and a distinct XSOAR 8 on-premises documentation track; multi-tenant deployments for enterprises and MSSPs (XSOAR 8 supports single- and multi-tenant for new customers, with SaaS child tenants on separated infrastructure; older hosted multi-tenant was enterprise-only, not MSSP). XSOAR 8.14 SaaS reached GA on 2026-05-03 (PANW docs; Tech-Insider). |
| Pricing | Not publicly listed. XSOAR 8 SaaS requires a yearly per-user license (multi-year available), with separate licensing for multi-tenant/child and development tenants (PANW licensing docs); PeerSpot reviewers consistently describe it as expensive, especially for SMBs (PeerSpot). For context only — a related product, not XSOAR: a third-party 2026 analysis estimates Cortex XSIAM at £200,000–£1M+/year depending on ingestion and user count (Tech-Insider). |
| Best fit | Large, Palo Alto-committed SOCs and MSSPs that need mature, deeply integrated orchestration and can absorb licensing and implementation costs (PeerSpot review pattern). |

**Key capabilities:**

- **Visual playbooks + content packs:** 1,000+ built-in playbooks across the Cortex ecosystem with conditional logic, approvals, retries, and human-decision steps (Tech-Insider; PANW datasheet).
- **Incident/case management:** centralized incident queues, ownership, analyst assignment, investigation tasks, evidence handling, SLAs, and escalation (PANW docs).
- **Threat-intelligence operations:** indicator ingestion, enrichment, scoring, deduplication, and distribution across feeds and platforms (PANW docs).
- **Git-based content development:** develop and test content in a development tenant against a built-in or private remote repository before promoting to production (PANW deployment docs).
- **Multi-tenancy:** parent/child tenant administration with segregated tenant data and permissions for MSSP and enterprise deployments (PANW XSOAR 8 FAQs).

**Strengths / weaknesses:**
Ratings: PeerSpot average 8.4/10 (displayed 4.2/5; 62 reviews; 92% willing to recommend) — ranked #2 in PeerSpot's SOAR category (PeerSpot, 2026-08-12); checkthat.ai's aggregation cites Gartner Peer Insights 4.5/5 from 69 ratings, with a February 2026 reviewer calling it "mature, reliable and extremely powerful for automating SOC workflows" (checkthat.ai). Praised (PeerSpot): playbook customization, broad third-party integrations, effective automation of repetitive SOC work, reduced investigation time, scalability, and stability. Criticized (PeerSpot): high cost especially for SMBs, complex setup and integration, learning curve for playbook development, playbook creation/debugging effort, UI and documentation improvements needed, and some reviewers wanting more AI assistance.

**Versus Vigil:**
The incumbent contrast: XSOAR executes predefined workflows, while Vigil's 13 specialized agents reason over evidence with human-on-the-loop response. Differentiators: licensing (Apache-2.0 vs proprietary), deployment (XSOAR SaaS and on-prem are separate tracks with PANW licensing machinery, vs Vigil self-hosted/air-gapped by design), authoring (visual editor + Python + Git-based content packs — code-adjacent but proprietary formats, not Markdown-as-code), integrations (a far broader commercial catalog vs Vigil's 30+ MCP), and detection engineering (Vigil ships 7,200+ Sigma/ESCU/Elastic/KQL rules; XSOAR content packs are playbooks and integrations, not a detection-rule library, per sources reviewed). Where Vigil wins: open license and cost structure, agentic depth, detection rules included, and vendor-neutral positioning — XSOAR reviewers themselves ask for more AI assistance, and Palo Alto's own roadmap moved agentic capability to AgentiX/XSIAM. Where XSOAR wins: enterprise maturity and scale, deep ecosystem consolidation for Palo Alto shops, MSSP multi-tenancy at scale, and decades of content-pack investment.

**Sources:**

- [PANW — Understand Cortex XSOAR licenses](https://cortex-docs.paloaltonetworks.com/cortex-xsoar-8-saas/learn-about-cortex-xsoar/understand-cortex-xsoar-licenses) — accessed 2026-10-09
- [PANW — Cortex XSOAR 8 FAQs: MSSP and Multi-Tenancy Deployment](https://docs-cortex.paloaltonetworks.com/r/Cortex-XSOAR/8/Cortex-XSOAR-8-FAQs/MSSP-and-Multi-Tenancy-Deployment) — accessed 2026-10-09
- [PANW — Multi-Tenant Overview (6.13 hosted/enterprise-MSSP entitlements)](https://docs-cortex.paloaltonetworks.com/r/Cortex-XSOAR/6.13/Cortex-XSOAR-Multi-Tenant-Guide/Multi-Tenant-Overview) — accessed 2026-10-09
- [PANW — Plan and prepare your deployment (Git-based content dev)](https://cortex-docs.paloaltonetworks.com/cortex-xsoar-8-saas/onboard-cortex-xsoar/plan-and-prepare-your-deployment.md) — accessed 2026-10-09
- [PeerSpot — Palo Alto Networks Cortex XSOAR reviews](https://www.peerspot.com/products/palo-alto-networks-cortex-xsoar-reviews) — accessed 2026-10-09
- [checkthat.ai — Best SOAR tools available (XSOAR ratings corroboration)](https://checkthat.ai/answers/what-are-the-best-soar-tools-available) — accessed 2026-10-09
- [Tech-Insider — Torq vs Tines vs Cortex XSIAM (XSOAR 8.14 GA, playbook counts, XSIAM cost ranges)](https://tech-insider.org/torq-vs-tines-vs-cortex-xsiam-2026/) — accessed 2026-10-09
- [Security Boulevard — The 10 Best Splunk SOAR Alternatives in 2026 (AgentiX succession)](https://securityboulevard.com/2026/08/the-10-best-splunk-soar-alternatives-in-2026-compared-before-the-python-playbook-migration/) — accessed 2026-10-09
- [PANW Cortex XSOAR datasheet (PDF, ML-driven assistant)](https://www.boll.ch/datasheets/Cortex_XSOAR.pdf) — accessed 2026-10-09

## Batch D — Suite Platforms (profiles 16–20)

### 16. Palo Alto Networks — Cortex XSIAM / Cortex AgentiX

| Field | Value |
|---|---|
| Category | Suite copilot (AI-driven SOC platform with embedded agentic AI) |
| What it is | Palo Alto Networks' cloud-delivered SOC platform that converges SIEM, SOAR, EDR/XDR, NDR, CDR, and threat intelligence into one platform, with Cortex AgentiX as its agentic-AI layer for building, deploying, and governing security AI agents. |
| Autonomy | Agentic with bounded response — agents reason, plan, and execute workflows, can be prompted or triggered autonomously, and are governed by roles, permissions, and human-in-the-loop approvals; Security Boulevard scores its autonomy ceiling at AL3 (AI-led with human review). |
| Open source | No |
| Deployment | Vendor-hosted cloud SaaS (customer-side collectors, endpoint agents, and response connectors run in the customer environment); no self-hosted option found in public materials. |
| Pricing | Not publicly listed (custom-quoted; Security Boulevard describes the model as usage-based, per-GB plus per-user). |
| Best fit | Enterprises already standardized on the Palo Alto/Cortex estate that want to consolidate the SOC onto XSIAM with governed agentic automation. |

**Key capabilities:**
- Vendor states XSIAM unifies SIEM, SOAR, EDR, NDR, and CDR on one data layer and applies 2,900+ ML models and 13,300+ detections, claiming 100% MITRE ATT&CK detection coverage and a 98% MTTR reduction. (Palo Alto Networks — Cortex XSIAM)
- Vendor states AgentiX deploys an AI agent workforce that can be prompted in real time or triggered autonomously, with administrators defining when agents act independently and when high-impact actions require human-in-the-loop approval. (Palo Alto Networks — Cortex AgentiX)
- Vendor states AgentiX carries 1,100+ prebuilt integrations and native Model Context Protocol (MCP) support, including a Cortex MCP Server that lets an external LLM query Cortex data, plus prebuilt agents (e.g., Case Investigation Agent). (Palo Alto Networks — Cortex AgentiX)
- Security Boulevard (July 2026) categorizes AgentiX as an "Ecosystem-Native Agent" with an AL3 autonomy ceiling and 200+ integrations that are "strongest inside the Palo Alto estate," and notes Palo Alto named AgentiX the successor to Cortex XSOAR on October 28, 2025. (Security Boulevard, July 2026)
- Vendor states the July 2026 release (XSIAM 3.6 / AgentiX 1.4) broadened use of frontier models and achieved FedRAMP Moderate and High authorization for AgentiX. (Palo Alto Networks — What's New in Cortex, July 2026)

**Strengths / weaknesses:** G2 reviewers praise XSIAM's alert correlation and noise reduction, automation of routine triage, and unified visibility across endpoint, network, identity, and cloud. Recurring complaints are high ingestion-based cost, complex implementation requiring tuning and professional services, a steep learning curve, and dashboard/usability issues — a pattern that weighs most on smaller teams without an existing Palo Alto investment (G2 — Cortex XSIAM reviews). The Swimlane-authored September roundup places AgentiX as "platform-native," best for "Cortex/XSIAM shops; governance + prebuilt agents," with the explicit watch-out "Ecosystem-centric" (Security Boulevard, September 2026).

**Versus Vigil:** Overlap: both are agentic SOCs with multi-agent investigation, response automation, and human-on-the-loop gates. Differentiators: XSIAM/AgentiX is a proprietary, cloud-hosted commercial platform whose comparison strengths — first-party telemetry fidelity, 13,300+ vendor-maintained detections, 1,100+ integrations, FedRAMP authorizations — come with vendor-state lock-in: Security Boulevard's architecture analysis says ecosystem-native agents are "zero-friction if you live in that ecosystem; third-party stack coverage is second-class," and the September roundup's watch-out for AgentiX is literally "Ecosystem-centric." Vigil is the open-stack alternative: Apache 2.0 licensed, self-hosted or air-gapped, with 7,200+ detection rules in open formats (Sigma/ESCU/Elastic/KQL) and 30+ MCP integrations that treat the customer's existing SIEM/EDR stack as first-class rather than second-class. Notably, AgentiX's own MCP support (vendor page) narrows the protocol gap — MCP alone is no longer a Vigil exclusive — so the durable Vigil differentiators are license, deployment model (self-hosted/air-gapped vs. vendor-hosted SaaS), and open detection formats. Where the suite wins on cited evidence: enterprise scale, certified governance (FedRAMP, per vendor), and depth on Palo Alto telemetry, at the price G2 reviewers flag as ingestion-expensive.

**Sources:**
- [Explore Cortex XSIAM Security Analytics — Palo Alto Networks](https://www.paloaltonetworks.com/cortex/cortex-xsiam) — accessed 2026-10-09
- [Cortex AgentiX — Palo Alto Networks](https://www.paloaltonetworks.com/cortex/agentix) — accessed 2026-10-09
- [The 12 Best Agentic SOC Platforms in 2026 — Security Boulevard](https://securityboulevard.com/2026/07/the-12-best-agentic-soc-platforms-in-2026-architectures-autonomy-levels-and-a-full-comparison/) — accessed 2026-10-09
- [The Best AI SOC Platforms in 2026: An Honest Comparison — Security Boulevard (Swimlane)](https://securityboulevard.com/2026/09/the-best-ai-soc-platforms-in-2026-an-honest-comparison/) — accessed 2026-10-09
- [Cortex XSIAM Reviews — G2](https://www.g2.com/products/palo-alto-cortex-xsiam/reviews) — accessed 2026-10-09
- [What's New in Cortex (July '26) — Palo Alto Networks Blog](https://www.paloaltonetworks.com/blog/security-operations/whats-new-in-cortex-july-2026/) — accessed 2026-10-09

### 17. CrowdStrike — Charlotte AI + Falcon Next-Gen SIEM

| Field | Value |
|---|---|
| Category | Suite copilot (agentic AI layer + cloud-native SIEM inside the Falcon platform) |
| What it is | CrowdStrike's agentic AI security analyst (Charlotte AI) — a multi-agent system for triage, investigation, and response — paired with Falcon Next-Gen SIEM, the Falcon platform's index-free, cloud-native SIEM that unifies CrowdStrike and third-party security data. |
| Autonomy | Agentic with bounded response — vendor describes configurable autonomy per workflow (human-in-the-loop approval, governed semi-automated, or fully autonomous for approved workflows); Security Boulevard assesses baseline Charlotte AI at roughly AL2–AL3, credit-metered rather than unconstrained. |
| Open source | No |
| Deployment | Cloud SaaS on the CrowdStrike Falcon platform (sensors/connectors on the customer side); no self-hosted option found in public materials. |
| Pricing | Not publicly listed for Falcon Next-Gen SIEM (quote-based); Charlotte AI is included at no cost for qualifying Falcon customers with 50 AI credits renewing monthly, and Charlotte Agentic SOAR is priced via a published credit-based model. |
| Best fit | Organizations already standardized on CrowdStrike Falcon that want agentic triage and cross-domain investigation anchored on Falcon telemetry. |

**Key capabilities:**
- Vendor states Charlotte AI dispatches specialized agents in parallel across endpoint, identity, cloud, SaaS, and network domains with one shared memory, and that Detection Triage has been benchmarked at over 98% accuracy against decisions of the Falcon Complete MDR team (vendor-benchmarked). (CrowdStrike — Charlotte AI)
- Vendor states AgentWorks lets teams build custom agents no-code in plain language, on the model of their choice, with governance controls: role-based permissions, execution traces, audit logs, credit caps, and configurable approvals; Charlotte AI is certified under ISO/IEC 42001:2023. (CrowdStrike — Charlotte AI)
- Vendor states Charlotte Agentic SOAR unites agentic reasoning and deterministic workflows in one governed workspace, with bidirectional MCP connectivity to third-party tools and agents. (CrowdStrike — Charlotte AI; CrowdStrike — Agentic SOC Transformation)
- Vendor states Falcon Next-Gen SIEM uses index-free architecture with claimed 150x faster search at petabyte scale, that data from licensed Falcon modules flows into the SIEM without additional ingestion charges, and that it can be purchased standalone to analyze third-party data. (CrowdStrike — Next-Gen SIEM)
- Intezer's 2026 roundup categorizes Charlotte AI as "Within a Platform" — best for organizations already standardized on Falcon — with the stated caveat that "depth is tied to the Falcon ecosystem and its data." (Intezer, April 2026)

**Strengths / weaknesses:** G2 reviewers of Falcon Next-Gen SIEM praise fast event search, tight integration with Falcon endpoint modules, a unified console across detection/investigation/SOAR, and Charlotte-AI-assisted detection-rule creation. Complaints cluster on premium and hard-to-predict cost, complex licensing and ingestion considerations, an implementation learning curve, and integrations that are not always plug-and-play (G2 — Falcon Next-Gen SIEM reviews). The Swimlane-authored September roundup lists the watch-out "Depth tied to Falcon ecosystem," and Palo Alto's Cyberpedia comparison (vendor source, treated as vendor-claimed) characterizes Charlotte AI as "supervised autonomy via Agentic SOAR" with "native Falcon ecosystem; limited third-party depth" (Palo Alto Cyberpedia).

**Versus Vigil:** Overlap: agentic triage and investigation with governed, human-approvable response; both treat automation and AI reasoning as first-class. Differentiators: Charlotte AI's cited strengths — 98% triage benchmark, ISO 42001 certification, MDR-trained models — are products of the proprietary Falcon data plane, and every independent cross-check lands on the same trade: Intezer says depth is tied to the Falcon ecosystem, Security Boulevard ties the value to Falcon-standardized shops, and CrowdStrike's own no-ingestion-charge for Falcon telemetry is an economic mechanism that deepens that gravity well. Vigil is stack-agnostic by construction: Apache 2.0, 30+ MCP integrations across vendors' SIEMs/EDRs, 7,200+ open-format detection rules, Markdown-defined workflows an operator can read and version, and self-hosted/air-gapped deployment — versus a SaaS console and credit-metered AI consumption (50 monthly credits included; Agentic SOAR billed by credits tied to ingestion). Where the suite wins on cited evidence: petabyte-scale index-free search, cross-domain first-party coverage for Falcon shops, and certified AI governance; the price is Falcon centrality and quote-based commercial terms.

**Sources:**
- [Charlotte AI: Agentic Analyst for Cybersecurity — CrowdStrike](https://www.crowdstrike.com/en-us/platform/charlotte-ai/) — accessed 2026-10-09
- [Next-Gen SIEM — CrowdStrike](https://www.crowdstrike.com/en-us/platform/next-gen-siem/) — accessed 2026-10-09
- [The Best Agentic SOC for CrowdStrike in 2026 (and Where Charlotte AI Fits) — Security Boulevard](https://securityboulevard.com/2026/08/the-best-agentic-soc-for-crowdstrike-in-2026-and-where-charlotte-ai-fits/) — accessed 2026-10-09
- [Top 16 AI SOC Tools for 2026 — Intezer](https://intezer.com/blog/top-15-ai-soc-platforms-in-2026) — accessed 2026-10-09
- [Falcon Next-Gen SIEM Reviews — G2](https://www.g2.com/products/falcon-next-gen-siem/reviews) — accessed 2026-10-09
- [Charlotte Agentic SOAR Pricing — CrowdStrike](https://www.crowdstrike.com/en-us/platform/charlotte-ai/agentic-soar/pricing/) — accessed 2026-10-09

### 18. SentinelOne — Purple AI

| Field | Value |
|---|---|
| Category | Suite copilot (agentic AI security analyst inside the Singularity Platform) |
| What it is | SentinelOne's generative/agentic AI analyst for the Singularity Platform: a conversational analyst for threat hunting, alert triage, and cross-source investigation, with one-click agentic Auto Investigation (GA March 2026) that produces explainable verdicts and can trigger closed-loop remediation. |
| Autonomy | Agentic with bounded response — Security Boulevard scores Purple AI at AL3 (AI-led with human review); Palo Alto's Cyberpedia calls it "semi-autonomous with streaming analytics" with audit logging and analyst review checkpoints; SentinelOne emphasizes analyst-in-the-loop governance. |
| Open source | No |
| Deployment | Cloud SaaS accessed through the Singularity cloud console (SentinelOne states Auto Investigation requires no additional deployment); the wider SentinelOne platform protects air-gapped environments at the endpoint layer, but no public source describes Purple AI itself as deployable on-premises. |
| Pricing | Not publicly listed (sold as an add-on module on tiered platform licensing; TrustRadius notes custom quotes are common across the AI SOC category). |
| Best fit | Existing SentinelOne Singularity customers, especially endpoint-centric SOCs expanding toward agentic operations. |

**Key capabilities:**
- Vendor states Purple AI Auto Investigation (GA at RSAC 2026, March 23, 2026) lets analysts launch complete agentic investigations with one click: gathering cross-stack evidence, synthesizing threat data, constructing attack timelines in real time, delivering explainable verdicts, and triggering closed-loop remediation via Singularity Hyperautomation while maintaining analyst-in-the-loop governance. (SentinelOne press release, March 2026)
- Vendor states Purple AI is available to all Purple AI Analyst customers with no further deployment or configuration, and that Purple AI was included in over 50% of all SentinelOne licenses sold in Q4 FY26 (vendor-reported attach rate). (SentinelOne press release, March 2026)
- Security Boulevard (July 2026) ranks Purple AI #2 among agentic SOC platforms as the "ecosystem-native agent breaking out of its ecosystem," noting the 2026 Athena release extends agentic triage beyond SentinelOne endpoint telemetry to third-party SIEMs and data lakes, while calling that third-party depth "new and unproven" and Purple AI an "add-on module on tiered platform licensing." (Security Boulevard, July 2026)
- Intezer's 2026 roundup places SentinelOne (Purple AI) #12, best for "enterprises invested in the SentinelOne Singularity platform," with agentic investigation native to Singularity as the key strength and value "tied to adopting the Singularity platform." (Intezer, April 2026)
- TrustRadius lists Purple AI at 8.6/10 from 12 reviews in its AI SOC Analyst category. (TrustRadius)

**Strengths / weaknesses:** Independent roundups converge on the same profile: Security Boulevard credits deep endpoint-native investigation quality and a clean upgrade path from EDR customer to agentic SOC, and says Athena's cross-environment reach is "ahead of Falcon's and Cortex's equivalent openness," while warning that investigation quality outside SentinelOne telemetry should be tested in a POV. G2 reviewers of SentinelOne products commonly cite cost for smaller organizations, pricing opacity, a steep learning curve, false positives, and policy/exclusion management friction (G2 — SentinelOne Singularity reviews). Palo Alto's Cyberpedia comparison (vendor source, treated as vendor-claimed) positions Purple AI #2 with "vendor-agnostic via OCSF normalization" as its integration posture (Palo Alto Cyberpedia).

**Versus Vigil:** Overlap: agentic investigation with explainable verdicts, human-in-the-loop response, and threat hunting in natural language; Purple AI is the suite copilot structurally closest to Vigil's autonomy tier (AL3). Differentiators: Purple AI's investigation quality is anchored on Singularity telemetry, and both independent cross-checks frame its reach in ecosystem terms — Intezer ties its value to Singularity adoption, and Security Boulevard tests "cross-stack coverage" as the open boundary even after Athena. Vigil is vendor-agnostic at the foundation rather than as a 2026 expansion: Apache 2.0 open source, 30+ MCP integrations, 7,200+ detection rules in open formats, Markdown-defined workflows, and self-hosted/air-gapped deployment versus a cloud console add-on on tiered licensing. Where the suite wins on cited evidence: proprietary Autonomous Security Intelligence, one-click remediation wired into Singularity Hyperautomation, and a vendor-reported >50% attach rate signaling production maturity; the trade is Singularity centrality and quote-based pricing.

**Sources:**
- [SentinelOne Unveils New AI Security Offerings — SentinelOne Investor Relations (March 23, 2026)](https://investors.sentinelone.com/press-releases/news-details/2026/SentinelOne-Unveils-New-AI-Security-Offerings-to-Give-Defenders-a-Decisive-Advantage-/default.aspx) — accessed 2026-10-09
- [The 12 Best Agentic SOC Platforms in 2026 — Security Boulevard](https://securityboulevard.com/2026/07/the-12-best-agentic-soc-platforms-in-2026-architectures-autonomy-levels-and-a-full-comparison/) — accessed 2026-10-09
- [Top 16 AI SOC Tools for 2026 — Intezer](https://intezer.com/blog/top-15-ai-soc-platforms-in-2026) — accessed 2026-10-09
- [Best AI SOC Analyst Software 2026 — TrustRadius](https://www.trustradius.com/categories/ai-soc-analyst) — accessed 2026-10-09
- [SentinelOne Singularity Cloud Security Reviews — G2](https://www.g2.com/products/sentinelone-singularity-cloud-security/reviews) — accessed 2026-10-09
- [Best AI SOC Tools: Top 10 Platforms for 2026 — Palo Alto Networks Cyberpedia](https://www.paloaltonetworks.com/cyberpedia/ai-soc-tools-comparison) — accessed 2026-10-09

### 19. Microsoft — Sentinel + Security Copilot

| Field | Value |
|---|---|
| Category | Suite copilot (cloud-native SIEM + embedded generative/agentic AI assistant and agents) |
| What it is | Microsoft Sentinel, the Azure cloud-native SIEM with analytics and data lake tiers and an MCP server for AI agents, plus Microsoft Security Copilot, the generative-AI assistant and agent platform embedded across Sentinel, Defender, Entra, Intune, and Purview. |
| Autonomy | Copilot → agentic agents with scoped, permission-bounded actions — Microsoft Learn states agents range from prompt-and-response to semi-autonomous workflows with human oversight, and may perform scoped actions within configured permissions when an appropriate user or administrator approves. |
| Open source | No |
| Deployment | Azure cloud service (Azure subscription required); data in analytics or data lake tiers. No self-hosted option; Azure region selection governs data residency. |
| Pricing | Public model, quote-free: Sentinel is pay-as-you-go per GB (region-specific rates via the Azure pricing calculator) with commitment tiers from 100 GB to 50,000 GB/day (up to 52% savings vs. pay-as-you-go, per Microsoft) and a 50 GB commitment tier in public preview (sign-ups October 1, 2025 – December 31, 2026); Security Copilot is capacity-based in Security Compute Units (SCUs) — provisioned SCUs billed hourly (Microsoft's published example: $4 per provisioned SCU per hour, $6 per overage SCU), and Microsoft 365 E5/E7 customers receive 400 SCUs/month per 1,000 user licenses, capped at 10,000 SCUs/month. |
| Best fit | Microsoft-consolidated enterprises (M365 E5/E7, Defender, Entra, Azure) that want AI agents across an already-Microsoft security estate. |

**Key capabilities:**
- Vendor states Security Copilot built into Sentinel summarizes incidents, drafts KQL queries, and recommends next steps, with a claimed ~30% reduction in mean time to respond (vendor-claimed figure). (Microsoft — Sentinel SIEM product page)
- Vendor states Security Copilot agents work across Defender, Entra, Intune, and Purview at no added cost with Microsoft 365 E5, with agents activated through a phased rollout for E5/E7 customers. (Microsoft — Security Copilot pricing)
- Microsoft Learn states Sentinel exposes an MCP server that exposes platform capabilities to AI agents, billed via the underlying meters it invokes (data lake queries, graph operations), with some AI-reasoning tools consuming SCUs. (Microsoft Learn — Sentinel pricing/billing; Azure — Sentinel pricing)
- D3 Security's March 2026 roundup ranks "Microsoft Security Copilot + Sentinel Enterprise" #10, citing 12+ specialized agents and graph-based reasoning over Sentinel data across 300+ Sentinel connectors, and lists limitations: adoption lower than the installed base suggests, analyst distrust when outputs are inaccurate, hallucination risk, permission complexity, and weak fit outside Microsoft/Azure dependence. (D3 Security, March 2026)
- TrustRadius ranks Microsoft Security Copilot #1 in its AI SOC Analyst category at 8.5/10 from 50 reviews. (TrustRadius)

**Strengths / weaknesses:** Strengths across sources: the deepest possible integration with the Microsoft estate (M365, Defender, Entra, Azure), cloud scale, 300+ connectors, and — uniquely in this batch — bundled agent capacity through E5/E7 entitlements rather than pure metered AI spend (Microsoft — Security Copilot pricing; TrustRadius). Weaknesses: Security Boulevard's September roundup lists the watch-outs "Ecosystem lock; agent roster still maturing"; D3 flags hallucination risk and permission complexity; and the Sentinel billing model itself (per-GB PAYG, commitment tiers, separate data-lake meters, SCU consumption) is multi-dimensional and region-dependent, which is why Microsoft publishes a cost estimator and capacity calculator rather than a single rate card (Azure — Sentinel pricing).

**Versus Vigil:** Overlap: agentic triage and investigation over SIEM telemetry with human-governed response, and — notably — both expose MCP interfaces for agents. Differentiators: Security Copilot's value is concentrated inside the Microsoft estate, and all three independent cross-checks frame it that way ("Microsoft-consolidated enterprises" as best fit; "Ecosystem lock" as the watch-out; D3: "less compelling for organizations that do not want deep Microsoft/Azure dependence"). Vigil is the stack-agnostic counter-position: Apache 2.0 open source, 30+ MCP integrations that span third-party SIEMs and EDRs rather than one vendor's, Markdown-defined workflows, and self-hosted/air-gapped deployment versus an Azure-bound service whose data residency is a function of Azure regions. Where the suite wins on cited evidence: graph-based reasoning over hyperscale Microsoft telemetry, E5-bundled agent capacity that undercuts standalone AI-SOC pricing for Microsoft shops, and the largest connector catalog (300+); the price is Azure dependency, multi-meter cost complexity, and governance overhead D3 describes for heterogeneous stacks.

**Sources:**
- [Microsoft Security Copilot — Pricing](https://www.microsoft.com/en-us/security/pricing/microsoft-security-copilot) — accessed 2026-10-09
- [Microsoft Sentinel Pricing — Microsoft Azure](https://azure.microsoft.com/en-us/pricing/details/microsoft-sentinel/) — accessed 2026-10-09
- [Plan costs and understand Microsoft Sentinel pricing and billing — Microsoft Learn](https://learn.microsoft.com/en-us/azure/sentinel/billing) — accessed 2026-10-09
- [Microsoft Sentinel — Cloud-native SIEM](https://www.microsoft.com/en-us/security/business/siem-and-xdr/microsoft-sentinel-siem) — accessed 2026-10-09
- [The Best AI SOC Platforms 2026 — D3 Security](https://d3security.com/blog/ai-soc-platforms-2026/) — accessed 2026-10-09
- [Best AI SOC Analyst Software 2026 — TrustRadius](https://www.trustradius.com/categories/ai-soc-analyst) — accessed 2026-10-09
- [The 12 Best Agentic SOC Platforms in 2026 — Security Boulevard](https://securityboulevard.com/2026/07/the-12-best-agentic-soc-platforms-in-2026-architectures-autonomy-levels-and-a-full-comparison/) — accessed 2026-10-09

### 20. Google — Security Operations (Chronicle SIEM + SOAR + Gemini)

| Field | Value |
|---|---|
| Category | Suite copilot (cloud-native SIEM + SOAR + threat intelligence with embedded Gemini AI) |
| What it is | Google Cloud's unified security operations platform — the former Chronicle SIEM with the Siemplify-derived SOAR, Google/Mandiant threat intelligence, and Gemini embedded for natural-language search, investigation assistance, case summaries, detection creation, and playbook creation. |
| Autonomy | Copilot + deterministic SOAR automation, trending agentic — Gemini generates queries, summaries, and recommendations while SOAR playbooks execute customer-authored automation; a third-party 2026 roundup describes an AI Triage Agent performing roughly 10 investigations per hour in the Enterprise edition (third-party characterization, not a Google guarantee). |
| Open source | No |
| Deployment | Google Cloud-hosted SaaS (customer-side forwarders, collectors, and remote agents); no self-hosted option found in public materials. |
| Pricing | Not publicly listed as a rate card — packaged in Standard, Enterprise, and Enterprise Plus editions priced on ingestion, each marked "Contact sales for pricing"; one year of security telemetry retention included at no additional cost. |
| Best fit | Google Cloud-native organizations (GCP, Workspace, Mandiant customers) consolidating SIEM, SOAR, and threat intelligence on one Google-operated platform. |

**Key capabilities:**
- Vendor states Google SecOps unifies SIEM, SOAR, and threat intelligence, with Gemini for natural-language search ("Gemini generates underlying queries and presents fully mapped syntax"), AI-generated case summaries, recommended response actions, and detection/playbook creation. (Google Cloud — Security Operations)
- Vendor states the platform includes full SOAR with playbooks orchestrating 300+ tools and 700+ parsers, threat-centric case management, and automatic entity stitching. (Google Cloud — Security Operations)
- Public package page defines ingestion-based tiers with concrete rule limits: Standard supports up to 1,000 single-event and 75 multi-event rules; Enterprise 2,000/125; Enterprise Plus 3,500/200 — with curated detections, UEBA (Enterprise+), and full Google Threat Intelligence incl. Mandiant (Enterprise Plus) distributed across tiers. (Google Cloud — Security Operations pricing)
- D3 Security's March 2026 roundup ranks "Google SecOps Enterprise" #9, citing 300+ native connectors, Gemini natural-language querying, and an AI Triage Agent (~10 investigations/hour) — a third-party characterization. (D3 Security, March 2026)
- Security Boulevard's SOAR-alternatives analysis notes Siemplify's SOAR "became the response layer of Google SecOps, now wrapped with Gemini-powered investigation assistance," calling it "a coherent consolidated stack" for Google Cloud-native organizations. (Security Boulevard, July 2026)

**Strengths / weaknesses:** G2 reviews (4.4/5 across ~61 reviews at retrieval) praise centralized detection and investigation, high-quality threat detection, Gemini-assisted summaries that reduce investigation time, and scalability; recurring complaints are high cost/costly upkeep, a steep learning curve, complex implementation and configuration, limited customization in some areas, and slow support reported by some reviewers (G2 — Google Security Operations reviews). Security Boulevard's agentic-SOC longlist tracks Google SecOps among the platforms to watch rather than ranking it in the top tier of agentic architectures (Security Boulevard, July 2026).

**Versus Vigil:** Overlap: both combine investigation, case management, SOAR-style response, and AI assistance over heterogeneous telemetry. Differentiators: Google SecOps is a fully proprietary, Google-hosted platform whose AI capability is packaged behind ingestion-based editions with "Contact sales" pricing and hard rule-count ceilings (e.g., 1,000 single-event rules in Standard vs. Vigil's 7,200+ detection rules in open Sigma/ESCU/Elastic/KQL formats, self-hosted). Vigil's Apache 2.0 license, air-gapped deployment, 30+ MCP integrations, and Markdown-defined workflows contrast with a SaaS platform where detection capacity, UEBA, and Gemini features are tiered by package. Where the suite wins on cited evidence: Google/Mandiant threat intelligence embedded end-to-end (Enterprise Plus), hyperscale ingestion with 12-month retention included, 300+ orchestrated tools, and a Gartner MQ SIEM Leader 2025 placement (vendor-stated); the trade is Google Cloud centrality, package-gated capabilities, and no public rate card.

**Sources:**
- [Google Security Operations — Google Cloud](https://cloud.google.com/security/products/security-operations) — accessed 2026-10-09
- [The Best AI SOC Platforms 2026 — D3 Security](https://d3security.com/blog/ai-soc-platforms-2026/) — accessed 2026-10-09
- [Google Security Operations Reviews — G2](https://www.g2.com/products/google-security-operations/reviews) — accessed 2026-10-09
- [Best SOAR Alternatives in 2026 — Security Boulevard](https://securityboulevard.com/2026/07/best-soar-alternatives-in-2026-the-agentic-platforms-replacing-legacy-soar/) — accessed 2026-10-09
- [The 12 Best Agentic SOC Platforms in 2026 — Security Boulevard](https://securityboulevard.com/2026/07/the-12-best-agentic-soc-platforms-in-2026-architectures-autonomy-levels-and-a-full-comparison/) — accessed 2026-10-09
- [Gemini in Google SecOps overview — Google Cloud Documentation](https://docs.cloud.google.com/chronicle/docs/secops/gemini-secops) — accessed 2026-10-09

## Batch E — SIEM / XDR / Detection Platforms (profiles 21–25)

### 21. Cisco (Splunk) — Splunk Enterprise Security + Splunk SOAR

| Field | Value |
|---|---|
| Category | SIEM + SOAR (suite copilot) |
| What it is | Cisco-owned premium SIEM (Enterprise Security) paired with a playbook-driven orchestration platform (SOAR), now marketed as one unified SecOps experience. |
| Autonomy | Copilot + playbook-driven — "assisted automation with analyst oversight" per [Palo Alto Cyberpedia](https://www.paloaltonetworks.com/cyberpedia/ai-soc-tools-comparison); vendor markets an "agentic AI" framing for ES Essentials ([Vendor states](https://www.splunk.com/en_us/products/enterprise-security-essentials.html)) |
| Open source | No — paid, licensed products ([Splunkbase](https://splunkbase.splunk.com/app/263)) |
| Deployment | Both — Splunk Cloud Platform (on AWS) or on-premises Splunk Enterprise; hybrid supported ([Splunkbase](https://splunkbase.splunk.com/app/263)) |
| Pricing | Not publicly listed — Splunk publicly documents four pricing models (ingest, workload, entity, and activity-based dual-meter for Cloud) but publishes no price list; quote via sales ([Splunk pricing models](https://www.splunk.com/en_us/products/pricing/pricing-models.html)) |
| Best fit | Large enterprises with existing Splunk estates and dedicated detection-engineering / Splunk-administration staff |

**Key capabilities:**

- **Risk-Based Alerting (RBA)** correlates risk events around users/hosts and consolidates them into higher-fidelity risk notables; [Vendor states](https://www.splunk.com/en_us/products/enterprise-security-essentials.html) RBA can cut alert volume by up to 90% (vendor claim, not an independent benchmark).
- **Entity risk scoring** — explainable 0–100 weighted risk scores with supporting detection detail for investigation ([Splunk ES features](https://www.splunk.com/en_us/products/splunk-enterprise-security-features.html)).
- **AI Assistant for ES** summarizes findings, crafts queries, and suggests next steps; admins choose between Frontier or Splunk-hosted models for compliance reasons ([Splunk docs, ES 8.5](https://help.splunk.com/en/splunk-enterprise-security-8/administer/8.5/ai-assistant-in-security-and-agentic-capabilities/choose-which-models-the-ai-assistant-uses-in-splunk-enterprise-security)). Cloud-only per [ES features page](https://www.splunk.com/en_us/products/splunk-enterprise-security-features.html).
- **SOAR playbook automation** — Visual Playbook Editor plus a large app catalog; [Vendor states](https://www.splunk.com/en_us/products/splunk-enterprise-security-features.html) hundreds of integrations and thousands of actions; Intezer's SOAR guide counts **2,800+ actions** with visual editor and case management ([Intezer SOAR Platform Guide](https://intezer.com/guides/soar-security/soar-platform-guide)).
- **Detection engineering** — Detection Studio for testing/deploying/monitoring detections ([Splunk](https://www.splunk.com/en_us/products/enterprise-security-essentials.html)); Panther's comparison table describes Splunk's model as "SPL correlation rules; Detection Studio; ESCU content library" ([Panther blog](https://panther.com/blog/best-ai-soc-platforms)).

**Strengths / weaknesses:**

- *Strengths:* Broad data-source visibility, mature search/analytics, strong automation; G2 lists ES at ~4.3/5 (224 reviews) and SOAR at 4.4/5, and both appear among highlighted products in G2's enterprise AI-SOC-agents category ([G2 category](https://www.g2.com/categories/ai-soc-agents/enterprise), [G2 SOAR reviews](https://www.g2.com/products/splunk-soar-security-orchestration-automation-and-response/reviews)). Expert Insights' SOC-automation roundup describes ES as "an enterprise SIEM combining deep visibility, risk-based alerting, UEBA, and SOAR into one platform" for large SOC teams ([Expert Insights](https://expertinsights.com/security-operations/best-soc-automation-platforms)); its AI-SOC roundup tags Splunk "SIEM + AI," best for "large enterprises with deep detection engineering needs" ([Expert Insights](https://expertinsights.com/security-operations/top-ai-soc-platforms-for-business)). Palo Alto Cyberpedia ranks "Splunk AI SOC" #4 in its 2026 AI-SOC tools comparison ([Cyberpedia](https://www.paloaltonetworks.com/cyberpedia/ai-soc-tools-comparison)).
- *Weaknesses:* Cost and learning curve are the noted cons for Splunk SOAR ([Intezer SOAR guide](https://intezer.com/guides/soar-security/soar-platform-guide)); multi-meter pricing (four documented models) adds procurement complexity ([Splunk pricing models](https://www.splunk.com/en_us/products/pricing/pricing-models.html)); and despite the vendor's agentic messaging, Security Boulevard's July 2026 agentic-SOC comparison lists Splunk AI agents only under "Also tracking," not among the 12 platforms compared in depth ([Security Boulevard](https://securityboulevard.com/2026/07/the-12-best-agentic-soc-platforms-in-2026-architectures-autonomy-levels-and-a-full-comparison/)).
- *Ownership:* Cisco announced the Splunk acquisition on 2023-09-21 (~$28B, $157/share) ([Reuters](https://www.reuters.com/markets/deals/cisco-acquire-splunk-28-billion-2023-09-21/), [Splunk press release](https://www.splunk.com/en_us/newsroom/press-releases/2023/cisco-to-acquire-splunk-to-help-make-organizations-more-secure-and-resilient-in-an-ai-powered-world.html)) and closed it on 2024-03-18 ([Investopedia](https://www.investopedia.com/cisco-systems-completes-its-usd28-billion-purchase-of-splunk-8610584), [Cisco](https://www.cisco.com/site/us/en/about/corporate-development/acquisitions/splunk/index.html)).

**Versus Vigil:**

- *Overlap:* Detection engineering, case management, investigation, and automated response workflows; Splunk's ecosystem spans the same log sources Vigil covers via its 30+ MCP integrations.
- *Where Splunk wins:* Scale and maturity of the data platform, the app/integration catalog, Cisco portfolio reach, on-premises-to-cloud deployment flexibility, and a vast third-party content library; enterprise procurement and support are battle-tested.
- *Where Vigil wins:* Vigil's platform is Apache-2.0 open source (Splunk's products are closed and license-metered); Vigil ships 13 agentic AI analysts doing triage through investigation, versus Splunk's copilot-plus-playbooks model that independent roundups do not yet class as fully agentic; Vigil's 7,200+ rules span Sigma/ESCU/Elastic/KQL formats and its workflows are Markdown-defined rather than locked to SPL/proprietary playbook editors; self-hosted/air-gapped deployment is a first-class Vigil mode, while Splunk's ingest/workload licensing models create cost exposure Vigil's OSS model avoids. Practically, ES + SOAR are two products to integrate and staff; Vigil is one unified agentic SOC.

**Sources:**

- [Splunk ES features](https://www.splunk.com/en_us/products/splunk-enterprise-security-features.html) — accessed 2026-10-09
- [Splunk ES Essentials](https://www.splunk.com/en_us/products/enterprise-security-essentials.html) — accessed 2026-10-09
- [Splunk ES 8.5 AI Assistant docs](https://help.splunk.com/en/splunk-enterprise-security-8/administer/8.5/ai-assistant-in-security-and-agentic-capabilities/choose-which-models-the-ai-assistant-uses-in-splunk-enterprise-security) — accessed 2026-10-09
- [Splunkbase — Splunk ES](https://splunkbase.splunk.com/app/263) — accessed 2026-10-09
- [Splunk pricing models](https://www.splunk.com/en_us/products/pricing/pricing-models.html) — accessed 2026-10-09
- [G2 — Splunk SOAR](https://www.g2.com/products/splunk-soar-security-orchestration-automation-and-response/reviews) — accessed 2026-10-09
- [G2 — Enterprise AI SOC Agents category](https://www.g2.com/categories/ai-soc-agents/enterprise) — accessed 2026-10-09
- [Intezer — SOAR Platform Guide](https://intezer.com/guides/soar-security/soar-platform-guide) — accessed 2026-10-09
- [Expert Insights — Best 10 SOC Automation Platforms](https://expertinsights.com/security-operations/best-soc-automation-platforms) — accessed 2026-10-09
- [Expert Insights — Best 11 AI SOC Platforms](https://expertinsights.com/security-operations/top-ai-soc-platforms-for-business) — accessed 2026-10-09
- [Palo Alto Cyberpedia — AI SOC tools comparison](https://www.paloaltonetworks.com/cyberpedia/ai-soc-tools-comparison) — accessed 2026-10-09
- [Security Boulevard — 12 Best Agentic SOC Platforms in 2026](https://securityboulevard.com/2026/07/the-12-best-agentic-soc-platforms-in-2026-architectures-autonomy-levels-and-a-full-comparison/) — accessed 2026-10-09
- [Reuters — Cisco to buy Splunk](https://www.reuters.com/markets/deals/cisco-acquire-splunk-28-billion-2023-09-21/) — accessed 2026-10-09
- [Investopedia — Cisco completes $28B purchase](https://www.investopedia.com/cisco-systems-completes-its-usd28-billion-purchase-of-splunk-8610584) — accessed 2026-10-09
- [Panther — Best AI SOC Platforms](https://panther.com/blog/best-ai-soc-platforms) — accessed 2026-10-09

### 22. IBM — QRadar Suite / watsonx

| Field | Value |
|---|---|
| Category | SIEM (suite copilot) — legacy enterprise SIEM; IBM's SaaS SIEM path ended with the 2024 divestiture |
| What it is | IBM's enterprise SIEM/SecOps line: QRadar Suite (launched 2023 as a cloud-native SecOps portfolio spanning SIEM, SOAR, and EDR/XDR/MDR components) and customer-managed QRadar SIEM, with watsonx positioned as IBM's AI layer. |
| Autonomy | Copilot (analyst-assistive); no public evidence of autonomous response in the retrieved materials |
| Open source | No — proprietary commercial software ([IBM pricing/deployment page](https://www.ibm.com/products/qradar-siem/pricing)) |
| Deployment | Both — on-premises hardware/virtual appliances for QRadar SIEM; QRadar Suite software is customer-managed. IBM no longer operates a QRadar SaaS (see below) ([IBM](https://www.ibm.com/products/qradar-siem/pricing), [DarkReading](https://www.darkreading.com/cybersecurity-analytics/ciso-grapple-with-ibm-unexpected-cybersecurity-software-exit)) |
| Pricing | Not publicly listed — IBM publishes licensing metrics (EPS/FPM usage model; Managed Virtual Servers enterprise model; subscription or perpetual) but no price lists ([IBM QRadar SIEM pricing](https://www.ibm.com/products/qradar-siem/pricing)) |
| Best fit | Regulated/on-premises environments with existing QRadar estates, IBM shops, and buyers needing network-flow analytics |

**Key capabilities:**

- **QRadar SIEM** — mature enterprise threat detection combining network and user behavior analytics with threat intelligence to prioritize and contextualize alerts ([Expert Insights — SOC automation platforms](https://expertinsights.com/security-operations/best-soc-automation-platforms)).
- **Network-flow analysis (NetFlow)** detects lateral movement without requiring log data from every device — a differentiator vs newer SIEMs, per [CompariSec's QRadar review](https://www.comparisec.com/vendors/siem/ibm-security-qradar).
- **QRadar Suite** (2023) — cloud-native SecOps portfolio with shared components across EDR/XDR/MDR ([DarkReading](https://www.darkreading.com/cybersecurity-analytics/ciso-grapple-with-ibm-unexpected-cybersecurity-software-exit)).
- **watsonx AI positioning** — as part of the 2024 IBM–Palo Alto partnership, Vendor states watsonx LLM technology will be integrated into Palo Alto's Cortex XSIAM, with IBM Consulting as preferred migration partner ([IBM newsroom](https://newsroom.ibm.com/2024-05-15-Palo-Alto-Networks-and-IBM-to-Jointly-Provide-AI-powered-Security-Offerings-IBM-to-Deliver-Security-Consulting-Services-Across-Palo-Alto-Networks-Security-Platforms)).
- **Deployment/licensing models** — EPS + FPM usage licensing or Managed Virtual Servers enterprise licensing; hardware or virtual appliances; subscription or perpetual terms ([IBM QRadar SIEM pricing](https://www.ibm.com/products/qradar-siem/pricing)).

**Strengths / weaknesses:**

- *Strengths:* Strong network-flow analysis, broad protocol/device support, large enterprise footprint (CompariSec cites ~706 Gartner Peer Insights reviews) ([CompariSec](https://www.comparisec.com/vendors/siem/ibm-security-qradar)); IBM support/consulting reach.
- *Weaknesses and the transition story:* IBM agreed on 2024-05-15 to sell its **QRadar SaaS** assets to Palo Alto Networks ([IBM newsroom](https://newsroom.ibm.com/2024-05-15-Palo-Alto-Networks-and-IBM-to-Jointly-Provide-AI-powered-Security-Offerings-IBM-to-Deliver-Security-Consulting-Services-Across-Palo-Alto-Networks-Security-Platforms), [TechTarget](https://www.techtarget.com/cybersecurity/news/366585436/IBM-sells-QRadar-SaaS-assets-to-Palo-Alto-Networks)); the deal closed 2024-08-31 and the acquired SaaS products reached **end of sale/end of life 2025-04-14**, with customers directed to migrate to Cortex XSIAM ([Palo Alto Cyberpedia](https://www.paloaltonetworks.com/cyberpedia/ibm-qradar-acquired-by-palo-alto-networks), [IBM](https://www.ibm.com/new/announcements/palo-alto-networks-ibm-qradar-saas)). On-premises QRadar SKUs are unaffected ([Palo Alto Cyberpedia](https://www.paloaltonetworks.com/cyberpedia/ibm-qradar-acquired-by-palo-alto-networks)). Forrester framed the exit as "IBM Surrenders SIEM" ([Forrester blog](https://www.forrester.com/blogs/ibm-surrenders-siem-while-panw-tries-to-gain-ground-on-tech-titans/)), and DarkReading reported CISOs grappling with the unexpected software exit ([DarkReading](https://www.darkreading.com/cybersecurity-analytics/ciso-grapple-with-ibm-unexpected-cybersecurity-software-exit)). Independent commentary also flags operational complexity and EPS-based pricing complexity ([CompariSec](https://www.comparisec.com/vendors/siem/ibm-security-qradar)). A current, independently verified G2 rating was not established this session — **Unverified**.

**Versus Vigil:**

- *Overlap:* Deployment sovereignty (on-premises/customer-managed options), SIEM-class detection and investigation, case workflows.
- *Where IBM wins:* Decades of enterprise install base, network-flow analytics that reduce logging dependence, appliance-grade on-prem deployments, and IBM's consulting/support footprint.
- *Where Vigil wins:* Agentic depth (13 autonomous agents vs copilot assistance), Apache-2.0 openness vs proprietary appliances, modern detection engineering (7,200+ rules across open formats vs proprietary content), MCP-based integration surface, and — critically — roadmap stability: QRadar SaaS buyers were migrated to a competitor's platform (Cortex XSIAM), while Vigil's OSS model means the customer owns the deployment with no vendor-controlled end-of-life path. EPS/FPM metering also contrasts with Vigil's license-free self-hosting.

**Sources:**

- [IBM newsroom — Palo Alto/IBM announcement](https://newsroom.ibm.com/2024-05-15-Palo-Alto-Networks-and-IBM-to-Jointly-Provide-AI-powered-Security-Offerings-IBM-to-Deliver-Security-Consulting-Services-Across-Palo-Alto-Networks-Security-Platforms) — accessed 2026-10-09
- [IBM — QRadar SaaS acquisition completion](https://www.ibm.com/new/announcements/palo-alto-networks-ibm-qradar-saas) — accessed 2026-10-09
- [IBM — QRadar SIEM pricing/deployment](https://www.ibm.com/products/qradar-siem/pricing) — accessed 2026-10-09
- [Palo Alto Cyberpedia — QRadar acquired](https://www.paloaltonetworks.com/cyberpedia/ibm-qradar-acquired-by-palo-alto-networks) — accessed 2026-10-09
- [TechTarget — IBM sells QRadar SaaS](https://www.techtarget.com/cybersecurity/news/366585436/IBM-sells-QRadar-SaaS-assets-to-Palo-Alto-Networks) — accessed 2026-10-09
- [Forrester — IBM Surrenders SIEM](https://www.forrester.com/blogs/ibm-surrenders-siem-while-panw-tries-to-gain-ground-on-tech-titans/) — accessed 2026-10-09
- [DarkReading — CISOs grapple with IBM exit](https://www.darkreading.com/cybersecurity-analytics/ciso-grapple-with-ibm-unexpected-cybersecurity-software-exit) — accessed 2026-10-09
- [Expert Insights — SOC automation platforms](https://expertinsights.com/security-operations/best-soc-automation-platforms) — accessed 2026-10-09
- [CompariSec — QRadar review](https://www.comparisec.com/vendors/siem/ibm-security-qradar) — accessed 2026-10-09

### 23. Stellar Cyber — Open XDR Platform

| Field | Value |
|---|---|
| Category | Open XDR (AI-native SecOps platform) |
| What it is | A vendor-agnostic security-operations platform unifying NG-SIEM, NDR, UEBA, ITDR, and XDR correlation in one console, aimed at lean teams and MSSPs. |
| Autonomy | Copilot by default; agentic-with-bounded-response via the paid **Autonomous SOC Add-on** (automated investigations, AI-driven alert verdicts) ([Stellar Cyber docs](https://docs.stellarcyber.ai/prod-docs/6.4.xs/Common/Stellar-Description.htm)) |
| Open source | No — "Open" refers to vendor-agnostic integrations, not source availability ([Stellar Cyber](https://stellarcyber.ai/learn/xdr-solutions/)) |
| Deployment | Both claimed — Vendor states the platform is "purpose-built for on-premises and cloud," with multi-tenant deployments for MSSPs and on-prem/cloud sensors ([Stellar Cyber pricing page](https://stellarcyber.ai/pricing/), [docs](https://docs.stellarcyber.ai/prod-docs/6.4.xs/Common/Stellar-Description.htm)); a fully customer-managed on-prem install of the entire platform is not clearly established in public docs — confirm in procurement |
| Pricing | Not publicly listed — Security Boulevard's March 2026 guide (secondary reporting) describes a single-license model tied to organizational scale; no public price list ([Security Boulevard](https://securityboulevard.com/2026/03/the-best-ai-soc-platforms-2026-comprehensive-comparison-guide/)) |
| Best fit | Mid-market security teams and MSSPs/MDRs consolidating SIEM/NDR/XDR without rip-and-replace |

**Key capabilities:**

- **Unified platform** — NG-SIEM, NDR, UEBA, ITDR, and Open XDR in one AI-native ISOC without rip-and-replace ([Vendor states — BlackHat 2025 release](https://stellarcyber.ai/stellar-cyber-improves-soc-operations-with-human-augmented-autonomous-cybersecurity-blackhat-2025/)).
- **AI-assisted investigation** — natural-language search over telemetry, AI-generated case summaries, and recommended investigation steps ([Stellar Cyber docs](https://docs.stellarcyber.ai/prod-docs/6.4.xs/Common/Stellar-Description.htm)).
- **Autonomous SOC Add-on** — automated alert investigations across cloud/endpoint/identity/network telemetry, AI-driven verdicts, verdict-aware case summaries, and user-reported phishing analysis ([Stellar Cyber docs](https://docs.stellarcyber.ai/prod-docs/6.4.xs/Common/Stellar-Description.htm)).
- **MSSP multi-tenancy** — multi-tier/multi-tenant deployment highlighted for MSSPs and distributed organizations ([Intezer](https://intezer.com/guides/ai-soc/mid-sized-enterprises)).
- **Integration breadth** — Security Boulevard reports 150+ integrations (secondary reporting) ([Security Boulevard](https://securityboulevard.com/2026/03/the-best-ai-soc-platforms-2026-comprehensive-comparison-guide/)).

**Strengths / weaknesses:**

- *Strengths:* Consolidation value and MSSP fit are the consistent themes: Expert Insights calls it "a unified security operations platform that merges SIEM, NDR, and XDR into a single environment, built specifically for lean security teams and MSSPs" ([Expert Insights](https://expertinsights.com/security-operations/top-ai-soc-platforms-for-business)); UnderDefense ranks Stellar Cyber Open XDR #4 in its 2026 enterprise AI-SOC list ([UnderDefense](https://underdefense.com/blog/ai-soc-for-enterprise/)); the vendor's site quotes a 4.8 Gartner Peer Insights score and ESG/analyst endorsements ([Vendor states — stellarcyber.ai](https://stellarcyber.ai/pricing/)); Vendor states 15,000+ customers and partners ([Vendor states — stellarcyber.ai](https://stellarcyber.ai/pricing/)).
- *Weaknesses:* No public pricing; Security Boulevard's coverage notes its claimed analyst-time savings are vendor-reported, not independently validated ([Security Boulevard](https://securityboulevard.com/2026/03/the-best-ai-soc-platforms-2026-comprehensive-comparison-guide/)); the vendor's own "agentic" self-ranking content ([stellarcyber.ai](https://stellarcyber.ai/learn/top-10-agentic-soc-platforms/)) is promotional; independent efficacy testing of the autonomous features was not found this session. A third-party battlecard reports onboarding effort and mid-market (rather than enterprise) brand recognition as limitations ([primaryguard.com](https://primaryguard.com/battlecards/autonomous-soc/stellar-vs-sentinel)) — secondary source, treat as indicative.

**Versus Vigil:**

- *Overlap:* Both pitch one-platform consolidation of detection, investigation, and response with automation doing the heavy lifting; both serve teams without large SOC headcount.
- *Where Stellar Cyber wins:* Native network detection (NDR sensors), UEBA/ITDR modules, multi-tenancy purpose-built for MSSPs, and a broader turnkey integration catalog; the Autonomous SOC Add-on offers a commercial path to hands-off triage.
- *Where Vigil wins:* The naming distinction matters — Stellar Cyber's "Open" is an integration philosophy, while Vigil is genuinely open source (Apache 2.0) with self-hosted/air-gapped deployment, Markdown-defined workflows customers can read and modify, and 7,200+ open-format detection rules. Vigil's 13 specialized agents are a broader agentic analyst bench than a paid add-on tier, and its StackStorm heritage gives it OSS automation depth that a proprietary XDR console cannot match.

**Sources:**

- [Stellar Cyber product docs (6.4)](https://docs.stellarcyber.ai/prod-docs/6.4.xs/Common/Stellar-Description.htm) — accessed 2026-10-09
- [Stellar Cyber BlackHat 2025 release](https://stellarcyber.ai/stellar-cyber-improves-soc-operations-with-human-augmented-autonomous-cybersecurity-blackhat-2025/) — accessed 2026-10-09
- [Stellar Cyber site/pricing](https://stellarcyber.ai/pricing/) — accessed 2026-10-09
- [Stellar Cyber — XDR solutions](https://stellarcyber.ai/learn/xdr-solutions/) — accessed 2026-10-09
- [Expert Insights — Best 11 AI SOC Platforms](https://expertinsights.com/security-operations/top-ai-soc-platforms-for-business) — accessed 2026-10-09
- [Intezer — AI SOC for mid-sized enterprises](https://intezer.com/guides/ai-soc/mid-sized-enterprises) — accessed 2026-10-09
- [UnderDefense — 9 Best AI SOC for Enterprise](https://underdefense.com/blog/ai-soc-for-enterprise/) — accessed 2026-10-09
- [Security Boulevard — Best AI SOC Platforms 2026](https://securityboulevard.com/2026/03/the-best-ai-soc-platforms-2026-comprehensive-comparison-guide/) — accessed 2026-10-09
- [primaryguard battlecard](https://primaryguard.com/battlecards/autonomous-soc/stellar-vs-sentinel) — accessed 2026-10-09

### 24. Hunters — SOC Platform (Next-Gen SIEM)

| Field | Value |
|---|---|
| Category | Next-Gen SIEM / SOC platform |
| What it is | A SaaS "AI-Driven Next-Gen SIEM" that automates detection, enrichment, correlation, prioritization, triage, and investigation for small SecOps teams, with detection engineering built in and managed by Hunters' Team Axon. |
| Autonomy | High automation of triage/investigation; agentic capabilities are vendor-announced — Hunters described moving from Copilot AI toward an "Agentic AI vision" ([CB Insights](https://www.cbinsights.com/company/huntersai)); fully autonomous response is not established in public materials |
| Open source | No — commercial platform; no source repository or OSS license identified ([G2](https://www.g2.com/products/hunters-soc-platform/reviews)) |
| Deployment | SaaS — cloud data-lake architecture; no self-hosted option found in public materials ([hunters.security](https://www.hunters.security/)) |
| Pricing | Not publicly listed — quote-based; no public price table found this session |
| Best fit | Lean/small SecOps teams that want vendor-managed detection engineering and data-lake economics without staffing a detection team |

**Key capabilities:**

- **Automated TDIR** — detection, enrichment, correlation, prioritization, triage, and investigation automated end-to-end ([Vendor states — hunters.security](https://www.hunters.security/), [Hunters LinkedIn](https://www.linkedin.com/company/hunters-ai)).
- **Team Axon** — Hunters' security research group builds, manages, and tunes detections; "no detection engineering necessary" ([Vendor states — hunters.security](https://www.hunters.security/), [Cyber Company Profiles](https://cybercompanyprofiles.com/companies/hunters)).
- **Data-lake architecture** — raw feeds land in a shared Snowflake database customers can build their own models on (per a Pennymac CISO quote on [hunters.security](https://www.hunters.security/)); Snowflake Ventures invested in Hunters and Hunters joined Snowflake Partner Connect ([Blumberg Capital](https://blumbergcapital.com/news-insights/hunters-receives-growth-funding-from-snowflake-ventures/)).
- **Fast deployment** — Vendor states out-of-the-box deployment "in days, with no ongoing management" ([hunters.security](https://www.hunters.security/)).
- **Analyst recognition (vendor-cited)** — GigaOm Radar for SIEM 2025, GigaOm Radar for Autonomous SOC 2024, Gartner Magic Quadrant for SIEM 2024, Forrester Security Analytics Platform Landscape Q4 2024 ([Vendor states — hunters.security](https://www.hunters.security/)).

**Strengths / weaknesses:**

- *Strengths:* Reliable detections and correlation that reduce noise, per the available G2 review ([G2](https://www.g2.com/products/hunters-soc-platform/reviews?qs=pros-and-cons)); Expert Insights highlights automatic incident identification/response, built-in detection engineering, and predictable cost ([Expert Insights](https://expertinsights.com/reviews/huntersai)); strong strategic backers — ~$118M raised including a $68M Series C (Jan 2022) from investors including Snowflake Ventures, Microsoft M12, Cisco Investments, Databricks, Okta, and YL Ventures ([CB Insights](https://www.cbinsights.com/company/huntersai), [Cyber Company Profiles](https://cybercompanyprofiles.com/companies/hunters)).
- *Weaknesses:* Very thin public review base — G2 shows 4.0/5 from a single review ([G2](https://www.g2.com/products/hunters-soc-platform/reviews)); Gartner Peer Insights ~4.4/5 across 41 reviews per aggregator [rfp.wiki](https://www.rfp.wiki/it-security/security-information-and-event-management/hunters) (secondary source); a G2 reviewer criticized incomplete API/endpoint coverage for customization ([G2](https://www.g2.com/products/hunters-soc-platform/reviews?qs=pros-and-cons)); no public pricing; agentic/autonomous claims remain vendor positioning without independent validation ([CB Insights](https://www.cbinsights.com/company/huntersai)).

**Versus Vigil:**

- *Overlap:* Both attack the same pain — alert triage load on understaffed teams — with automation over correlated, lake-stored telemetry.
- *Where Hunters wins:* Managed detection engineering (Team Axon) genuinely removes the detection-ops burden; Snowflake-anchored data-lake economics; days-not-months deployment; hyperscaler/enterprise investor ecosystem.
- *Where Vigil wins:* The models are opposite poles on ownership. Hunters is a closed, vendor-operated SaaS where detection logic is managed *for* you; Vigil is Apache-2.0 with 7,200+ rules across open formats (Sigma/ESCU/Elastic/KQL) that the customer owns, edits, and extends, Markdown workflows, self-hosted/air-gapped modes, and 30+ MCP integrations. For teams that want detection control, sovereignty, or air-gap compliance, Vigil is the fit; for teams that want detection outsourced, Hunters is the fit.

**Sources:**

- [hunters.security](https://www.hunters.security/) — accessed 2026-10-09
- [G2 — Hunters SOC Platform](https://www.g2.com/products/hunters-soc-platform/reviews) — accessed 2026-10-09
- [G2 — pros/cons](https://www.g2.com/products/hunters-soc-platform/reviews?qs=pros-and-cons) — accessed 2026-10-09
- [Expert Insights — Hunters review](https://expertinsights.com/reviews/huntersai) — accessed 2026-10-09
- [CB Insights — Hunters profile](https://www.cbinsights.com/company/huntersai) — accessed 2026-10-09
- [Blumberg Capital — Snowflake Ventures investment](https://blumbergcapital.com/news-insights/hunters-receives-growth-funding-from-snowflake-ventures/) — accessed 2026-10-09
- [Cyber Company Profiles — Hunters](https://cybercompanyprofiles.com/companies/hunters) — accessed 2026-10-09
- [rfp.wiki — Hunters](https://www.rfp.wiki/it-security/security-information-and-event-management/hunters) — accessed 2026-10-09
- [Hunters LinkedIn](https://www.linkedin.com/company/hunters-ai) — accessed 2026-10-09

### 25. Panther — AI SOC Platform (Cloud SIEM)

| Field | Value |
|---|---|
| Category | Cloud SIEM (detection platform / AI SOC) |
| What it is | A cloud-native SIEM built on a customer-owned security data lake (Snowflake or Databricks), with detection-as-code in Python/SQL/YAML and an AI agent layer for triage and investigation. |
| Autonomy | Agentic investigation with bounded actions — Vendor states Panther AI investigates, delivers definitive risk classifications, closes benign alerts, and proposes detection improvements "with audit trails… configurable thresholds. Humans stay in control" ([panther.com](https://panther.com/pricing/)) |
| Open source | **Partial** — the platform is proprietary, but Panther open-sources its detection content and tooling: the `panther-analysis` detections repo is Apache-2.0 ([GitHub](https://github.com/panther-labs/panther-analysis)), the Panther Analysis Tool (PAT) CLI is open source ([Panther docs](https://docs.panther.com/panther-developer-workflows/overview)), and its MCP server is open source ([Panther docs](https://docs.panther.com/ai/mcp/mcp-server)) |
| Deployment | SaaS (Panther Cloud) or bring-your-own AWS + data lake ("Deploy Panther in your own cloud environment with your existing AWS and Databricks or Snowflake accounts") ([panther.com](https://panther.com/pricing/)); no self-hosted/air-gapped edition found in public materials |
| Pricing | Not publicly listed — vendor describes subscription/usage-based plans; the pricing page presents Panther Cloud vs BYO-data-lake options without public prices ([panther.com](https://panther.com/pricing/), [Panther blog](https://panther.com/blog/ai-tools-security-alert-triage)) |
| Best fit | Engineering-led SOCs — teams with GitHub/CI-CD practices, AWS-heavy estates, and detection engineers who want rules in code |

**Key capabilities:**

- **Detection-as-code** — detections written in Python (rules), SQL (scheduled queries), and YAML, version-controlled in Git with peer review, unit tests, historical replay, and CI/CD deployment; no proprietary query language ([Panther detection engine](https://panther.com/product/detection-engine), [Panther developer workflows](https://docs.panther.com/panther-developer-workflows/overview)).
- **Open-source detection packs** — `panther-labs/panther-analysis`: Apache-2.0 licensed, Python-based rules/policies/scheduled rules, 458 stars, 130 contributors, actively released (v3.112.0, 2026-07-07) ([GitHub — panther-analysis](https://github.com/panther-labs/panther-analysis)).
- **Open-source MCP server** — natural-language interaction with Panther alerts, detections, schemas, and data from MCP clients; Panther states it released the MCP server in collaboration with Block's security team for AI-native detection engineering ([Panther docs](https://docs.panther.com/ai/mcp/mcp-server), [Panther blog](https://panther.com/blog/mcp-tools)).
- **Panther AI / AI SOC agent** — AI Detection Builder turns natural-language threat descriptions into reviewable detection code; AI-assisted triage and investigation with enrichment from GitHub, PagerDuty, Atlassian, and Notion via MCP ([Panther blog](https://panther.com/blog/ai-detection-engineering), [AI SOC agent](https://panther.com/product/ai-soc-agent)).
- **Customer-owned data lake** — security data lives in the customer's Snowflake or Databricks instance; storage/compute separation for cost control ([Panther blog](https://panther.com/blog/best-siem-tools), [panther.com](https://panther.com/pricing/)).

**Strengths / weaknesses:**

- *Strengths:* Roundup recognition for its detection-as-code model — UnderDefense names Panther among the "9 best AI SOC tools with detection-as-code and Python/CI-CD" for 2026, calling it "a cloud-scale detection platform" ([UnderDefense](https://underdefense.com/blog/best-ai-soc-tools-with-detection-as-code-and-python-ci-cd-for-detection-rules/)); Panther is a highlighted product in G2's enterprise AI-SOC-agents category ([G2](https://www.g2.com/categories/ai-soc-agents/enterprise)); a June 2026 G2 review praises fast AI Auto Triage, SQL/Snowflake querying, and price-to-capability ([G2 review](https://www.g2.com/products/panther/reviews/panther-review-12919421)). Vendor states ~70–90% reductions in tuning time, false positives, alert volume, and investigation time ([Vendor states — panther.com](https://panther.com/pricing/)); Vendor states Panther joined Databricks (July 2026 site banner) ([panther.com](https://panther.com/pricing/)).
- *Weaknesses:* The same G2 review reports limited plug-and-play integrations (some sources require S3 delivery plus in-Panther normalization), an operational maintenance burden if detections aren't kept up, and customization drift against the upstream managed-rule repo ([G2 review](https://www.g2.com/products/panther/reviews/panther-review-12919421)); Python skills are needed for advanced rules (mitigated by Simple/AI Detection Builders) ([Panther](https://panther.com/blog/threat-detection)); no public pricing; no air-gapped deployment.

**Versus Vigil:**

- *Overlap and the key affinity:* Panther is the **closest open-adjacent philosophy to Vigil's detection engineering** in this batch. Both treat detection content as code and text: Panther's detections are Python/SQL/YAML in Git with CI/CD and an Apache-2.0 community repo; Vigil's 7,200+ rules ship in open formats (Sigma/ESCU/Elastic/KQL) and its workflows are Markdown-defined. Both expose MCP surfaces for AI agents (Panther's MCP server is open source; Vigil integrates 30+ tools over MCP), both reject proprietary query-language lock-in, and both keep humans in the loop by design. Both also push data ownership: customer-owned Snowflake/Databricks on Panther's side, self-hosted/air-gapped deployment on Vigil's.
- *Where Panther wins:* Data-lake scale and economics (petabyte-scale on customer warehouses), mature Python rule tooling (testing, replay, PAT), and a deep engineering-grade workflow for detection teams; its SIEM data layer is more industrialized than Vigil's.
- *Where Vigil wins:* Platform openness — Vigil's entire platform is Apache-2.0 vs Panther's open content atop a proprietary platform; agentic breadth — 13 specialized SOC agents (triage through forensics) with case management and human-on-the-loop response, vs Panther's AI layer over a detection/data platform; deployment sovereignty — true self-hosted/air-gapped operation vs SaaS/BYOC; and zero licensing meters vs subscription pricing. The two are as much complements as competitors: a Panther shop standardizing on Python detections is a natural Vigil audience, and detection content flows conceptually between the two ecosystems.

**Sources:**

- [GitHub — panther-labs/panther-analysis](https://github.com/panther-labs/panther-analysis) — accessed 2026-10-09
- [Panther — detection engine](https://panther.com/product/detection-engine) — accessed 2026-10-09
- [Panther docs — developer workflows](https://docs.panther.com/panther-developer-workflows/overview) — accessed 2026-10-09
- [Panther docs — MCP server](https://docs.panther.com/ai/mcp/mcp-server) — accessed 2026-10-09
- [Panther — AI SOC agent](https://panther.com/product/ai-soc-agent) — accessed 2026-10-09
- [panther.com/pricing (platform & hosting)](https://panther.com/pricing/) — accessed 2026-10-09
- [Panther blog — best SIEM tools](https://panther.com/blog/best-siem-tools) — accessed 2026-10-09
- [Panther blog — MCP tools](https://panther.com/blog/mcp-tools) — accessed 2026-10-09
- [Panther blog — AI detection engineering](https://panther.com/blog/ai-detection-engineering) — accessed 2026-10-09
- [UnderDefense — detection-as-code AI SOC tools](https://underdefense.com/blog/best-ai-soc-tools-with-detection-as-code-and-python-ci-cd-for-detection-rules/) — accessed 2026-10-09
- [G2 — Panther review](https://www.g2.com/products/panther/reviews/panther-review-12919421) — accessed 2026-10-09
- [G2 — Enterprise AI SOC Agents category](https://www.g2.com/categories/ai-soc-agents/enterprise) — accessed 2026-10-09

## Sources

Consolidated from the source lists of all 25 profiles, deduplicated by URL within each batch. Every entry was accessed 2026-10-09; the profile source lists above carry the per-claim attributions.

### Batch A sources

- [Dropzone AI — AI SOC Analyst product page](https://www.dropzone.ai/ai-soc-analyst) — accessed 2026-10-09 *(first cited in profile 1)*
- [Dropzone AI — How to Customize Your AI SOC Analyst (2026-05-07)](https://www.dropzone.ai/blog/blog-customize-ai-soc-analyst) — accessed 2026-10-09 *(first cited in profile 1)*
- [D3 Security — The 12 Best Agentic SOC Platforms in 2026 (2026-07-27, syndicated to Security Boulevard)](https://securityboulevard.com/2026/07/the-12-best-agentic-soc-platforms-in-2026-architectures-autonomy-levels-and-a-full-comparison/) — accessed 2026-10-09 *(first cited in profile 1)*
- [Expert Insights — Best 11 AI SOC Platforms for Business (updated 2026-10-08)](https://expertinsights.com/security-operations/top-ai-soc-platforms-for-business) — accessed 2026-10-09 *(first cited in profile 1)*
- [tech-insider.org — Prophet vs Dropzone vs Radiant Security: AI SOC 2026 (2026-09-13)](https://tech-insider.org/prophet-security-vs-dropzone-ai-vs-radiant-security-2026/) — accessed 2026-10-09 *(first cited in profile 1)*
- [Gartner Peer Insights — Dropzone AI reviews](https://www.gartner.com/reviews/vendor/dropzone-ai) — accessed 2026-10-09 *(first cited in profile 1)*
- [Prophet Security — homepage / agentic AI SOC platform](https://www.prophetsecurity.ai/) — accessed 2026-10-09 *(first cited in profile 2)*
- [Prophet Security — FAQ (integrations, autonomy description)](https://www.prophetsecurity.ai/prophet-security-faq) — accessed 2026-10-09 *(first cited in profile 2)*
- [Prophet Security — What is Agentic SOC? (2026-10-07)](https://www.prophetsecurity.ai/blog/what-is-agentic-soc) — accessed 2026-10-09 *(first cited in profile 2)*
- [Intezer — AI SOC product page](https://intezer.com/product/ai-soc) — accessed 2026-10-09 *(first cited in profile 3)*
- [Intezer — Forensic AI SOC pricing page](https://intezer.com/product/pricing) — accessed 2026-10-09 *(first cited in profile 3)*
- [Intezer — Top 16 AI SOC Tools for 2026 (2026-04-06; vendor-authored roundup)](https://intezer.com/blog/top-15-ai-soc-platforms-in-2026) — accessed 2026-10-09 *(first cited in profile 3)*
- [UnderDefense — 8/10 Best Agentic AI SOC Platforms for 2026 (updated 2026-10-09)](https://underdefense.com/blog/agentic-soc-platforms/) — accessed 2026-10-09 *(first cited in profile 3)*
- [UnderDefense — 9 Best AI SOC for Enterprise (2026-03-13)](https://underdefense.com/blog/ai-soc-for-enterprise/) — accessed 2026-10-09 *(first cited in profile 3)*
- [Microsoft Azure Marketplace — Intezer Autonomous SOC listing](https://marketplace.microsoft.com/en-us/product/saas/intezerlabsinc.autonomous-soc-platform2?tab=overview) — accessed 2026-10-09 *(first cited in profile 3)*
- [TrustRadius — Best AI SOC Analyst Software 2026 category (Intezer listing)](https://www.trustradius.com/categories/ai-soc-analyst) — accessed 2026-10-09 *(first cited in profile 3)*
- [Qevlar AI — AI SOC platform page](https://www.qevlar.com/ai-soc) — accessed 2026-10-09 *(first cited in profile 4)*
- [Qevlar AI — $30M funding press release (March 2026)](https://www.qevlar.com/press/qevlar-ai-raises-30m) — accessed 2026-10-09 *(first cited in profile 4)*
- [Qevlar AI — $14M funding announcement (2025)](https://www.qevlar.com/post/qevlar-ai-raises-14m-to-supercharge-security-operations-centres-with-agentic-ai) — accessed 2026-10-09 *(first cited in profile 4)*
- [Atos — press release on Qevlar-powered virtual SOC analyst (2025-10-07)](https://atos.net/en/2025/press-release_2025_10_07/atos-further-augments-the-ai-tooling-of-its-cybersecurity-teams-with-virtual-soc-analyst-powered-by-qevlar-ai) — accessed 2026-10-09 *(first cited in profile 4)*
- [Cyber Vendor Guide — Qevlar AI profile](https://www.cybervendorguide.com/tools/qevlar-ai) — accessed 2026-10-09 *(first cited in profile 4)*
- [ReliaQuest — GreyMatter integrations / agentic AI platform page (updated 2026-10-08)](https://reliaquest.com/integrations/) — accessed 2026-10-09 *(first cited in profile 5)*
- [G2 — ReliaQuest GreyMatter reviews and product description](https://www.g2.com/products/reliaquest-greymatter/reviews) — accessed 2026-10-09 *(first cited in profile 5)*
- [Panther — 10 Best AI SOC Platforms: Features & Use Cases (2026-06-29, GreyMatter row)](https://panther.com/blog/best-ai-soc-platforms) — accessed 2026-10-09 *(first cited in profile 5)*
- [AWS Marketplace — ReliaQuest GreyMatter listing and reviews](https://aws.amazon.com/marketplace/reviews/reviews-list/prodview-bk276y2eevzd2) — accessed 2026-10-09 *(first cited in profile 5)*
- [LeadIQ — ReliaQuest company overview (2026-08-25)](https://leadiq.com/c/reliaquest/5a1d86fe2400002400612066) — accessed 2026-10-09 *(first cited in profile 5)*

### Batch B sources

- [UnderDefense, Managed Detection and Response (MDR) Services page (vendor)](https://underdefense.com/services/managed-detection-and-response/) — accessed 2026-10-09 *(first cited in profile 10)*
- [UnderDefense, "AI SOC Guide: Architecture, Capabilities, Pricing, and Migration" (vendor blog)](https://underdefense.com/blog/ai-soc/) — accessed 2026-10-09 *(first cited in profile 10)*
- [UnderDefense, "Best AI SOC for Mid-Market: 8 Providers Scored, Priced" (vendor blog; $11–$15/endpoint/month range)](https://underdefense.com/blog/ai-soc-for-mid-market/) — accessed 2026-10-09 *(first cited in profile 10)*
- [Agentic Index, UnderDefense vendor profile](https://agenticindex.io/vendors/underdefense) — accessed 2026-10-09 *(first cited in profile 10)*
- [G2, UnderDefense MAXI reviews](https://www.g2.com/products/underdefense-maxi/reviews) — accessed 2026-10-09 *(first cited in profile 10)*
- [UnderDefense press release, "UnderDefense Launches Unified MAXI Workspace…" (Aug 5, 2026)](https://underdefense.com/company-news/underdefense-launches-unified-maxi-workspace-one-platform-for-agentic-ai-soc-compliance-ai-and-ciso-intelligence-at-enterprise-scale/) — accessed 2026-10-09 *(first cited in profile 10)*
- [Exaforce — Agentic SOC and MDR (exaforce.com)](https://www.exaforce.com) — accessed 2026-10-09 *(first cited in profile 6)*
- [TrustRadius, Best AI SOC Analyst Software 2026 (category listing)](https://www.trustradius.com/categories/ai-soc-analyst) — accessed 2026-10-09 *(first cited in profile 6)*
- [Intezer, "Top 16 AI SOC Tools for 2026: SOC Automation Compared"](https://intezer.com/blog/top-15-ai-soc-platforms-in-2026) — accessed 2026-10-09 *(first cited in profile 6)*
- [G2, Exaforce Reviews](https://www.g2.com/products/exaforce/reviews) — accessed 2026-10-09 *(first cited in profile 6)*
- [Latio vendor profile, Exaforce Reviews 2026](https://www.latio.com/vendor/exaforce) — accessed 2026-10-09 *(first cited in profile 6)*
- [Beri (The Daily Brief), Exaforce overview](https://www.beri.net/tools/exaforce) — accessed 2026-10-09 *(first cited in profile 6)*
- [TechCrunch, "Exaforce raises $125M Series B…" (May 12, 2026)](https://techcrunch.com/2026/05/12/exaforce-raises-125m-series-b-to-build-ai-for-catching-and-stopping-cyberattacks-as-they-happen/) — accessed 2026-10-09 *(first cited in profile 6)*
- [Business Wire, "Exaforce Raises $125M Series B to Combat AI-Powered Attacks…" (May 12, 2026)](https://www.businesswire.com/news/home/20260512993333/en/Exaforce-Raises-%24125M-Series-B-to-Combat-AI-Powered-Attacks-with-Real-Time-Security-Reasoning) — accessed 2026-10-09 *(first cited in profile 6)*
- [Security Boulevard, "The 12 Best Agentic SOC Platforms in 2026"](https://securityboulevard.com/2026/07/the-12-best-agentic-soc-platforms-in-2026-architectures-autonomy-levels-and-a-full-comparison/) — accessed 2026-10-09 *(first cited in profile 6)*
- [7AI — Company page (7ai.com)](https://7ai.com/company) — accessed 2026-10-09 *(first cited in profile 7)*
- [AWS Marketplace, 7AI Agentic SOC Platform listing](https://aws.amazon.com/marketplace/pp/prodview-2bhzh7e2dlc7k) — accessed 2026-10-09 *(first cited in profile 7)*
- [7AI blog, "Top AI SOC Platforms in 2026" comparison (vendor-authored)](https://blog.7ai.com/top-ai-soc-platforms-in-2026) — accessed 2026-10-09 *(first cited in profile 7)*
- [Index Ventures, "Security's Agentic Era Starts Here: Our Investment in 7AI" (Dec 2025)](https://www.indexventures.com/perspectives/securitys-agentic-era-starts-here-our-investment-in-7ai/) — accessed 2026-10-09 *(first cited in profile 7)*
- [CRN, "The 10 Hottest Cybersecurity Startups of 2026 (So Far)"](https://www.crn.com/news/security/2026/the-10-hottest-cybersecurity-startups-of-2026-so-far) — accessed 2026-10-09 *(first cited in profile 7)*
- [Simbian.ai — "Self-Improving Defense" (vendor site)](https://simbian.ai) — accessed 2026-10-09 *(first cited in profile 8)*
- [AWS Marketplace, Simbian AI SOC Agent listing](https://aws.amazon.com/marketplace/pp/prodview-77rory5w3laek) — accessed 2026-10-09 *(first cited in profile 8)*
- [Agentic Index, Simbian vendor profile](https://agenticindex.io/vendors/simbian) — accessed 2026-10-09 *(first cited in profile 8)*
- [AGENCCY, Simbian company profile](https://agenccy.ai/catalogue/simbian/) — accessed 2026-10-09 *(first cited in profile 8)*
- [G2, Simbian reviews](https://www.g2.com/products/simbian/reviews) — accessed 2026-10-09 *(first cited in profile 8)*
- [Darktrace, Cyber AI Analyst product page (vendor)](https://www.darktrace.com/cyber-ai-analyst) — accessed 2026-10-09 *(first cited in profile 9)*
- [Digital by Default, "Darktrace Review 2026: Does the AI Immune System Actually Work?"](https://digitalbydefault.ai/blog/darktrace-ai-cybersecurity-review-2026) — accessed 2026-10-09 *(first cited in profile 9)*
- [UnderDefense, "Darktrace Pricing Guide 2026: Real Costs, Hidden Fees" (third-party, competitor-published estimates)](https://underdefense.com/blog/darktrace-pricing-guide/) — accessed 2026-10-09 *(first cited in profile 9)*
- [Cybersecurity Essentials, "Darktrace vs Vectra AI vs SentinelOne Purple AI" comparison](https://www.cybersecurityessential.com/ai-security/ai-defence/darktrace-vectra-sentinelone-ai-platforms-compared/) — accessed 2026-10-09 *(first cited in profile 9)*
- [Thoma Bravo, "Thoma Bravo Completes Acquisition of Darktrace" (Oct 1, 2024)](https://www.thomabravo.com/press-releases/thoma-bravo-completes-acquisition-of-darktrace) — accessed 2026-10-09 *(first cited in profile 9)*
- [The Cyber Throne, "Biggest GoldRush: Major Security Acquisitions in 2025" (Darktrace → Cado Security, ~$150M)](https://thecyberthrone.in/2025/12/29/biggest-goldrush-major-security-acquisitions-in-2025/) — accessed 2026-10-09 *(first cited in profile 9)*
- [Thoma Bravo, "Darktrace Announces Acquisition of Mira Security" (Jul 21, 2025)](https://www.thomabravo.com/press-releases/darktrace-announces-acquisition-of-mira-security-a-leading-provider-of-network-traffic-visibility-solutions) — accessed 2026-10-09 *(first cited in profile 9)*

### Batch C sources

- [Torq — The Torq AI SOC Platform](https://torq.io/ai-soc-platform/) — accessed 2026-10-09 *(first cited in profile 11)*
- [Agentic Index — Torq Features & Pricing](https://agenticindex.io/vendors/torq) — accessed 2026-10-09 *(first cited in profile 11)*
- [SecureCoding — Tines vs Torq: story-built cases or agentic alert triage?](https://www.securecoding.com/compare/tines-vs-torq/) — accessed 2026-10-09 *(first cited in profile 11)*
- [Tech-Insider — Torq vs Tines vs Cortex XSIAM: SOAR Platform Compared (2026)](https://tech-insider.org/torq-vs-tines-vs-cortex-xsiam-2026/) — accessed 2026-10-09 *(first cited in profile 11)*
- [Security Boulevard — The Best AI SOC Platforms in 2026: An Honest Comparison](https://securityboulevard.com/2026/09/the-best-ai-soc-platforms-in-2026-an-honest-comparison/) — accessed 2026-10-09 *(first cited in profile 11)*
- [Security Boulevard — The 12 Best Agentic SOC Platforms in 2026](https://securityboulevard.com/2026/07/the-12-best-agentic-soc-platforms-in-2026-architectures-autonomy-levels-and-a-full-comparison/) — accessed 2026-10-09 *(first cited in profile 11)*
- [AWS Marketplace — Torq HyperSOC listing and reviews](https://aws.amazon.com/marketplace/pp/prodview-2c4o6nqsvkxhy) — accessed 2026-10-09 *(first cited in profile 11)*
- [Recatools — Torq Review: No-Code Security Automation](https://recatools.com/ai-directory/torq/) — accessed 2026-10-09 *(first cited in profile 11)*
- [PeerSpot — What advice do you have for others considering Torq?](https://www.peerspot.com/questions/what-advice-do-you-have-for-others-considering-torq) — accessed 2026-10-09 *(first cited in profile 11)*
- [CybersecTools — Torq HyperSOC](https://cybersectools.com/tools/torq-hypersoc) — accessed 2026-10-09 *(first cited in profile 11)*
- [strike48 — Torq competitors](https://www.strike48.com/post/torq-competitors) — accessed 2026-10-09 *(first cited in profile 11)*
- [Swimlane — Turbine, the Agentic AI Automation Platform](https://swimlane.com/swimlane-turbine/) — accessed 2026-10-09 *(first cited in profile 12)*
- [Swimlane — Enterprise Pricing and Packaging](https://swimlane.com/platform/enterprise-packaging/) — accessed 2026-10-09 *(first cited in profile 12)*
- [Swimlane — AI SOC powered by Swimlane Turbine](https://swimlane.com/product/ai-soc/) — accessed 2026-10-09 *(first cited in profile 12)*
- [Swimlane docs — Playbooks Overview](https://docs.swimlane.com/playbooks-overview) — accessed 2026-10-09 *(first cited in profile 12)*
- [Swimlane — Turbine Overview datasheet (deployment models)](https://45377644.fs1.hubspotusercontent-na1.net/hubfs/45377644/2025%20Sponsor%20Assets/Turbine%20Overview%20-%20Swimlane.pdf) — accessed 2026-10-09 *(first cited in profile 12)*
- [UnderDefense — Andesite vs. Swimlane: AI SOC Showdown for 2025](https://underdefense.com/blog/andesite-vs-swimlane-the-2025-ai-soc-dilemma/) — accessed 2026-10-09 *(first cited in profile 12)*
- [G2 — Swimlane Reviews](https://www.g2.com/products/swimlane/reviews) — accessed 2026-10-09 *(first cited in profile 12)*
- [SoftwareReviews — Swimlane reviews](https://www.softwarereviews.com/products/swimlane?c_id=218) — accessed 2026-10-09 *(first cited in profile 12)*
- [TrustRadius — Swimlane](https://www.trustradius.com/products/swimlane) — accessed 2026-10-09 *(first cited in profile 12)*
- [Security Boulevard — The 10 Best Splunk SOAR Alternatives in 2026](https://securityboulevard.com/2026/08/the-10-best-splunk-soar-alternatives-in-2026-compared-before-the-python-playbook-migration/) — accessed 2026-10-09 *(first cited in profile 12)*
- [D3 Security — Morpheus FAQ](https://d3security.com/faq/) — accessed 2026-10-09 *(first cited in profile 13)*
- [D3 Security — The Accountable Agentic SOC Platform](https://d3security.com/) — accessed 2026-10-09 *(first cited in profile 13)*
- [D3 Security — Morpheus for the Enterprise SOC](https://d3security.com/morpheus/enterprise/) — accessed 2026-10-09 *(first cited in profile 13)*
- [D3 Security — Agentic SOC Platform](https://d3security.com/agentic-soc-platform/) — accessed 2026-10-09 *(first cited in profile 13)*
- [D3 Security — AI SOC Platform ($0.27/alert comparison)](https://d3security.com/ai-soc-platform/) — accessed 2026-10-09 *(first cited in profile 13)*
- [MSSP Alert — D3 Security Unveils Morpheus (2025-03-19)](https://www.msspalert.com/news/d3-security-unveils-morpheus-its-ai-powered-autonomous-soc) — accessed 2026-10-09 *(first cited in profile 13)*
- [G2 — D3 Security Management Systems seller reviews](https://www.g2.com/sellers/d3-security-management-systems) — accessed 2026-10-09 *(first cited in profile 13)*
- [Tines — Introducing the AI Agent Action (2025-06-24)](https://www.tines.com/blog/introducing-ai-agents/) — accessed 2026-10-09 *(first cited in profile 14)*
- [Tines — Turo case study](https://www.tines.com/case-studies/turo/) — accessed 2026-10-09 *(first cited in profile 14)*
- [G2 — Tines Reviews (4.7/5, 397 reviews)](https://www.g2.com/it/products/tines/reviews) — accessed 2026-10-09 *(first cited in profile 14)*
- [checkthat.ai — Best SOAR tools (Tines rating corroboration)](https://checkthat.ai/answers/what-are-the-best-soar-tools-available) — accessed 2026-10-09 *(first cited in profile 14)*
- [apis.io — Tines API provider profile](https://apis.io/providers/tines/) — accessed 2026-10-09 *(first cited in profile 14)*
- [Security Boulevard — Best SOAR Alternatives in 2026: The Agentic Platforms Replacing Legacy SOAR](https://securityboulevard.com/2026/07/best-soar-alternatives-in-2026-the-agentic-platforms-replacing-legacy-soar/) — accessed 2026-10-09 *(first cited in profile 14)*
- [cybercompanyprofiles — Tines: Funding, Competitors and Strategy](https://cybercompanyprofiles.com/companies/tines) — accessed 2026-10-09 *(first cited in profile 14)*
- [PANW — Understand Cortex XSOAR licenses](https://cortex-docs.paloaltonetworks.com/cortex-xsoar-8-saas/learn-about-cortex-xsoar/understand-cortex-xsoar-licenses) — accessed 2026-10-09 *(first cited in profile 15)*
- [PANW — Cortex XSOAR 8 FAQs: MSSP and Multi-Tenancy Deployment](https://docs-cortex.paloaltonetworks.com/r/Cortex-XSOAR/8/Cortex-XSOAR-8-FAQs/MSSP-and-Multi-Tenancy-Deployment) — accessed 2026-10-09 *(first cited in profile 15)*
- [PANW — Multi-Tenant Overview (6.13 hosted/enterprise-MSSP entitlements)](https://docs-cortex.paloaltonetworks.com/r/Cortex-XSOAR/6.13/Cortex-XSOAR-Multi-Tenant-Guide/Multi-Tenant-Overview) — accessed 2026-10-09 *(first cited in profile 15)*
- [PANW — Plan and prepare your deployment (Git-based content dev)](https://cortex-docs.paloaltonetworks.com/cortex-xsoar-8-saas/onboard-cortex-xsoar/plan-and-prepare-your-deployment.md) — accessed 2026-10-09 *(first cited in profile 15)*
- [PeerSpot — Palo Alto Networks Cortex XSOAR reviews](https://www.peerspot.com/products/palo-alto-networks-cortex-xsoar-reviews) — accessed 2026-10-09 *(first cited in profile 15)*
- [PANW Cortex XSOAR datasheet (PDF, ML-driven assistant)](https://www.boll.ch/datasheets/Cortex_XSOAR.pdf) — accessed 2026-10-09 *(first cited in profile 15)*

### Batch D sources

- [Explore Cortex XSIAM Security Analytics — Palo Alto Networks](https://www.paloaltonetworks.com/cortex/cortex-xsiam) — accessed 2026-10-09 *(first cited in profile 16)*
- [Cortex AgentiX — Palo Alto Networks](https://www.paloaltonetworks.com/cortex/agentix) — accessed 2026-10-09 *(first cited in profile 16)*
- [The 12 Best Agentic SOC Platforms in 2026 — Security Boulevard](https://securityboulevard.com/2026/07/the-12-best-agentic-soc-platforms-in-2026-architectures-autonomy-levels-and-a-full-comparison/) — accessed 2026-10-09 *(first cited in profile 16)*
- [The Best AI SOC Platforms in 2026: An Honest Comparison — Security Boulevard (Swimlane)](https://securityboulevard.com/2026/09/the-best-ai-soc-platforms-in-2026-an-honest-comparison/) — accessed 2026-10-09 *(first cited in profile 16)*
- [Cortex XSIAM Reviews — G2](https://www.g2.com/products/palo-alto-cortex-xsiam/reviews) — accessed 2026-10-09 *(first cited in profile 16)*
- [What's New in Cortex (July '26) — Palo Alto Networks Blog](https://www.paloaltonetworks.com/blog/security-operations/whats-new-in-cortex-july-2026/) — accessed 2026-10-09 *(first cited in profile 16)*
- [Charlotte AI: Agentic Analyst for Cybersecurity — CrowdStrike](https://www.crowdstrike.com/en-us/platform/charlotte-ai/) — accessed 2026-10-09 *(first cited in profile 17)*
- [Next-Gen SIEM — CrowdStrike](https://www.crowdstrike.com/en-us/platform/next-gen-siem/) — accessed 2026-10-09 *(first cited in profile 17)*
- [The Best Agentic SOC for CrowdStrike in 2026 (and Where Charlotte AI Fits) — Security Boulevard](https://securityboulevard.com/2026/08/the-best-agentic-soc-for-crowdstrike-in-2026-and-where-charlotte-ai-fits/) — accessed 2026-10-09 *(first cited in profile 17)*
- [Top 16 AI SOC Tools for 2026 — Intezer](https://intezer.com/blog/top-15-ai-soc-platforms-in-2026) — accessed 2026-10-09 *(first cited in profile 17)*
- [Falcon Next-Gen SIEM Reviews — G2](https://www.g2.com/products/falcon-next-gen-siem/reviews) — accessed 2026-10-09 *(first cited in profile 17)*
- [Charlotte Agentic SOAR Pricing — CrowdStrike](https://www.crowdstrike.com/en-us/platform/charlotte-ai/agentic-soar/pricing/) — accessed 2026-10-09 *(first cited in profile 17)*
- [SentinelOne Unveils New AI Security Offerings — SentinelOne Investor Relations (March 23, 2026)](https://investors.sentinelone.com/press-releases/news-details/2026/SentinelOne-Unveils-New-AI-Security-Offerings-to-Give-Defenders-a-Decisive-Advantage-/default.aspx) — accessed 2026-10-09 *(first cited in profile 18)*
- [Best AI SOC Analyst Software 2026 — TrustRadius](https://www.trustradius.com/categories/ai-soc-analyst) — accessed 2026-10-09 *(first cited in profile 18)*
- [SentinelOne Singularity Cloud Security Reviews — G2](https://www.g2.com/products/sentinelone-singularity-cloud-security/reviews) — accessed 2026-10-09 *(first cited in profile 18)*
- [Best AI SOC Tools: Top 10 Platforms for 2026 — Palo Alto Networks Cyberpedia](https://www.paloaltonetworks.com/cyberpedia/ai-soc-tools-comparison) — accessed 2026-10-09 *(first cited in profile 18)*
- [Microsoft Security Copilot — Pricing](https://www.microsoft.com/en-us/security/pricing/microsoft-security-copilot) — accessed 2026-10-09 *(first cited in profile 19)*
- [Microsoft Sentinel Pricing — Microsoft Azure](https://azure.microsoft.com/en-us/pricing/details/microsoft-sentinel/) — accessed 2026-10-09 *(first cited in profile 19)*
- [Plan costs and understand Microsoft Sentinel pricing and billing — Microsoft Learn](https://learn.microsoft.com/en-us/azure/sentinel/billing) — accessed 2026-10-09 *(first cited in profile 19)*
- [Microsoft Sentinel — Cloud-native SIEM](https://www.microsoft.com/en-us/security/business/siem-and-xdr/microsoft-sentinel-siem) — accessed 2026-10-09 *(first cited in profile 19)*
- [The Best AI SOC Platforms 2026 — D3 Security](https://d3security.com/blog/ai-soc-platforms-2026/) — accessed 2026-10-09 *(first cited in profile 19)*
- [Google Security Operations — Google Cloud](https://cloud.google.com/security/products/security-operations) — accessed 2026-10-09 *(first cited in profile 20)*
- [Google Security Operations Reviews — G2](https://www.g2.com/products/google-security-operations/reviews) — accessed 2026-10-09 *(first cited in profile 20)*
- [Best SOAR Alternatives in 2026 — Security Boulevard](https://securityboulevard.com/2026/07/best-soar-alternatives-in-2026-the-agentic-platforms-replacing-legacy-soar/) — accessed 2026-10-09 *(first cited in profile 20)*
- [Gemini in Google SecOps overview — Google Cloud Documentation](https://docs.cloud.google.com/chronicle/docs/secops/gemini-secops) — accessed 2026-10-09 *(first cited in profile 20)*

### Batch E sources

- [Splunk ES features](https://www.splunk.com/en_us/products/splunk-enterprise-security-features.html) — accessed 2026-10-09 *(first cited in profile 21)*
- [Splunk ES Essentials](https://www.splunk.com/en_us/products/enterprise-security-essentials.html) — accessed 2026-10-09 *(first cited in profile 21)*
- [Splunk ES 8.5 AI Assistant docs](https://help.splunk.com/en/splunk-enterprise-security-8/administer/8.5/ai-assistant-in-security-and-agentic-capabilities/choose-which-models-the-ai-assistant-uses-in-splunk-enterprise-security) — accessed 2026-10-09 *(first cited in profile 21)*
- [Splunkbase — Splunk ES](https://splunkbase.splunk.com/app/263) — accessed 2026-10-09 *(first cited in profile 21)*
- [Splunk pricing models](https://www.splunk.com/en_us/products/pricing/pricing-models.html) — accessed 2026-10-09 *(first cited in profile 21)*
- [G2 — Splunk SOAR](https://www.g2.com/products/splunk-soar-security-orchestration-automation-and-response/reviews) — accessed 2026-10-09 *(first cited in profile 21)*
- [G2 — Enterprise AI SOC Agents category](https://www.g2.com/categories/ai-soc-agents/enterprise) — accessed 2026-10-09 *(first cited in profile 21)*
- [Intezer — SOAR Platform Guide](https://intezer.com/guides/soar-security/soar-platform-guide) — accessed 2026-10-09 *(first cited in profile 21)*
- [Expert Insights — Best 10 SOC Automation Platforms](https://expertinsights.com/security-operations/best-soc-automation-platforms) — accessed 2026-10-09 *(first cited in profile 21)*
- [Expert Insights — Best 11 AI SOC Platforms](https://expertinsights.com/security-operations/top-ai-soc-platforms-for-business) — accessed 2026-10-09 *(first cited in profile 21)*
- [Palo Alto Cyberpedia — AI SOC tools comparison](https://www.paloaltonetworks.com/cyberpedia/ai-soc-tools-comparison) — accessed 2026-10-09 *(first cited in profile 21)*
- [Security Boulevard — 12 Best Agentic SOC Platforms in 2026](https://securityboulevard.com/2026/07/the-12-best-agentic-soc-platforms-in-2026-architectures-autonomy-levels-and-a-full-comparison/) — accessed 2026-10-09 *(first cited in profile 21)*
- [Reuters — Cisco to buy Splunk](https://www.reuters.com/markets/deals/cisco-acquire-splunk-28-billion-2023-09-21/) — accessed 2026-10-09 *(first cited in profile 21)*
- [Investopedia — Cisco completes $28B purchase](https://www.investopedia.com/cisco-systems-completes-its-usd28-billion-purchase-of-splunk-8610584) — accessed 2026-10-09 *(first cited in profile 21)*
- [Panther — Best AI SOC Platforms](https://panther.com/blog/best-ai-soc-platforms) — accessed 2026-10-09 *(first cited in profile 21)*
- [IBM newsroom — Palo Alto/IBM announcement](https://newsroom.ibm.com/2024-05-15-Palo-Alto-Networks-and-IBM-to-Jointly-Provide-AI-powered-Security-Offerings-IBM-to-Deliver-Security-Consulting-Services-Across-Palo-Alto-Networks-Security-Platforms) — accessed 2026-10-09 *(first cited in profile 22)*
- [IBM — QRadar SaaS acquisition completion](https://www.ibm.com/new/announcements/palo-alto-networks-ibm-qradar-saas) — accessed 2026-10-09 *(first cited in profile 22)*
- [IBM — QRadar SIEM pricing/deployment](https://www.ibm.com/products/qradar-siem/pricing) — accessed 2026-10-09 *(first cited in profile 22)*
- [Palo Alto Cyberpedia — QRadar acquired](https://www.paloaltonetworks.com/cyberpedia/ibm-qradar-acquired-by-palo-alto-networks) — accessed 2026-10-09 *(first cited in profile 22)*
- [TechTarget — IBM sells QRadar SaaS](https://www.techtarget.com/cybersecurity/news/366585436/IBM-sells-QRadar-SaaS-assets-to-Palo-Alto-Networks) — accessed 2026-10-09 *(first cited in profile 22)*
- [Forrester — IBM Surrenders SIEM](https://www.forrester.com/blogs/ibm-surrenders-siem-while-panw-tries-to-gain-ground-on-tech-titans/) — accessed 2026-10-09 *(first cited in profile 22)*
- [DarkReading — CISOs grapple with IBM exit](https://www.darkreading.com/cybersecurity-analytics/ciso-grapple-with-ibm-unexpected-cybersecurity-software-exit) — accessed 2026-10-09 *(first cited in profile 22)*
- [CompariSec — QRadar review](https://www.comparisec.com/vendors/siem/ibm-security-qradar) — accessed 2026-10-09 *(first cited in profile 22)*
- [Stellar Cyber product docs (6.4)](https://docs.stellarcyber.ai/prod-docs/6.4.xs/Common/Stellar-Description.htm) — accessed 2026-10-09 *(first cited in profile 23)*
- [Stellar Cyber BlackHat 2025 release](https://stellarcyber.ai/stellar-cyber-improves-soc-operations-with-human-augmented-autonomous-cybersecurity-blackhat-2025/) — accessed 2026-10-09 *(first cited in profile 23)*
- [Stellar Cyber site/pricing](https://stellarcyber.ai/pricing/) — accessed 2026-10-09 *(first cited in profile 23)*
- [Stellar Cyber — XDR solutions](https://stellarcyber.ai/learn/xdr-solutions/) — accessed 2026-10-09 *(first cited in profile 23)*
- [Intezer — AI SOC for mid-sized enterprises](https://intezer.com/guides/ai-soc/mid-sized-enterprises) — accessed 2026-10-09 *(first cited in profile 23)*
- [UnderDefense — 9 Best AI SOC for Enterprise](https://underdefense.com/blog/ai-soc-for-enterprise/) — accessed 2026-10-09 *(first cited in profile 23)*
- [Security Boulevard — Best AI SOC Platforms 2026](https://securityboulevard.com/2026/03/the-best-ai-soc-platforms-2026-comprehensive-comparison-guide/) — accessed 2026-10-09 *(first cited in profile 23)*
- [primaryguard battlecard](https://primaryguard.com/battlecards/autonomous-soc/stellar-vs-sentinel) — accessed 2026-10-09 *(first cited in profile 23)*
- [hunters.security](https://www.hunters.security/) — accessed 2026-10-09 *(first cited in profile 24)*
- [G2 — Hunters SOC Platform](https://www.g2.com/products/hunters-soc-platform/reviews) — accessed 2026-10-09 *(first cited in profile 24)*
- [G2 — pros/cons](https://www.g2.com/products/hunters-soc-platform/reviews?qs=pros-and-cons) — accessed 2026-10-09 *(first cited in profile 24)*
- [Expert Insights — Hunters review](https://expertinsights.com/reviews/huntersai) — accessed 2026-10-09 *(first cited in profile 24)*
- [CB Insights — Hunters profile](https://www.cbinsights.com/company/huntersai) — accessed 2026-10-09 *(first cited in profile 24)*
- [Blumberg Capital — Snowflake Ventures investment](https://blumbergcapital.com/news-insights/hunters-receives-growth-funding-from-snowflake-ventures/) — accessed 2026-10-09 *(first cited in profile 24)*
- [Cyber Company Profiles — Hunters](https://cybercompanyprofiles.com/companies/hunters) — accessed 2026-10-09 *(first cited in profile 24)*
- [rfp.wiki — Hunters](https://www.rfp.wiki/it-security/security-information-and-event-management/hunters) — accessed 2026-10-09 *(first cited in profile 24)*
- [Hunters LinkedIn](https://www.linkedin.com/company/hunters-ai) — accessed 2026-10-09 *(first cited in profile 24)*
- [GitHub — panther-labs/panther-analysis](https://github.com/panther-labs/panther-analysis) — accessed 2026-10-09 *(first cited in profile 25)*
- [Panther — detection engine](https://panther.com/product/detection-engine) — accessed 2026-10-09 *(first cited in profile 25)*
- [Panther docs — developer workflows](https://docs.panther.com/panther-developer-workflows/overview) — accessed 2026-10-09 *(first cited in profile 25)*
- [Panther docs — MCP server](https://docs.panther.com/ai/mcp/mcp-server) — accessed 2026-10-09 *(first cited in profile 25)*
- [Panther — AI SOC agent](https://panther.com/product/ai-soc-agent) — accessed 2026-10-09 *(first cited in profile 25)*
- [panther.com/pricing (platform & hosting)](https://panther.com/pricing/) — accessed 2026-10-09 *(first cited in profile 25)*
- [Panther blog — best SIEM tools](https://panther.com/blog/best-siem-tools) — accessed 2026-10-09 *(first cited in profile 25)*
- [Panther blog — MCP tools](https://panther.com/blog/mcp-tools) — accessed 2026-10-09 *(first cited in profile 25)*
- [Panther blog — AI detection engineering](https://panther.com/blog/ai-detection-engineering) — accessed 2026-10-09 *(first cited in profile 25)*
- [UnderDefense — detection-as-code AI SOC tools](https://underdefense.com/blog/best-ai-soc-tools-with-detection-as-code-and-python-ci-cd-for-detection-rules/) — accessed 2026-10-09 *(first cited in profile 25)*
- [G2 — Panther review](https://www.g2.com/products/panther/reviews/panther-review-12919421) — accessed 2026-10-09 *(first cited in profile 25)*
