from datetime import datetime, timedelta, timezone

from conftest import sample_build


def test_admin_page_renders(client):
    r = client.get("/admin")
    assert r.status_code == 200
    assert "最长保留" in r.text
    assert 'name="retention_days"' in r.text
    assert 'name="password"' in r.text


def test_save_retention_and_run(client, auth_headers, admin_password):
    old = (datetime.now(timezone.utc) - timedelta(days=400)).strftime("%Y-%m-%dT%H:%M:%SZ")
    recent = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    client.post(
        "/api/v1/builds",
        json=sample_build(buildId=1, buildDate=old, jobName="old-job"),
        headers=auth_headers,
    )
    client.post(
        "/api/v1/builds",
        json=sample_build(buildId=2, buildDate=recent, jobName="new-job"),
        headers=auth_headers,
    )

    r = client.post(
        "/admin/retention",
        data={
            "password": admin_password,
            "retention_days": "365",
            "retention_max_per_job": "0",
            "action": "save_and_run",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"].rstrip("/").endswith("/admin") or r.headers["location"] == "/admin"
    assert "notice=" not in r.headers["location"]

    listed = client.get("/api/v1/builds").json()
    assert listed["total"] == 1
    assert listed["items"][0]["jobName"] == "new-job"

    admin = client.get("/admin")
    assert "保留策略已执行" in admin.text
    admin2 = client.get("/admin")
    assert "保留策略已执行" not in admin2.text

    # config persists
    cfg = client.get("/api/v1/admin/retention", headers=auth_headers).json()
    assert cfg["retentionDays"] == 365
    assert cfg["source"] == "database"


def test_save_retention_rejects_bad_password(client, admin_password):
    r = client.post(
        "/admin/retention",
        data={
            "password": "nope",
            "retention_days": "365",
            "retention_max_per_job": "0",
            "action": "save",
        },
    )
    assert r.status_code == 401
