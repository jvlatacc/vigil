"""Re-fetch the official CISA KEV catalog into the bundled snapshot.

Run before a release so the bundled seed carries the current catalog:

    python scripts/update_kev_catalog.py

The file is stored exactly as served — no reformatting — so the seed loader
and the poller's refresher parse the same bytes. Provenance lives beside the
catalog in data/threat_intel/README.md; update its retrieval date when this
changes the file.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = REPO_ROOT / "data" / "threat_intel" / "cisa-kev" / "catalog.json"

# The official feed URL, as published on CISA's Known Exploited
# Vulnerabilities Catalog page (https://www.cisa.gov/known-exploited-
# vulnerabilities-catalog). No key, no terms beyond the catalog's
# community-benefit notice.
KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"


def main() -> int:
    request = urllib.request.Request(
        KEV_URL, headers={"User-Agent": "vigil-kev-seed/1.0"}
    )
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
        body = response.read()

    # Validate before storing: a truncated or reshaped catalog must not
    # replace a good snapshot.
    catalog = json.loads(body)
    entries = catalog["vulnerabilities"]
    if not entries or not all(e.get("cveID") for e in entries):
        raise SystemExit("catalog has no vulnerabilities or an entry without cveID")

    CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CATALOG_PATH.write_bytes(body)
    print(
        f"wrote {CATALOG_PATH.relative_to(REPO_ROOT)}: "
        f"catalogVersion={catalog.get('catalogVersion')} "
        f"dateReleased={catalog.get('dateReleased')} "
        f"count={len(entries)}"
    )
    print("update the retrieval date in data/threat_intel/README.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
