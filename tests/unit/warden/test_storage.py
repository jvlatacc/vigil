"""PolicyStore tests: 0700 directory, 0600 files, atomic writes, no parse."""

from __future__ import annotations

import os

from services.warden.storage import PolicyStore


def _mode(path) -> int:
    return os.stat(path).st_mode & 0o777


class TestPermissions:
    def test_data_dir_is_private_0700(self, tmp_path) -> None:
        base = tmp_path / "state"
        PolicyStore(base)

        assert base.is_dir()
        assert _mode(base) == 0o700

    def test_existing_loose_dir_is_tightened_to_0700(self, tmp_path) -> None:
        base = tmp_path / "state"
        base.mkdir()
        os.chmod(base, 0o755)

        PolicyStore(base)

        assert _mode(base) == 0o700

    def test_credentials_file_is_0600(self, tmp_path) -> None:
        store = PolicyStore(tmp_path)

        store.save_credentials("wn-abc123", "node-tok")

        assert _mode(tmp_path / "credentials.json") == 0o600

    def test_policy_file_is_0600(self, tmp_path) -> None:
        store = PolicyStore(tmp_path)

        store.save_policy({"policy_version": 1})

        assert _mode(tmp_path / "policy.json") == 0o600


class TestRoundTrip:
    def test_credentials_round_trip(self, tmp_path) -> None:
        store = PolicyStore(tmp_path)

        store.save_credentials("wn-abc123", "tok-1")
        assert store.load_credentials() == ("wn-abc123", "tok-1")

        store.save_credentials("wn-abc123", "tok-2")
        assert store.load_credentials() == ("wn-abc123", "tok-2")

    def test_missing_files_read_as_none(self, tmp_path) -> None:
        store = PolicyStore(tmp_path)

        assert store.load_credentials() is None
        assert store.load_policy() is None

    def test_corrupt_files_read_as_none_not_raise(self, tmp_path) -> None:
        store = PolicyStore(tmp_path)
        (tmp_path / "credentials.json").write_bytes(b"{not json")
        (tmp_path / "policy.json").write_bytes(b"[1, 2, 3]")

        assert store.load_credentials() is None
        assert store.load_policy() is None

    def test_policy_round_trips_exactly(self, tmp_path) -> None:
        store = PolicyStore(tmp_path)
        doc = {
            "policy_version": 42,
            "envelope": {"payload": "abc", "payloadType": "t", "signatures": []},
            "payload_hash": "f" * 64,
        }

        store.save_policy(doc)

        assert store.load_policy() == doc

    def test_atomic_write_leaves_no_tmp_files(self, tmp_path) -> None:
        store = PolicyStore(tmp_path)

        store.save_credentials("wn-abc123", "tok")
        store.save_policy({"policy_version": 1})

        assert list(tmp_path.glob(".*")) == []
