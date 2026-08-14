from conftest import sample_build


def test_create_with_commit_fields(client, auth_headers):
    payload = sample_build(
        commitMsg="feat: add monitor metrics\n\nMore details here.",
        commitAuthor="Alice <alice@example.com>",
        commitId="d948e59faf9d9b5fee4902a4ee81349f843792b4",
        commitFiles=["src/main.py", "README.md", "app/db.py"],
    )
    r = client.post("/api/v1/builds", json=payload, headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["commitMsg"].startswith("feat: add monitor metrics")
    assert body["commitAuthor"] == "Alice <alice@example.com>"
    assert body["commitId"].startswith("d948e59")
    assert body["commitFiles"] == ["src/main.py", "README.md", "app/db.py"]

    detail = client.get(f"/api/v1/builds/{body['id']}")
    assert detail.status_code == 200
    assert detail.json()["commitFiles"][0] == "src/main.py"

    page = client.get(f"/build/{body['id']}")
    assert page.status_code == 200
    assert "feat: add monitor metrics" in page.text
    assert "Alice" in page.text
    assert "src/main.py" in page.text
    assert "Commit 详情" in page.text


def test_commit_files_as_string(client, auth_headers):
    payload = sample_build(
        buildId=2,
        commitMsg="fix",
        commitAuthor="Bob",
        commitId="abc123",
        commitFiles="a.py\nb.py",
    )
    r = client.post("/api/v1/builds", json=payload, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["commitFiles"] == ["a.py", "b.py"]
