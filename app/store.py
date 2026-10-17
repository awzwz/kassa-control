"""Очередь задач и результаты в одном файле SQLite.

Почему SQLite, а не Redis: задач будет десятки, файл переживает перезапуск, его можно
открыть и посмотреть глазами. Несколько обработчиков берут задачи атомарно через
BEGIN IMMEDIATE, поэтому одну задачу не возьмут двое.
"""
import json
import secrets
import sqlite3
import time
from typing import Any

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id            TEXT PRIMARY KEY,
    status        TEXT NOT NULL,            -- queued | processing | done | failed
    filename      TEXT NOT NULL,
    path          TEXT,                     -- путь к видео; NULL после обработки (файл удалён)
    size_bytes    INTEGER NOT NULL,
    priority      INTEGER NOT NULL DEFAULT 0,
    created_at    REAL NOT NULL,
    started_at    REAL,
    finished_at   REAL,
    attempts      INTEGER NOT NULL DEFAULT 0,
    worker        TEXT,
    progress_json TEXT,                     -- ход анализа для интерфейса
    result_json   TEXT,                     -- ответ строго по §10 кейса
    details_json  TEXT,                     -- дополнительные данные для интерфейса и PDF
    error         TEXT
);
CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status, priority DESC, created_at);
"""


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(config.DB_PATH, timeout=10, isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA busy_timeout=10000")
    c.execute("PRAGMA synchronous=NORMAL")
    return c


def init() -> None:
    """Создаёт папки и таблицу. Режим WAL хранится в самом файле, поэтому включаем его один раз.
    Несколько процессов могут стартовать одновременно, поэтому при блокировке пробуем ещё раз."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    for attempt in range(20):
        try:
            with _conn() as c:
                c.execute("PRAGMA journal_mode=WAL")
                c.executescript(SCHEMA)
            return
        except sqlite3.OperationalError:
            if attempt == 19:
                raise
            time.sleep(0.25 + 0.1 * attempt)


def new_job_id() -> str:
    """Короткий идентификатор как в примере кейса: 3f2a9c1e."""
    return secrets.token_hex(4)


def create_job(filename: str, path: str, size_bytes: int, priority: int = 0) -> str:
    with _conn() as c:
        for _ in range(5):
            job_id = new_job_id()
            try:
                c.execute(
                    "INSERT INTO jobs (id, status, filename, path, size_bytes, priority, created_at) "
                    "VALUES (?, 'queued', ?, ?, ?, ?, ?)",
                    (job_id, filename, path, size_bytes, priority, time.time()),
                )
                return job_id
            except sqlite3.IntegrityError:
                continue
    raise RuntimeError("не удалось выдать уникальный job_id")


def claim_job(worker: str) -> dict[str, Any] | None:
    """Берёт одну задачу из очереди. Атомарно: двое обработчиков не возьмут одну и ту же."""
    with _conn() as c:
        c.execute("BEGIN IMMEDIATE")
        try:
            row = c.execute(
                "SELECT * FROM jobs WHERE status='queued' ORDER BY priority DESC, created_at LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            c.execute(
                "UPDATE jobs SET status='processing', started_at=?, worker=?, attempts=attempts+1 WHERE id=?",
                (time.time(), worker, row["id"]),
            )
            return dict(row)
        finally:
            c.execute("COMMIT")


def set_progress(job_id: str, progress: dict[str, Any]) -> None:
    with _conn() as c:
        c.execute("UPDATE jobs SET progress_json=? WHERE id=?", (json.dumps(progress, ensure_ascii=False), job_id))


def finish_job(job_id: str, result: dict[str, Any], details: dict[str, Any]) -> None:
    with _conn() as c:
        c.execute(
            "UPDATE jobs SET status='done', finished_at=?, path=NULL, result_json=?, details_json=? WHERE id=?",
            (time.time(), json.dumps(result, ensure_ascii=False), json.dumps(details, ensure_ascii=False), job_id),
        )


def fail_job(job_id: str, error: str) -> None:
    with _conn() as c:
        c.execute(
            "UPDATE jobs SET status='failed', finished_at=?, path=NULL, error=? WHERE id=?",
            (time.time(), error, job_id),
        )


def get_job(job_id: str) -> dict[str, Any] | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return dict(row) if row else None


def queue_size() -> int:
    with _conn() as c:
        return c.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','processing')").fetchone()[0]


def requeue_stale(max_age_sec: float) -> int:
    """После перезапуска: задачи, зависшие в processing, возвращаем в очередь (один раз)."""
    cutoff = time.time() - max_age_sec
    with _conn() as c:
        c.execute("BEGIN IMMEDIATE")
        try:
            n = c.execute(
                "UPDATE jobs SET status='queued', started_at=NULL WHERE status='processing' "
                "AND started_at < ? AND attempts < 2 AND path IS NOT NULL",
                (cutoff,),
            ).rowcount
            c.execute(
                "UPDATE jobs SET status='failed', error='обработчик прервался дважды' "
                "WHERE status='processing' AND started_at < ? AND attempts >= 2",
                (cutoff,),
            )
            return n
        finally:
            c.execute("COMMIT")


def purge_old(ttl_hours: float) -> int:
    """Удаляет результаты старше ttl_hours (видео удаляется сразу после обработки, здесь — записи и кадры)."""
    cutoff = time.time() - ttl_hours * 3600
    with _conn() as c:
        return c.execute("DELETE FROM jobs WHERE status IN ('done','failed') AND finished_at < ?", (cutoff,)).rowcount


def list_recent(limit: int = 50) -> list[dict[str, Any]]:
    with _conn() as c:
        rows = c.execute(
            "SELECT id, status, filename, size_bytes, created_at, started_at, finished_at, progress_json, error "
            "FROM jobs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
