from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from conftest import sample_build
from app.queries import apply_default_today_dates, local_today_iso


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
