"""The Wazuh provenance dict survives to the persistence seam (AC-1).

``_wazuh_finding`` builds a rich metadata block — vendor, wazuh_alert_id,
rule_id, rule_level, agent identity — that the fixed field lists on the way
to Postgres used to drop, leaving stored Wazuh alerts indistinguishable from
Kibana-native ones. Here the transform drives the same path the poller does
(``ingest_finding`` and ``_ingest_finding_batch``), with the database seam
captured, so a fixed-field-list edit that drops the key again fails here
before it silently blanks the column.
"""

from unittest.mock import patch

import pytest

from core.integrations.elastic.ingestion import ElasticIngestion
from core.ingestion.ingestion_service import IngestionService, to_internal_finding

pytestmark = pytest.mark.unit

ES_URL = "https://indexer.test:9200"
INDEX = "wazuh-alerts-4.x-*"

# Shape of a wazuh-alerts-4.x document (Wazuh 4.14) after its Filebeat pipeline.
ALERT = {
    "_index": "wazuh-alerts-4.x-2026.09.28",
    "_id": "abc123",
    "_source": {
        "@timestamp": "2026-09-28T11:17:18.394Z",
        "id": "1790597838.2112422",
        "agent": {"id": "001", "name": "web01"},
        "rule": {
            "id": "5712",
            "level": 10,
            "description": "sshd: brute force trying to get access to the system.",
            "groups": ["syslog", "sshd"],
        },
        "data": {"srcip": "203.0.113.7", "dstuser": "root"},
        "full_log": "Sep 28 11:17:17 web01 sshd[1]: Failed password for root",
    },
}


def _ingestion() -> ElasticIngestion:
    config = {
        "elasticsearch_url": ES_URL,
        "kibana_url": None,
        "api_key": None,
        "username": "vigil-reader",
        "password": "secret",
        "index_pattern": INDEX,
        "min_rule_level": None,
        "verify_ssl": False,
    }
    with patch("core.integrations.elastic.ingestion.resolve", return_value=config):
        return ElasticIngestion()


def _wazuh_finding() -> dict:
    return _ingestion().transform_alert_to_finding(ALERT)


class _CaptureDb:
    """The seam ingest_finding talks to, keeping what it was handed."""

    def __init__(self):
        self.created: list[dict] = []
        self.bulk: list[dict] = []

    def get_finding(self, finding_id):
        return None

    def create_finding(self, **kwargs):
        self.created.append(kwargs)
        return object()

    def bulk_create_findings(self, rows):
        self.bulk.extend(rows)
        return {"imported": len(rows), "skipped": 0}


@pytest.fixture
def service():
    svc = IngestionService()
    svc.use_database = True
    svc.db_service = _CaptureDb()
    return svc


def test_ingest_finding_delivers_wazuh_provenance_to_the_seam(service):
    assert service.ingest_finding(_wazuh_finding()) is True
    assert service.stats["findings_imported"] == 1

    row = service.db_service.created[0]
    meta = row["source_metadata"]
    assert meta["vendor"] == "wazuh"
    assert meta["wazuh_alert_id"] == ALERT["_source"]["id"]
    assert meta["rule_id"] == "5712"
    assert meta["rule_level"] == 10
    assert meta["agent_name"] == "web01"
    assert row["data_source"] == "elastic"


def test_ingest_finding_batch_delivers_wazuh_provenance_to_the_bulk_seam(service):
    service._ingest_finding_batch([_wazuh_finding()])
    assert service.stats["findings_imported"] == 1

    row = service.db_service.bulk[0]
    meta = row["source_metadata"]
    assert meta["vendor"] == "wazuh"
    assert meta["wazuh_alert_id"] == ALERT["_source"]["id"]
    assert meta["rule_id"] == "5712"
    assert meta["rule_level"] == 10
    assert meta["agent_name"] == "web01"


def test_metadata_alias_maps_onto_source_metadata():
    provenance = {"vendor": "wazuh", "rule_id": "5712"}
    out = to_internal_finding({"metadata": provenance, "finding_id": "f-1"})
    assert out["source_metadata"] == provenance
    assert "metadata" not in out


def test_internal_source_metadata_wins_over_the_alias():
    out = to_internal_finding(
        {
            "source_metadata": {"vendor": "wazuh"},
            "metadata": {"vendor": "something-else"},
            "finding_id": "f-1",
        }
    )
    assert out["source_metadata"] == {"vendor": "wazuh"}


def test_scalar_metadata_is_kept_wrapped_and_blank_metadata_is_absent():
    out = to_internal_finding({"metadata": "text blob", "finding_id": "f-1"})
    assert out["source_metadata"] == {"metadata": "text blob"}

    out = to_internal_finding({"metadata": {}, "finding_id": "f-1"})
    assert "source_metadata" not in out
