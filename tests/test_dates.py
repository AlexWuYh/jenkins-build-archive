from app.queries import escape_like, normalize_date_from, normalize_date_to


def test_normalize_date_from_ymd():
    assert normalize_date_from("2026-08-14") == "2026-08-14T00:00:00"


def test_normalize_date_to_ymd():
    assert normalize_date_to("2026-08-14") == "2026-08-14T23:59:59.999999"


def test_normalize_preserves_full_iso():
    full = "2026-08-14T10:32:18+08:00"
    assert normalize_date_from(full) == full
    assert normalize_date_to(full) == full


def test_normalize_empty():
    assert normalize_date_from(None) is None
    assert normalize_date_to("") is None


def test_escape_like():
    assert escape_like("a%b_c\\d") == "a\\%b\\_c\\\\d"
