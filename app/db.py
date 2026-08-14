import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path


def get_database_path() -> str:
    return os.getenv("DATABASE_PATH", "/data/build_archive.db")


def ensure_database_dir() -> None:
    Path(get_database_path()).parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_db():
    ensure_database_dir()
    # check_same_thread=False not needed for sync request handlers
    conn = sqlite3.connect(get_database_path(), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    # Faster durable writes under WAL; still safe for single-node archive.
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with get_db() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS build_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_name TEXT NOT NULL,
                build_id INTEGER NOT NULL,
                build_date TEXT NOT NULL,
                git_repository TEXT,
                git_branch TEXT,
                git_commit TEXT,
                docker_registry TEXT,
                docker_repository TEXT,
                docker_image_tag TEXT,
                docker_image_digest TEXT,
                build_result TEXT,
                build_url TEXT,
                duration_ms INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(job_name, build_id)
            );

            CREATE INDEX IF NOT EXISTS idx_build_job_date
                ON build_records(job_name, build_date DESC);
            CREATE INDEX IF NOT EXISTS idx_build_branch
                ON build_records(git_branch);
            CREATE INDEX IF NOT EXISTS idx_build_commit
                ON build_records(git_commit);
            CREATE INDEX IF NOT EXISTS idx_build_tag
                ON build_records(docker_image_tag);
            CREATE INDEX IF NOT EXISTS idx_build_digest
                ON build_records(docker_image_digest);
            CREATE INDEX IF NOT EXISTS idx_build_date
                ON build_records(build_date DESC);
            CREATE INDEX IF NOT EXISTS idx_build_result
                ON build_records(build_result);
            CREATE INDEX IF NOT EXISTS idx_build_job_name
                ON build_records(job_name);
            -- Helps list ORDER BY build_date DESC, id DESC
            CREATE INDEX IF NOT EXISTS idx_build_date_id
                ON build_records(build_date DESC, id DESC);

            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )


def get_setting(db, key: str) -> str | None:
    row = db.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else None


def set_setting(db, key: str, value: str, updated_at: str) -> None:
    db.execute(
        """
        INSERT INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value=excluded.value,
            updated_at=excluded.updated_at
        """,
        (key, value, updated_at),
    )
