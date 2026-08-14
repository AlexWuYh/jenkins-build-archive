import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote, unquote

from fastapi import FastAPI, Form, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .db import get_db, init_db
from .queries import (
    ALLOWED_PAGE_SIZES,
    DEFAULT_PAGE_SIZE,
    JOB_DROPDOWN_LIMIT,
    MAX_PAGE,
    apply_default_today_dates,
    clamp_page_size,
    load_global_stats,
    load_job_filter_options,
    load_result_filter_options,
    local_today_iso,
    search_builds,
)
from .retention import apply_retention, load_retention_config, save_retention_config
from .schemas import BuildRecordIn

APP_NAME = os.getenv("APP_NAME", "Jenkins Build Archive")
API_TOKEN = os.getenv("API_TOKEN", "change-me-please")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "change-me-please")
BASE_DIR = Path(__file__).resolve().parent

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app = FastAPI(title=APP_NAME, version="1.4.0")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.on_event("startup")
def startup():
    init_db()
    with get_db() as db:
        cfg = load_retention_config(db)
        if cfg.enabled:
            apply_retention(db, cfg)


def token_is_configured() -> bool:
    return bool(API_TOKEN) and API_TOKEN != "change-me-please"


def admin_password_configured() -> bool:
    return bool(ADMIN_PASSWORD) and ADMIN_PASSWORD != "change-me-please"


def _secure_equal(provided: Optional[str], expected: str) -> bool:
    if not provided or not expected:
        return False
    a = provided.encode("utf-8")
    b = expected.encode("utf-8")
    if len(a) != len(b):
        return False
    return secrets.compare_digest(a, b)


def extract_bearer_or_header(
    authorization: Optional[str], x_api_token: Optional[str]
) -> Optional[str]:
    if x_api_token:
        return x_api_token.strip()
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def check_api_token(token: Optional[str]) -> Optional[str]:
    if not token_is_configured():
        return "API_TOKEN is not configured"
    if not _secure_equal(token, API_TOKEN):
        return "Invalid API token"
    return None


def check_admin_password(password: Optional[str]) -> Optional[str]:
    """Return error message if password invalid; None if OK."""
    if not admin_password_configured():
        return "ADMIN_PASSWORD is not configured"
    if not _secure_equal((password or "").strip(), ADMIN_PASSWORD):
        return "Invalid admin password"
    return None


def require_token(authorization: Optional[str], x_api_token: Optional[str]) -> None:
    token = extract_bearer_or_header(authorization, x_api_token)
    err = check_api_token(token)
    if err == "API_TOKEN is not configured":
        raise HTTPException(status_code=503, detail=err)
    if err:
        raise HTTPException(status_code=401, detail=err)


def row_to_dict(row):
    return {
        "id": row["id"],
        "jobName": row["job_name"],
        "buildId": row["build_id"],
        "buildDate": row["build_date"],
        "gitRepository": row["git_repository"],
        "gitBranch": row["git_branch"],
        "gitCommit": row["git_commit"],
        "dockerRegistry": row["docker_registry"],
        "dockerRepository": row["docker_repository"],
        "dockerImageTag": row["docker_image_tag"],
        "dockerImageDigest": row["docker_image_digest"],
        "buildResult": row["build_result"],
        "buildUrl": row["build_url"],
        "durationMs": row["duration_ms"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


FLASH_COOKIE = "jba_flash"
FLASH_MAX_AGE = 60  # seconds; one-shot display


def set_flash_redirect(url: str, message: str) -> RedirectResponse:
    """PRG flash via cookie so refresh / shared URLs do not keep showing the banner."""
    resp = RedirectResponse(url=url, status_code=303)
    resp.set_cookie(
        key=FLASH_COOKIE,
        value=quote(message, safe=""),
        max_age=FLASH_MAX_AGE,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return resp


def _parse_id_list(ids: List[str]) -> List[int]:
    result: List[int] = []
    for raw in ids:
        try:
            value = int(str(raw).strip())
        except (TypeError, ValueError):
            continue
        if value >= 1:
            result.append(value)
    # preserve order, unique
    seen = set()
    unique = []
    for i in result:
        if i not in seen:
            seen.add(i)
            unique.append(i)
    return unique


@app.get("/health")
def health():
    with get_db() as db:
        db.execute("SELECT 1").fetchone()
    return {"status": "ok", "service": APP_NAME}


@app.get("/api/v1/stats")
def stats():
    with get_db() as db:
        s = load_global_stats(db)
        cfg = load_retention_config(db)
    return {
        "totalBuilds": s["total"],
        "jobs": s["jobs"],
        "branches": s["branches"],
        "success": s["success"],
        "retentionDays": cfg.days,
        "retentionMaxPerJob": cfg.max_per_job,
    }


@app.post("/api/v1/builds", status_code=200)
def create_or_update_build(
    payload: BuildRecordIn,
    authorization: Optional[str] = Header(default=None),
    x_api_token: Optional[str] = Header(default=None),
):
    require_token(authorization, x_api_token)
    now = utc_now_iso()
    with get_db() as db:
        db.execute(
            """
            INSERT INTO build_records (
                job_name, build_id, build_date, git_repository, git_branch, git_commit,
                docker_registry, docker_repository, docker_image_tag, docker_image_digest,
                build_result, build_url, duration_ms, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_name, build_id) DO UPDATE SET
                build_date=excluded.build_date,
                git_repository=excluded.git_repository,
                git_branch=excluded.git_branch,
                git_commit=excluded.git_commit,
                docker_registry=excluded.docker_registry,
                docker_repository=excluded.docker_repository,
                docker_image_tag=excluded.docker_image_tag,
                docker_image_digest=excluded.docker_image_digest,
                build_result=excluded.build_result,
                build_url=excluded.build_url,
                duration_ms=excluded.duration_ms,
                updated_at=excluded.updated_at
            """,
            (
                payload.jobName,
                payload.buildId,
                payload.buildDate,
                payload.gitRepository,
                payload.gitBranch,
                payload.gitCommit,
                payload.dockerRegistry,
                payload.dockerRepository,
                payload.dockerImageTag,
                payload.dockerImageDigest,
                payload.buildResult,
                payload.buildUrl,
                payload.durationMs,
                now,
                now,
            ),
        )
        row = db.execute(
            "SELECT * FROM build_records WHERE job_name=? AND build_id=?",
            (payload.jobName, payload.buildId),
        ).fetchone()
    return row_to_dict(row)


@app.delete("/api/v1/builds/{record_id}")
def delete_build(
    record_id: int,
    authorization: Optional[str] = Header(default=None),
    x_api_token: Optional[str] = Header(default=None),
):
    require_token(authorization, x_api_token)
    with get_db() as db:
        row = db.execute(
            "SELECT * FROM build_records WHERE id=?", (record_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Build not found")
        db.execute("DELETE FROM build_records WHERE id=?", (record_id,))
    return {
        "deleted": True,
        "id": record_id,
        "jobName": row["job_name"],
        "buildId": row["build_id"],
    }


@app.get("/api/v1/admin/retention")
def retention_config_api(
    authorization: Optional[str] = Header(default=None),
    x_api_token: Optional[str] = Header(default=None),
):
    require_token(authorization, x_api_token)
    with get_db() as db:
        cfg = load_retention_config(db)
    return {
        "enabled": cfg.enabled,
        "retentionDays": cfg.days,
        "retentionMaxPerJob": cfg.max_per_job,
        "source": cfg.source,
    }


@app.post("/api/v1/admin/retention/run")
def retention_run_api(
    authorization: Optional[str] = Header(default=None),
    x_api_token: Optional[str] = Header(default=None),
):
    require_token(authorization, x_api_token)
    with get_db() as db:
        cfg = load_retention_config(db)
        result = apply_retention(db, cfg)
    return result


@app.get("/api/v1/builds/{record_id}")
def api_get_build(record_id: int):
    with get_db() as db:
        row = db.execute("SELECT * FROM build_records WHERE id=?", (record_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Build not found")
    return row_to_dict(row)


@app.get("/api/v1/builds")
def api_list_builds(
    q: Optional[str] = None,
    job: Optional[str] = None,
    branch: Optional[str] = None,
    result: Optional[str] = None,
    dateFrom: Optional[str] = None,
    dateTo: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=100),
):
    with get_db() as db:
        rows, total, page, page_size = search_builds(
            db,
            q=q,
            job=job,
            branch=branch,
            result=result,
            date_from=dateFrom,
            date_to=dateTo,
            page=page,
            page_size=pageSize,
        )
    return {
        "items": [row_to_dict(r) for r in rows],
        "total": total,
        "page": page,
        "pageSize": page_size,
    }


def _fetch_build_row(record_id: int):
    with get_db() as db:
        return db.execute(
            "SELECT * FROM build_records WHERE id=?", (record_id,)
        ).fetchone()


def _detail_response(
    request: Request,
    row,
    *,
    error: Optional[str] = None,
    status_code: int = 200,
):
    return templates.TemplateResponse(
        "detail.html",
        {
            "request": request,
            "row": row,
            "error": error,
            "admin_configured": admin_password_configured(),
        },
        status_code=status_code,
    )


def _index_context(
    request: Request,
    *,
    q=None,
    job=None,
    branch=None,
    result=None,
    dateFrom=None,
    dateTo=None,
    page=1,
    page_size=DEFAULT_PAGE_SIZE,
    flash=None,
    error=None,
    apply_today_default: bool = True,
):
    page_size = clamp_page_size(page_size)
    used_default_today = False
    if apply_today_default:
        dateFrom, dateTo, used_default_today = apply_default_today_dates(
            request.query_params, dateFrom, dateTo
        )
    with get_db() as db:
        rows, total, page, page_size = search_builds(
            db,
            q=q,
            job=job,
            branch=branch,
            result=result,
            date_from=dateFrom,
            date_to=dateTo,
            page=page,
            page_size=page_size,
        )
        jobs = load_job_filter_options(db)
        results = load_result_filter_options(db)
        stats_data = load_global_stats(db)
        retention = load_retention_config(db)

    total_pages = max(1, (total + page_size - 1) // page_size) if total else 1
    total_pages_capped = min(total_pages, MAX_PAGE)
    deep_page_capped = total_pages > MAX_PAGE
    today = local_today_iso()
    # Visual “当日” when range is exactly local today (default or user-selected).
    is_today_range = bool(dateFrom and dateTo and dateFrom == dateTo == today)
    return {
        "request": request,
        "rows": rows,
        "jobs": jobs,
        "job_dropdown_limit": JOB_DROPDOWN_LIMIT,
        "job_dropdown_capped": stats_data["jobs"] > JOB_DROPDOWN_LIMIT,
        "results": results,
        "stats": stats_data,
        "total": total,
        "page": page,
        "page_size": page_size,
        "page_sizes": ALLOWED_PAGE_SIZES,
        "total_pages": total_pages_capped,
        "total_pages_real": total_pages,
        "deep_page_capped": deep_page_capped,
        "q": q or "",
        "job": job or "",
        "branch": branch or "",
        "result": result or "",
        "dateFrom": dateFrom or "",
        "dateTo": dateTo or "",
        "filter_default_today": used_default_today,
        "is_today_range": is_today_range,
        "today": today,
        "flash": flash,
        "error": error,
        "admin_configured": admin_password_configured(),
        "retention": retention,
    }


@app.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    q: Optional[str] = None,
    job: Optional[str] = None,
    branch: Optional[str] = None,
    result: Optional[str] = None,
    dateFrom: Optional[str] = None,
    dateTo: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=100),
):
    raw_flash = request.cookies.get(FLASH_COOKIE)
    flash = unquote(raw_flash) if raw_flash else None
    response = templates.TemplateResponse(
        "index.html",
        _index_context(
            request,
            q=q,
            job=job,
            branch=branch,
            result=result,
            dateFrom=dateFrom,
            dateTo=dateTo,
            page=page,
            page_size=pageSize,
            flash=flash,
        ),
    )
    if raw_flash:
        response.delete_cookie(FLASH_COOKIE, path="/")
    return response


@app.get("/build/{record_id}", response_class=HTMLResponse)
def build_detail(request: Request, record_id: int):
    row = _fetch_build_row(record_id)
    if not row:
        raise HTTPException(status_code=404, detail="Build not found")
    return _detail_response(request, row)


@app.post("/build/{record_id}/delete", response_class=HTMLResponse)
def ui_delete_build(
    request: Request,
    record_id: int,
    password: str = Form(default=""),
    confirm: str = Form(default=""),
):
    """Admin UI single delete — uses ADMIN_PASSWORD (not API_TOKEN)."""
    row = _fetch_build_row(record_id)
    if not row:
        raise HTTPException(status_code=404, detail="Build not found")

    if (confirm or "").strip() != "DELETE":
        return _detail_response(
            request,
            row,
            error="请在确认框中输入 DELETE（全大写）后再删除。",
            status_code=400,
        )

    err = check_admin_password(password)
    if err == "ADMIN_PASSWORD is not configured":
        return _detail_response(
            request,
            row,
            error="服务端未配置管理密码（ADMIN_PASSWORD），无法删除。",
            status_code=503,
        )
    if err:
        return _detail_response(
            request,
            row,
            error="管理密码错误，删除已取消。",
            status_code=401,
        )

    with get_db() as db:
        db.execute("DELETE FROM build_records WHERE id=?", (record_id,))

    msg = f"已删除构建记录：{row['job_name']} #{row['build_id']}"
    return set_flash_redirect("/", msg)


@app.post("/builds/batch-delete", response_class=HTMLResponse)
async def ui_batch_delete(
    request: Request,
    password: str = Form(default=""),
    confirm: str = Form(default=""),
):
    """Batch delete selected build records from the list page."""
    form = await request.form()
    ids = _parse_id_list(form.getlist("ids"))

    def fail(error: str, status_code: int = 400):
        return templates.TemplateResponse(
            "index.html",
            _index_context(request, error=error),
            status_code=status_code,
        )

    if not ids:
        return fail("请先勾选要删除的构建记录。", 400)

    if (confirm or "").strip() != "DELETE":
        return fail("请在确认框中输入 DELETE（全大写）后再批量删除。", 400)

    err = check_admin_password(password)
    if err == "ADMIN_PASSWORD is not configured":
        return fail("服务端未配置管理密码（ADMIN_PASSWORD），无法删除。", 503)
    if err:
        return fail("管理密码错误，批量删除已取消。", 401)

    placeholders = ",".join("?" * len(ids))
    with get_db() as db:
        cursor = db.execute(
            f"DELETE FROM build_records WHERE id IN ({placeholders})",
            ids,
        )
        deleted = cursor.rowcount if cursor.rowcount is not None else 0

    return set_flash_redirect("/", f"已批量删除 {deleted} 条构建记录")


@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    with get_db() as db:
        cfg = load_retention_config(db)
    raw_flash = request.cookies.get(FLASH_COOKIE)
    flash = unquote(raw_flash) if raw_flash else None
    response = templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "admin_configured": admin_password_configured(),
            "retention": cfg,
            "flash": flash,
            "error": None,
        },
    )
    if raw_flash:
        response.delete_cookie(FLASH_COOKIE, path="/")
    return response


@app.post("/admin/retention", response_class=HTMLResponse)
def admin_save_retention(
    request: Request,
    password: str = Form(default=""),
    retention_days: str = Form(default="0"),
    retention_max_per_job: str = Form(default="0"),
    action: str = Form(default="save"),
):
    def render(error=None, flash=None, cfg=None, status_code=200):
        if cfg is None:
            with get_db() as db:
                cfg = load_retention_config(db)
        return templates.TemplateResponse(
            "admin.html",
            {
                "request": request,
                "admin_configured": admin_password_configured(),
                "retention": cfg,
                "flash": flash,
                "error": error,
            },
            status_code=status_code,
        )

    err = check_admin_password(password)
    if err == "ADMIN_PASSWORD is not configured":
        return render("服务端未配置管理密码（ADMIN_PASSWORD）。", status_code=503)
    if err:
        return render("管理密码错误。", status_code=401)

    try:
        days = max(0, int(str(retention_days).strip() or "0"))
        max_per_job = max(0, int(str(retention_max_per_job).strip() or "0"))
    except ValueError:
        return render("保留天数与每 Job 上限必须是非负整数。", status_code=400)

    if days > 36500:
        return render("最长保留期限不能超过 36500 天。", status_code=400)
    if max_per_job > 1_000_000:
        return render("每 Job 最大条数过大。", status_code=400)

    with get_db() as db:
        cfg = save_retention_config(
            db, days=days, max_per_job=max_per_job, updated_at=utc_now_iso()
        )
        if action == "save_and_run":
            result = apply_retention(db, cfg)
            return set_flash_redirect(
                "/admin",
                f"保留策略已执行，清理 {result['deletedTotal']} 条记录。",
            )

    return set_flash_redirect("/admin", "保留策略已保存。")
