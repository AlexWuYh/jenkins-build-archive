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


def test_commit_files_single_element_with_embedded_newlines(client, auth_headers):
    """Jenkins often sends one list item with real or escaped newlines."""
    payload = sample_build(
        buildId=58,
        commitMsg="更新Jenkinsfile, Jenkinsfile-Arm",
        commitAuthor="yinghaowu@deepglint.com",
        commitId="cd238d2ab716ba76a4f0a9e5f1e24a42370f0307",
        commitFiles=["✏️ Jenkinsfile\n✏️ Jenkinsfile-Arm"],
    )
    r = client.post("/api/v1/builds", json=payload, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["commitFiles"] == ["✏️ Jenkinsfile", "✏️ Jenkinsfile-Arm"]

    # literal backslash-n (double-escaped from shell)
    payload2 = sample_build(
        buildId=59,
        commitFiles=["✏️ Jenkinsfile\\n✏️ Jenkinsfile-Arm"],
    )
    r2 = client.post("/api/v1/builds", json=payload2, headers=auth_headers)
    assert r2.status_code == 200
    assert r2.json()["commitFiles"] == ["✏️ Jenkinsfile", "✏️ Jenkinsfile-Arm"]

    page = client.get(f"/build/{r.json()['id']}")
    assert page.status_code == 200
    assert "file-chip" in page.text
    assert "Jenkinsfile-Arm" in page.text
    # Should render as separate chips, not one blob with \\n
    assert "Jenkinsfile\\n" not in page.text
    assert page.text.count("file-chip") >= 2


def test_commit_files_without_newlines_unchanged(client, auth_headers):
    """Normal list / single path must not be mangled and must not error."""
    # multi-element list, no \n anywhere
    r = client.post(
        "/api/v1/builds",
        json=sample_build(
            buildId=60,
            commitFiles=["Jenkinsfile", "Jenkinsfile-Arm", "src/main.py"],
        ),
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["commitFiles"] == ["Jenkinsfile", "Jenkinsfile-Arm", "src/main.py"]

    # single path string
    r2 = client.post(
        "/api/v1/builds",
        json=sample_build(buildId=61, commitFiles="Jenkinsfile"),
        headers=auth_headers,
    )
    assert r2.status_code == 200
    assert r2.json()["commitFiles"] == ["Jenkinsfile"]

    # empty / placeholder → null, not 422
    for bid, files in ((62, []), (63, "-"), (64, None), (65, [""])):
        payload = sample_build(buildId=bid, commitFiles=files)
        if files is None:
            payload.pop("commitFiles", None)
        resp = client.post("/api/v1/builds", json=payload, headers=auth_headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["commitFiles"] is None


def test_expand_commit_files_never_raises():
    from app.schemas import expand_commit_files

    cases = [
        None,
        "",
        "-",
        "Jenkinsfile",
        ["a.py", "b.py"],
        ["single"],
        "a.py\nb.py",
        ["a\\nb"],
        "not-json [ broken",
        {"weird": "dict"},
        12345,
        [None, "", "ok.py"],
        [["nested", "list"]],
    ]
    for case in cases:
        result = expand_commit_files(case)
        assert result is None or (
            isinstance(result, list) and all(isinstance(x, str) for x in result)
        )


def test_git_commit_falls_back_to_commit_id(client, auth_headers):
    """Jenkins may only push commitId; Git card should still show the SHA."""
    payload = sample_build(
        buildId=3,
        gitCommit=None,
        commitId="51d58dc80abcdef",
        commitMsg="更新Jenkinsfile",
        commitAuthor="yinghaowu@example.com",
        commitFiles=["Jenkinsfile"],
    )
    # omit gitCommit key entirely
    payload.pop("gitCommit", None)
    r = client.post("/api/v1/builds", json=payload, headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["gitCommit"] == "51d58dc80abcdef"
    assert body["commitId"] == "51d58dc80abcdef"

    page = client.get(f"/build/{body['id']}")
    assert page.status_code == 200
    assert "51d58dc80abcdef" in page.text
    # Commit 详情 no longer repeats commitId label
    assert "commitId" not in page.text
    assert "更新Jenkinsfile" in page.text


def test_duration_ms_shown_on_detail(client, auth_headers):
    payload = sample_build(buildId=10, durationMs=125500)
    r = client.post("/api/v1/builds", json=payload, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["durationMs"] == 125500

    page = client.get(f"/build/{r.json()['id']}")
    assert page.status_code == 200
    assert "构建耗时" in page.text
    assert "2 分" in page.text
    assert "5.5 秒" in page.text


def test_duration_ms_accepts_numeric_string(client, auth_headers):
    payload = sample_build(buildId=11, durationMs="90000")
    r = client.post("/api/v1/builds", json=payload, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["durationMs"] == 90000


def test_git_commit_dash_placeholder_falls_back_to_commit_id(client, auth_headers):
    """Real Jenkins payloads often send gitCommit='-' when GIT_COMMIT is unset."""
    payload = sample_build(
        buildId=1819,
        gitCommit="-",
        commitId="8952fbcf2e1e8e95b07fddfa5dd04739a97ad671",
        commitMsg="更新Jenkinsfile",
        commitAuthor="yinghaowu@deepglint.com",
        commitFiles=["✏️ Jenkinsfile"],
    )
    r = client.post("/api/v1/builds", json=payload, headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["gitCommit"] == "8952fbcf2e1e8e95b07fddfa5dd04739a97ad671"
    assert body["commitId"] == "8952fbcf2e1e8e95b07fddfa5dd04739a97ad671"
    assert body["gitCommit"] != "-"

    page = client.get(f"/build/{body['id']}")
    assert page.status_code == 200
    assert "8952fbcf2e1e8e95b07fddfa5dd04739a97ad671" in page.text

    listing = client.get("/?all=1")
    assert listing.status_code == 200
    assert "8952fbcf2e" in listing.text
