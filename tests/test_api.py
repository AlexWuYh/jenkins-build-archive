from datetime import datetime, timedelta, timezone

from conftest import sample_build


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_create_requires_token(client):
    r = client.post("/api/v1/builds", json=sample_build())
    assert r.status_code == 401


def test_create_and_upsert(client, auth_headers):
    r = client.post("/api/v1/builds", json=sample_build(), headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["jobName"] == "demo-job"
    assert body["buildId"] == 1
    record_id = body["id"]
    created_at = body["createdAt"]

    r2 = client.post(
        "/api/v1/builds",
        json=sample_build(gitCommit="bbbbbbbb", dockerImageTag="2.3.1-1-retry"),
        headers=auth_headers,
    )
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["id"] == record_id
    assert body2["gitCommit"] == "bbbbbbbb"
    assert body2["createdAt"] == created_at
    assert body2["updatedAt"] >= created_at


def test_reject_javascript_build_url(client, auth_headers):
    r = client.post(
        "/api/v1/builds",
        json=sample_build(buildUrl="javascript:alert(1)"),
        headers=auth_headers,
    )
    assert r.status_code == 422


def test_date_to_includes_same_day(client, auth_headers):
    client.post("/api/v1/builds", json=sample_build(), headers=auth_headers)
    r = client.get("/api/v1/builds", params={"dateFrom": "2026-08-14", "dateTo": "2026-08-14"})
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["items"][0]["buildId"] == 1


def test_list_and_get(client, auth_headers):
    created = client.post(
        "/api/v1/builds", json=sample_build(), headers=auth_headers
    ).json()
    listed = client.get("/api/v1/builds", params={"q": "release/2.3.1"}).json()
    assert listed["total"] == 1
    detail = client.get(f"/api/v1/builds/{created['id']}")
    assert detail.status_code == 200
    assert detail.json()["dockerImageTag"] == "2.3.1-1"


def test_delete_requires_token(client, auth_headers):
    created = client.post(
        "/api/v1/builds", json=sample_build(), headers=auth_headers
    ).json()
    r = client.delete(f"/api/v1/builds/{created['id']}")
    assert r.status_code == 401
    r2 = client.delete(f"/api/v1/builds/{created['id']}", headers=auth_headers)
    assert r2.status_code == 200
    assert r2.json()["deleted"] is True
    assert client.get(f"/api/v1/builds/{created['id']}").status_code == 404


def test_delete_missing(client, auth_headers):
    r = client.delete("/api/v1/builds/99999", headers=auth_headers)
    assert r.status_code == 404


def test_unconfigured_token_is_fail_closed(client, monkeypatch):
    from app import main as main_mod

    main_mod.API_TOKEN = "change-me-please"
    r = client.post(
        "/api/v1/builds",
        json=sample_build(),
        headers={"Authorization": "Bearer change-me-please"},
    )
    assert r.status_code == 503


def test_html_page_rejects_zero(client):
    r = client.get("/", params={"page": 0})
    assert r.status_code == 422


def test_retention_max_per_job(client, auth_headers, monkeypatch):
    from app import retention as retention_mod
    from app.db import get_db
    from app.retention import RetentionConfig, apply_retention

    for i in range(1, 6):
        client.post(
            "/api/v1/builds",
            json=sample_build(
                buildId=i,
                buildDate=f"2026-08-0{i}T12:00:00+08:00",
                dockerImageTag=f"t-{i}",
            ),
            headers=auth_headers,
        )

    with get_db() as db:
        result = apply_retention(db, RetentionConfig(days=0, max_per_job=2))
    assert result["deletedByMaxPerJob"] == 3
    listed = client.get("/api/v1/builds").json()
    assert listed["total"] == 2
    ids = {item["buildId"] for item in listed["items"]}
    assert ids == {5, 4}


def test_retention_days(client, auth_headers):
    from app.db import get_db
    from app.retention import RetentionConfig, apply_retention

    old = (datetime.now(timezone.utc) - timedelta(days=40)).strftime("%Y-%m-%dT%H:%M:%SZ")
    recent = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    client.post(
        "/api/v1/builds",
        json=sample_build(buildId=10, buildDate=old, jobName="old-job"),
        headers=auth_headers,
    )
    client.post(
        "/api/v1/builds",
        json=sample_build(buildId=11, buildDate=recent, jobName="new-job"),
        headers=auth_headers,
    )

    with get_db() as db:
        result = apply_retention(db, RetentionConfig(days=30, max_per_job=0))
    assert result["deletedByDays"] == 1
    listed = client.get("/api/v1/builds").json()
    assert listed["total"] == 1
    assert listed["items"][0]["jobName"] == "new-job"


def test_retention_run_endpoint(client, auth_headers, monkeypatch):
    monkeypatch.setenv("RETENTION_MAX_PER_JOB", "1")
    from app import retention as retention_mod

    # reload config from env inside endpoint via load_retention_config
    client.post(
        "/api/v1/builds",
        json=sample_build(buildId=1, buildDate="2026-08-01T12:00:00Z"),
        headers=auth_headers,
    )
    client.post(
        "/api/v1/builds",
        json=sample_build(buildId=2, buildDate="2026-08-02T12:00:00Z"),
        headers=auth_headers,
    )
    r = client.post("/api/v1/admin/retention/run", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["retentionMaxPerJob"] == 1
    assert body["deletedByMaxPerJob"] == 1
    assert client.get("/api/v1/builds").json()["total"] == 1


def test_stats(client, auth_headers):
    client.post("/api/v1/builds", json=sample_build(), headers=auth_headers)
    r = client.get("/api/v1/stats")
    assert r.status_code == 200
    assert r.json()["totalBuilds"] == 1
    assert r.json()["success"] == 1
