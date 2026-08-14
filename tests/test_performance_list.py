from conftest import sample_build


def test_list_page_size(client, auth_headers):
    for i in range(1, 6):
        client.post(
            "/api/v1/builds",
            json=sample_build(buildId=i, dockerImageTag=f"t-{i}"),
            headers=auth_headers,
        )
    r = client.get("/api/v1/builds", params={"pageSize": 2, "page": 1})
    assert r.status_code == 200
    body = r.json()
    assert body["pageSize"] == 2
    assert body["total"] == 5
    assert len(body["items"]) == 2

    r2 = client.get("/api/v1/builds", params={"pageSize": 2, "page": 3})
    assert r2.json()["page"] == 3
    assert len(r2.json()["items"]) == 1


def test_html_page_size_selector(client, auth_headers):
    client.post("/api/v1/builds", json=sample_build(), headers=auth_headers)
    r = client.get("/", params={"pageSize": 50})
    assert r.status_code == 200
    assert 'name="pageSize"' in r.text
    assert "selected" in r.text


def test_like_special_chars_do_not_error(client, auth_headers):
    client.post(
        "/api/v1/builds",
        json=sample_build(gitBranch="feat/100%_done", dockerImageTag="x_y%z"),
        headers=auth_headers,
    )
    r = client.get("/api/v1/builds", params={"q": "100%"})
    assert r.status_code == 200
    # escaped % should still match literal percent via ESCAPE
    assert r.json()["total"] >= 1
