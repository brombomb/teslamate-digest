import os
import pytest
from pathlib import Path


@pytest.fixture(autouse=True)
def isolate_test_data_dir(tmp_path, monkeypatch):
    """
    Ensures that test execution uses an isolated temporary data directory
    and never mutates the user's persistent SQLite database or configuration.
    """
    test_data_dir = tmp_path / "test_data"
    test_data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATA_DIR", str(test_data_dir))

    import app.storage as storage
    import app.config as config

    monkeypatch.setattr(storage, "DATA_DIR", test_data_dir)
    monkeypatch.setattr(storage, "SQLITE_DB_PATH", test_data_dir / "teslamate_digest.db")
    monkeypatch.setattr(storage, "LEGACY_CONFIG_FILE", test_data_dir / "config.json")
    monkeypatch.setattr(storage, "LEGACY_MAINTENANCE_FILE", test_data_dir / "maintenance.json")

    monkeypatch.setattr(config, "DATA_DIR", test_data_dir)
    monkeypatch.setattr(config, "CONFIG_FILE", test_data_dir / "config.json")
    monkeypatch.setattr(config, "MAINTENANCE_FILE", test_data_dir / "maintenance.json")
