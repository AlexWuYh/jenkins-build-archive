"""Build record retention policies."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .db import get_setting, set_setting

SETTING_RETENTION_DAYS = "retention_days"
SETTING_RETENTION_MAX_PER_JOB = "retention_max_per_job"


def _env_int(name: str, default: int = 0) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(0, value)


def _parse_nonneg_int(raw: str | None, default: int) -> int:
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return max(0, int(str(raw).strip()))
    except ValueError:
        return default


@dataclass(frozen=True)
class RetentionConfig:
    days: int
    max_per_job: int
    source: str = "env"  # env | database | mixed

    @property
    def enabled(self) -> bool:
        return self.days > 0 or self.max_per_job > 0


def load_retention_config(db=None) -> RetentionConfig:
    """
    Effective config:
    - If app_settings has a key, use DB value
    - Else fall back to environment (RETENTION_DAYS / RETENTION_MAX_PER_JOB)
    """
    env_days = _env_int("RETENTION_DAYS", 0)
    env_max = _env_int("RETENTION_MAX_PER_JOB", 0)
    days = env_days
    max_per_job = env_max
    has_days = False
    has_max = False

    if db is not None:
        db_days = get_setting(db, SETTING_RETENTION_DAYS)
        db_max = get_setting(db, SETTING_RETENTION_MAX_PER_JOB)
        if db_days is not None:
            days = _parse_nonneg_int(db_days, env_days)
            has_days = True
        if db_max is not None:
            max_per_job = _parse_nonneg_int(db_max, env_max)
            has_max = True

    if has_days and has_max:
        source = "database"
    elif has_days or has_max:
        source = "mixed"
    else:
        source = "env"

    return RetentionConfig(days=days, max_per_job=max_per_job, source=source)


def save_retention_config(
    db, *, days: int, max_per_job: int, updated_at: str
) -> RetentionConfig:
    days = max(0, int(days))
    max_per_job = max(0, int(max_per_job))
    set_setting(db, SETTING_RETENTION_DAYS, str(days), updated_at)
    set_setting(db, SETTING_RETENTION_MAX_PER_JOB, str(max_per_job), updated_at)
    return RetentionConfig(days=days, max_per_job=max_per_job, source="database")


def apply_retention(db, config: RetentionConfig | None = None) -> dict:
    """Apply retention rules. Returns counts of deleted rows per rule."""
    cfg = config or load_retention_config(db)
    deleted_by_days = 0
    deleted_by_max = 0

    if cfg.days > 0:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=cfg.days)).isoformat(
            timespec="seconds"
        )
        cursor = db.execute(
            """
            DELETE FROM build_records
            WHERE build_date < ?
               OR (length(build_date) = 10 AND build_date < date(?))
            """,
            (cutoff, cutoff),
        )
        deleted_by_days = cursor.rowcount if cursor.rowcount is not None else 0

    if cfg.max_per_job > 0:
        cursor = db.execute(
            """
            DELETE FROM build_records
            WHERE id IN (
                SELECT id FROM (
                    SELECT id,
                           ROW_NUMBER() OVER (
                               PARTITION BY job_name
                               ORDER BY build_date DESC, id DESC
                           ) AS rn
                    FROM build_records
                ) ranked
                WHERE rn > ?
            )
            """,
            (cfg.max_per_job,),
        )
        deleted_by_max = cursor.rowcount if cursor.rowcount is not None else 0

    return {
        "enabled": cfg.enabled,
        "retentionDays": cfg.days,
        "retentionMaxPerJob": cfg.max_per_job,
        "source": cfg.source,
        "deletedByDays": deleted_by_days,
        "deletedByMaxPerJob": deleted_by_max,
        "deletedTotal": deleted_by_days + deleted_by_max,
    }
