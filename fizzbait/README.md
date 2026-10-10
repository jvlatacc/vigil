# fizzbait — sample range datasets

Benign traffic families and recognizable attack scenarios, shaped as
**finding records** (not raw device logs) so a Vigil SOC instance ingests
them with its native S3 folder sync — no code changes, no parsers, no
pipeline work. One call pulls the whole prefix.

```text
fizzbait/
├── manifest.yaml                     # index: per-file label, source, row count, MITRE
├── benign/                           # 6 traffic families — the quiet baseline
│   ├── dns.jsonl       proxy.jsonl   firewall.jsonl
│   ├── edr.jsonl       email.jsonl   flow.jsonl
└── malicious/                        # 8 attack scenarios — the signal
    ├── c2_beaconing.jsonl            lateral_movement_rdp.jsonl
    ├── dns_exfiltration.jsonl        credential_brute_force.jsonl
    ├── phishing_initial_access.jsonl ransomware_staging.jsonl
    ├── powershell_encoded.jsonl      port_scan.jsonl
```

Each benign family pairs with the attack scenario that shares its
`data_source` (e.g. `benign/dns.jsonl` vs `malicious/dns_exfiltration.jsonl`),
which is what makes the set demoable as a range: same sources, one side noisy
and normal, the other carrying a real pattern.

## Record format

JSON Lines — one finding-shaped record per line. The only field Vigil's
ingestion requires is `finding_id`; every other field below is what keeps the
rows realistic, filterable, and deduplicated on re-sync. The dialect matches
`tests/fixtures/sample_findings.json`, which `to_internal_finding` maps
automatically.

| Field | Notes |
|---|---|
| `finding_id` | **Stable** `f-<yyyymmdd>-<scenario>-<nnnn>`. Stable ids are what make an S3 re-sync dedupe instead of duplicating findings. |
| `timestamp` | ISO-8601 UTC (`2026-03-01T09:15:00Z`). |
| `data_source` | From Vigil's demo vocabulary: `dns`, `proxy`, `firewall`, `edr`, `email`, `flow`. |
| `severity` | Benign: `info`/`low`. Malicious: `medium`–`critical`. |
| `status` | `new` — findings land in the normal triage queue. |
| `anomaly_score` | Benign < 0.3; malicious ≥ 0.5. |
| `title`, `description` | Human-readable alert summary; the description states the distinguishing signal. |
| `mitre_predictions` | `{technique: confidence}`. **Empty on benign rows**; ≥ 1 entry on malicious rows. |
| `entity_context` | JSONB passthrough: ips, ports, scenario detail, the attack's distinguishing signal, and the `label`. |
| `cluster_id` | `benign-<family>-NNN` or `c-<attack>-NNN`, reusing the demo cluster vocabulary (`core/platform/demo_data_service.py`). |
| `source_metadata` | Provenance: `dataset: fizzbait`, source `file`, `schema_version` — so ingested rows trace back to this folder. |

Raw-log flavor rides inside `entity_context.source_evidence` — Vigil ingests
finding rows; it has no syslog/CEF/NetFlow parser, and this dataset does not
ask for one.

## Label convention

Labels live three ways, and every record carries all three:

1. **`entity_context.label`** — `benign` or `malicious`, on 100% of records.
2. **Directory split** — `benign/*.jsonl` vs `malicious/*.jsonl`.
3. **`cluster_id`** — `benign-*` vs `c-<attack>-NNN`.

`manifest.yaml` (deliberately YAML, not JSON: the S3 sync ingests every `.json`
under the prefix as findings) indexes each file with its label, data source,
scenario, exact row count, and MITRE coverage.

## Attack scenarios

| File (`malicious/`) | MITRE | `data_source` | `cluster_id` | Signal in `entity_context` |
|---|---|---|---|---|
| `c2_beaconing.jsonl` | T1071.001, T1071.004 | flow | `c-beaconing-001` | Fixed-interval outbound TLS, low jitter, connection times |
| `lateral_movement_rdp.jsonl` | T1021.001 | flow | `c-lateral-movement-002` | Workstation→workstation RDP chains, off-hours, unusual account |
| `dns_exfiltration.jsonl` | T1048.003 | dns | `c-exfiltration-003` | High-entropy subdomains, single resolver, abnormal query volume |
| `credential_brute_force.jsonl` | T1110.001 | auth (via flow) | `c-credential-theft-004` | Failure bursts per account, password spray, one eventual success |
| `phishing_initial_access.jsonl` | T1566.001, T1566.002 | email | `c-phishing-006` | New-sender domains, credential-lure subjects, clickthroughs |
| `ransomware_staging.jsonl` | T1486, T1490 | edr | `c-ransomware-005` | Mass extension rewrites, shadow-copy deletion, ransom note |
| `powershell_encoded.jsonl` | T1059.001, T1027 | edr | `c-powershell-emulation-007` | Base64 `-enc` command lines, office parent spawning shell |
| `port_scan.jsonl` | T1046 | firewall | `c-port-scan-008` | Single source sweeping ports/hosts, refused-then-open hits |

## Ingest into Vigil from S3

```bash
# 1. Push the folder — this repo layout maps 1:1 onto the bucket prefix.
aws s3 sync . s3://<bucket>/fizzbait/ --exclude "*" --include "fizzbait/*"

# 2. Point Vigil at the bucket (once — or via the UI: Settings → S3).
curl -X POST "$VIGIL_URL/api/config/s3" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $VIGIL_API_TOKEN" \
  -d '{
    "bucket_name": "<bucket>",
    "region": "us-east-1",
    "auth_method": "credentials",
    "parquet_prefix": "fizzbait/"
  }'

# 3. Ingest the whole prefix — recursive, extension-routed.
curl -X POST "$VIGIL_URL/api/ingest/sync-s3-folder?prefix=fizzbait/" \
  -H "Authorization: Bearer $VIGIL_API_TOKEN"
```

With `parquet_prefix` set to `fizzbait/`, step 3 works with no explicit prefix.
Re-running the sync is safe: stable `finding_id`s mean rows dedupe instead of
duplicating. Credentials resolve through the instance's secrets manager
(`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_SESSION_TOKEN`), and API
clients authenticate with the session cookie or `Authorization: Bearer` token
the rest of the Vigil API uses.

## Validation

`tests/unit/test_fizzbait_datasets.py` enforces the contract in CI: every
line parses, ids match the stable convention, labels agree with directories,
benign rows stay quiet (`anomaly_score < 0.3`, no MITRE), malicious rows carry
a prediction at `anomaly_score ≥ 0.5`, the manifest matches disk exactly, all
files stay ≤ 2 MiB, and nothing trips a `.gitignore` pattern. Run it with:

```bash
venv/bin/pytest tests/unit/test_fizzbait_datasets.py -v
```

Files are static and hand-tunable JSONL; there is no generator script in the
repo. Keep any edit consistent with the manifest (`row_count` is asserted
exactly) and the id convention.
