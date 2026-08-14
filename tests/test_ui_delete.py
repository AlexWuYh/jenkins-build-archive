from conftest import sample_build


def test_detail_page_shows_delete_form(client, auth_headers, admin_password):
    created = client.post(
        "/api/v1/builds", json=sample_build(), headers=auth_headers
    ).json()
    r = client.get(f"/build/{created['id']}")
    assert r.status_code == 200
    html = r.text
    assert 'action="/build/' in html
    assert "/delete" in html
    assert 'name="password"' in html
    assert 'name="confirm"' in html
    assert "永久删除" in html
    assert admin_password not in html
    assert f'value="{admin_password}"' not in html
    assert "test-token-not-for-production" not in html


def test_ui_delete_success(client, auth_headers, admin_password):
    created = client.post(
        "/api/v1/builds", json=sample_build(), headers=auth_headers
    ).json()
    r = client.post(
        f"/build/{created['id']}/delete",
        data={"password": admin_password, "confirm": "DELETE"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "notice=deleted" in r.headers["location"]
    assert client.get(f"/api/v1/builds/{created['id']}").status_code == 404

    home = client.get(r.headers["location"])
    assert home.status_code == 200
    assert "已删除构建记录" in home.text
    assert "demo-job" in home.text


def test_ui_delete_requires_confirm_word(client, auth_headers, admin_password):
    created = client.post(
        "/api/v1/builds", json=sample_build(), headers=auth_headers
    ).json()
    r = client.post(
        f"/build/{created['id']}/delete",
        data={"password": admin_password, "confirm": "delete"},
        follow_redirects=False,
    )
    assert r.status_code == 400
    assert "DELETE" in r.text
    assert client.get(f"/api/v1/builds/{created['id']}").status_code == 200


def test_ui_delete_rejects_bad_password(client, auth_headers):
    created = client.post(
        "/api/v1/builds", json=sample_build(), headers=auth_headers
    ).json()
    r = client.post(
        f"/build/{created['id']}/delete",
        data={"password": "wrong-password", "confirm": "DELETE"},
        follow_redirects=False,
    )
    assert r.status_code == 401
    assert "密码" in r.text
    assert client.get(f"/api/v1/builds/{created['id']}").status_code == 200


def test_ui_delete_missing_record(client, admin_password):
    r = client.post(
        "/build/99999/delete",
        data={"password": admin_password, "confirm": "DELETE"},
    )
    assert r.status_code == 404


def test_batch_delete(client, auth_headers, admin_password):
    ids = []
    for i in range(1, 4):
        body = client.post(
            "/api/v1/builds",
            json=sample_build(buildId=i, dockerImageTag=f"t-{i}"),
            headers=auth_headers,
        ).json()
        ids.append(body["id"])

    r = client.post(
        "/builds/batch-delete",
        data={
            "ids": [str(ids[0]), str(ids[2])],
            "password": admin_password,
            "confirm": "DELETE",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "batch-deleted" in r.headers["location"]
    assert client.get(f"/api/v1/builds/{ids[0]}").status_code == 404
    assert client.get(f"/api/v1/builds/{ids[1]}").status_code == 200
    assert client.get(f"/api/v1/builds/{ids[2]}").status_code == 404


def test_batch_delete_requires_selection(client, auth_headers, admin_password):
    client.post("/api/v1/builds", json=sample_build(), headers=auth_headers)
    r = client.post(
        "/builds/batch-delete",
        data={"password": admin_password, "confirm": "DELETE"},
    )
    assert r.status_code == 400
    assert "勾选" in r.text
