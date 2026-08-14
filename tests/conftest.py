import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def api_token() -> str:
    return "test-token-not-for-production"


@pytest.fixture()
def admin_password() -> str:
    return "OpsDelete!42"


@pytest.fixture()
def client(
    tmp_path: Path,
    api_token: str,
    admin_password: str,
    monkeypatch: pytest.MonkeyPatch,
):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    monkeypatch.setenv("API_TOKEN", api_token)
    monkeypatch.setenv("ADMIN_PASSWORD", admin_password)
    monkeypatch.setenv("RETENTION_DAYS", "0")
    monkeypatch.setenv("RETENTION_MAX_PER_JOB", "0")

    from app import main as main_mod
    from app.db import init_db

    main_mod.API_TOKEN = api_token
    main_mod.ADMIN_PASSWORD = admin_password
    init_db()

    with TestClient(main_mod.app) as test_client:
        yield test_client


@pytest.fixture()
def auth_headers(api_token: str) -> dict:
    return {"Authorization": f"Bearer {api_token}"}


def sample_build(**overrides):
    base = {
        "jobName": "demo-job",
        "buildId": 1,
        "buildDate": "2026-08-14T10:32:18+08:00",
        "gitRepository": "https://github.com/example/demo.git",
        "gitBranch": "release/2.3.1",
        "gitCommit": "a8f31c2abcdef",
        "dockerRegistry": "registry.example.local",
        "dockerRepository": "dev/demo",
        "dockerImageTag": "2.3.1-1",
        "dockerImageDigest": "sha256:abc",
        "buildResult": "SUCCESS",
        "buildUrl": "https://jenkins.example.local/job/demo-job/1/",
        "durationMs": 12000,
    }
    base.update(overrides)
    return base
