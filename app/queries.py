"""List/search helpers tuned for larger SQLite datasets."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Optional, Sequence
from zoneinfo import ZoneInfo

# Columns needed by list UI / API list payload (detail still uses SELECT *).
LIST_COLUMNS = (
    "id, job_name, build_id, build_date, git_repository, git_branch, git_commit, "
    "commit_msg, commit_author, commit_id, commit_files, "
    "docker_registry, docker_repository, docker_image_tag, docker_image_digest, "
    "build_result, build_url, duration_ms, created_at, updated_at"
)

DEFAULT_PAGE_SIZE = 20
ALLOWED_PAGE_SIZES = (20, 50, 100)
# Cap job filter dropdown so millions of historical job names cannot bloat HTML.
JOB_DROPDOWN_LIMIT = 300
# Soft guard: very deep OFFSET is expensive in SQLite; clamp UI page.
MAX_PAGE = 500


def clamp_page_size(value: Optional[int]) -> int:
    try:
        size = int(value) if value is not None else DEFAULT_PAGE_SIZE
    except (TypeError, ValueError):
        return DEFAULT_PAGE_SIZE
    if size in ALLOWED_PAGE_SIZES:
        return size
    if size < 1:
        return DEFAULT_PAGE_SIZE
    return min(max(size, 1), 100)


def clamp_page(page: int, total_pages: int) -> int:
    total_pages = max(1, total_pages)
    page = max(1, int(page or 1))
    page = min(page, total_pages)
    page = min(page, MAX_PAGE)
    return page


def escape_like(term: str) -> str:
    """Escape %, _ and \\ for use with LIKE ... ESCAPE '\\'."""
    return (
        term.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


def normalize_date_from(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    text = value.strip()
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        return f"{text}T00:00:00"
    return text


def normalize_date_to(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    text = value.strip()
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        return f"{text}T23:59:59.999999"
    return text


def local_today_iso() -> str:
    """Today's date (YYYY-MM-DD) in configured TZ (default Asia/Shanghai)."""
    tz_name = os.getenv("TZ", "Asia/Shanghai")
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("Asia/Shanghai")
    return datetime.now(tz).date().isoformat()


def apply_default_today_dates(
    query_params,
    date_from: Optional[str],
    date_to: Optional[str],
) -> tuple[Optional[str], Optional[str], bool]:
    """
    HTML list default: fill blank dateFrom/dateTo with local today so the form
    always shows concrete dates. Pass all=1 to list entire history (no date filter).

    Returns (date_from, date_to, used_default).
    """
    df = (date_from or "").strip()
    dt = (date_to or "").strip()
    # Explicit all-history mode only when no concrete dates were chosen.
    if str(query_params.get("all") or "") == "1" and not df and not dt:
        return None, None, False

    today = local_today_iso()
    used = False
    if not df and not dt:
        return today, today, True
    if not df:
        df = today
        used = True
    if not dt:
        dt = today
        used = True
    return df, dt, used


def build_filters(
    q: Optional[str],
    job: Optional[str],
    branch: Optional[str],
    result: Optional[str],
    date_from: Optional[str],
    date_to: Optional[str],
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []

    if q and q.strip():
        like = f"%{escape_like(q.strip())}%"
        clauses.append(
            "("
            "job_name LIKE ? ESCAPE '\\' OR "
            "git_branch LIKE ? ESCAPE '\\' OR "
            "git_commit LIKE ? ESCAPE '\\' OR "
            "docker_image_tag LIKE ? ESCAPE '\\' OR "
            "docker_repository LIKE ? ESCAPE '\\' OR "
            "git_repository LIKE ? ESCAPE '\\'"
            ")"
        )
        params.extend([like] * 6)
    if job and job.strip():
        clauses.append("job_name = ?")
        params.append(job.strip())
    if branch and branch.strip():
        clauses.append("git_branch LIKE ? ESCAPE '\\'")
        params.append(f"%{escape_like(branch.strip())}%")
    if result and result.strip():
        clauses.append("build_result = ?")
        params.append(result.strip())
    date_from_n = normalize_date_from(date_from)
    date_to_n = normalize_date_to(date_to)
    if date_from_n:
        clauses.append("build_date >= ?")
        params.append(date_from_n)
    if date_to_n:
        clauses.append("build_date <= ?")
        params.append(date_to_n)

    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


def search_builds(
    db,
    *,
    q: Optional[str] = None,
    job: Optional[str] = None,
    branch: Optional[str] = None,
    result: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> tuple[Sequence[Any], int, int, int]:
    """
    Returns (rows, total, page, page_size).
    Uses a single connection and clamped pagination.
    """
    page_size = clamp_page_size(page_size)
    where, params = build_filters(q, job, branch, result, date_from, date_to)

    total = db.execute(
        f"SELECT COUNT(*) FROM build_records{where}", params
    ).fetchone()[0]

    total_pages = max(1, (total + page_size - 1) // page_size) if total else 1
    # Also respect MAX_PAGE for deep OFFSET cost
    hard_max_pages = min(total_pages, MAX_PAGE)
    page = clamp_page(page, hard_max_pages)
    offset = (page - 1) * page_size

    rows = db.execute(
        f"SELECT {LIST_COLUMNS} FROM build_records{where} "
        f"ORDER BY build_date DESC, id DESC LIMIT ? OFFSET ?",
        params + [page_size, offset],
    ).fetchall()
    return rows, total, page, page_size


def load_global_stats(db) -> dict:
    """One table scan for dashboard stats."""
    row = db.execute(
        """
        SELECT
            COUNT(*) AS total,
            COUNT(DISTINCT job_name) AS jobs,
            COUNT(DISTINCT CASE
                WHEN git_branch IS NOT NULL AND git_branch != '' THEN git_branch
            END) AS branches,
            SUM(CASE WHEN build_result = 'SUCCESS' THEN 1 ELSE 0 END) AS success
        FROM build_records
        """
    ).fetchone()
    return {
        "total": row["total"] or 0,
        "jobs": row["jobs"] or 0,
        "branches": row["branches"] or 0,
        "success": int(row["success"] or 0),
    }


def load_job_filter_options(db, limit: int = JOB_DROPDOWN_LIMIT) -> list[str]:
    """
    Prefer recently active jobs over a full DISTINCT of entire history.
    Keeps the filter dropdown bounded for large datasets.
    """
    rows = db.execute(
        """
        SELECT job_name
        FROM build_records
        GROUP BY job_name
        ORDER BY MAX(build_date) DESC, job_name ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [r[0] for r in rows]


def load_result_filter_options(db) -> list[str]:
    rows = db.execute(
        """
        SELECT DISTINCT build_result
        FROM build_records
        WHERE build_result IS NOT NULL AND build_result != ''
        ORDER BY build_result
        """
    ).fetchall()
    return [r[0] for r in rows]
