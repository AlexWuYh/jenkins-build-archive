from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from conftest import sample_build
from app.queries import apply_default_today_dates, build_list_query, local_today_iso


def test_local_today_iso_format():
    value = local_today_iso()
    assert len(value) == 10
    assert value[4] == "-" and value[7] == "-"


def test_apply_default_fills_blank_dates():
    class QP(dict):
        def get(self, key, default=None):
            return dict.get(self, key, default)

    df, dt, used = apply_default_today_dates(QP(), None, None)
    assert used is True
    assert df == dt == local_today_iso()

    # empty strings also fill today
    df2, dt2, used2 = apply_default_today_dates(QP({"dateFrom": "", "dateTo": ""}), "", "")
    assert used2 is True
    assert df2 == dt2 == local_today_iso()


def test_all_param_skips_default():
    class QP(dict):
        def get(self, key, default=None):
            return dict.get(self, key, default)

    df, dt, used = apply_default_today_dates(QP({"all": "1"}), "", "")
    assert used is False
    assert df is None and dt is None


def test_index_defaults_to_today(client, auth_headers, monkeypatch):
    monkeypatch.setenv("TZ", "Asia/Shanghai")
    today = local_today_iso()
    yesterday = (
        datetime.now(ZoneInfo("Asia/Shanghai")).date() - timedelta(days=1)
    ).isoformat()

    client.post(
        "/api/v1/builds",
        json=sample_build(
            buildId=101,
            buildDate=f"{today}T10:00:00+08:00",
            jobName="today-job",
        ),
        headers=auth_headers,
    )
    client.post(
        "/api/v1/builds",
        json=sample_build(
            buildId=102,
            buildDate=f"{yesterday}T10:00:00+08:00",
            jobName="yesterday-job",
        ),
        headers=auth_headers,
    )

    r = client.get("/")
    assert r.status_code == 200
    # date inputs must show concrete today values
    assert f'name="dateFrom" value="{today}"' in r.text
    assert f'name="dateTo" value="{today}"' in r.text
    assert "找到 <b>1</b> 条构建记录" in r.text
    assert 'aria-label="选择 today-job #101"' in r.text
    assert 'aria-label="选择 yesterday-job #102"' not in r.text

    # all=1 shows full history, empty date fields
    r2 = client.get("/", params={"all": "1"})
    assert "找到 <b>2</b> 条构建记录" in r2.text
    assert 'aria-label="选择 yesterday-job #102"' in r2.text


def test_build_list_query_preserves_all_history():
    qs = build_list_query(all_history=True, page_size=20, q="demo")
    assert "all=1" in qs
    assert "dateFrom" not in qs
    assert "dateTo" not in qs
    assert "q=demo" in qs
    assert "pageSize=20" in qs

    ranged = build_list_query(
        date_from="2026-08-21",
        date_to="2026-08-21",
        page_size=50,
        all_history=False,
    )
    assert "all=" not in ranged
    assert "dateFrom=2026-08-21" in ranged
    assert "pageSize=50" in ranged


def test_html_all_history_pagination_keeps_filter_and_row_numbers(
    client, auth_headers
):
    for i in range(1, 5):
        client.post(
            "/api/v1/builds",
            json=sample_build(buildId=i, jobName=f"page-job-{i}"),
            headers=auth_headers,
        )

    listing = client.get("/", params={"all": "1", "pageSize": 2})
    assert listing.status_code == 200
    assert "找到 <b>4</b> 条构建记录" in listing.text
    assert "all=1&amp;pageSize=2&amp;page=2" in listing.text
    assert 'scope="col" class="col-index">序号</th>' in listing.text
    assert 'class="col-index muted">1</td>' in listing.text
    assert 'aria-label="结果列表分页"' in listing.text
    assert 'aria-label="表格底部分页"' in listing.text

    page2 = client.get("/", params={"all": "1", "pageSize": 2, "page": 2})
    assert page2.status_code == 200
    today = local_today_iso()
    assert "找到 <b>4</b> 条构建记录" in page2.text
    assert "全部历史" in page2.text
    assert f'name="dateFrom" value="{today}"' not in page2.text
    assert 'name="all" value="1"' in page2.text
    assert 'class="col-index muted">3</td>' in page2.text
    assert 'class="col-index muted">4</td>' in page2.text

    toolbar = page2.text.find('aria-label="结果列表分页"')
    table_pager = page2.text.find('aria-label="表格底部分页"')
    batch = page2.text.find('id="batch-delete-heading"')
    assert 0 < toolbar < table_pager < batch
