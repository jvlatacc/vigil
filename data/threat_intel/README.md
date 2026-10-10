# Bundled threat-intel data

Seed data shipped so a fresh Vigil install boots with authoritative known-bad
context already in the `threat_indicators` store — loaded by
`core/threat_intel/kev_seed.py` at database init, kept current by the feed
poller. Only sources whose terms permit bundling with attribution live here;
everything else is fetched at runtime from user-configured feeds.

## cisa-kev/catalog.json — CISA Known Exploited Vulnerabilities catalog

| | |
| --- | --- |
| Source | CISA Known Exploited Vulnerabilities Catalog: <https://www.cisa.gov/known-exploited-vulnerabilities-catalog> |
| Feed URL | <https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json> (no key required) |
| Retrieved | 2026-10-09 (catalogVersion `2026.10.08`, released `2026-10-08T20:09:18.9833Z`, 1,739 entries) |
| License | U.S. Government published data; CISA requests attribution and community benefit when reused. Bundled unmodified with this attribution. |
| SHA-256 | `fb1621beec7db19d99c1f919dede3d4cc01ad88acd16f79f1592929c4826dfee` |

The file is the official JSON exactly as served — no fields added, removed, or
reformatted — so the seed loader and the poller's refresher parse the same
bytes the publisher distributes.

### Regenerating

    python scripts/update_kev_catalog.py

Run before a release, then update the Retrieved line above (and the SHA-256)
when the file changed. The script validates the catalog shape before storing,
so a truncated download cannot replace a good snapshot.
