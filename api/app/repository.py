import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator

from .config import settings


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def initialise() -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    with connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
              id TEXT PRIMARY KEY,
              status TEXT NOT NULL,
              audio_path TEXT NOT NULL,
              midi_path TEXT NOT NULL DEFAULT '',
              track_index INTEGER NOT NULL DEFAULT 0,
              error TEXT,
              result_json TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              source_text TEXT NOT NULL DEFAULT '',
              source_kind TEXT NOT NULL DEFAULT 'chords',
              bpm REAL,
              capo INTEGER NOT NULL DEFAULT 0,
              tuning_json TEXT NOT NULL DEFAULT '["E2", "A2", "D3", "G3", "B3", "E4"]',
              reference_url TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS reviews (
              job_id TEXT NOT NULL,
              finding_id TEXT NOT NULL,
              decision TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              PRIMARY KEY (job_id, finding_id)
            );
            """
        )
        _add_column_if_missing(conn, "jobs", "source_text", "TEXT NOT NULL DEFAULT ''")
        _add_column_if_missing(conn, "jobs", "source_kind", "TEXT NOT NULL DEFAULT 'chords'")
        _add_column_if_missing(conn, "jobs", "bpm", "REAL")
        _add_column_if_missing(conn, "jobs", "capo", "INTEGER NOT NULL DEFAULT 0")
        _add_column_if_missing(conn, "jobs", "tuning_json", "TEXT NOT NULL DEFAULT '[\"E2\", \"A2\", \"D3\", \"G3\", \"B3\", \"E4\"]'")
        _add_column_if_missing(conn, "jobs", "reference_url", "TEXT NOT NULL DEFAULT ''")


def _add_column_if_missing(conn: sqlite3.Connection, table: str, name: str, definition: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if name not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(settings.database_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def create_job(
    job_id: str,
    audio_path: Path,
    source_text: str,
    source_kind: str,
    bpm: float | None,
    capo: int,
    tuning: list[str],
    reference_url: str = "",
) -> dict:
    now = utc_now()
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO jobs (
              id, status, audio_path, midi_path, track_index, error, result_json,
              created_at, updated_at, source_text, source_kind, bpm, capo, tuning_json, reference_url
            ) VALUES (?, ?, ?, '', 0, NULL, NULL, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (job_id, "queued", str(audio_path), now, now, source_text, source_kind, bpm, capo, json.dumps(tuning), reference_url),
        )
    return get_job(job_id)


def get_job(job_id: str) -> dict | None:
    with connection() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(row) if row else None


def set_processing(job_id: str) -> None:
    _set_job(job_id, "processing")


def set_complete(job_id: str, result: dict) -> None:
    with connection() as conn:
        conn.execute(
            "UPDATE jobs SET status = ?, result_json = ?, error = NULL, updated_at = ? WHERE id = ?",
            ("complete", json.dumps(result), utc_now(), job_id),
        )


def set_failed(job_id: str, error: str) -> None:
    with connection() as conn:
        conn.execute(
            "UPDATE jobs SET status = ?, error = ?, updated_at = ? WHERE id = ?",
            ("failed", error[:1000], utc_now(), job_id),
        )


def _set_job(job_id: str, status: str) -> None:
    with connection() as conn:
        conn.execute("UPDATE jobs SET status = ?, updated_at = ? WHERE id = ?", (status, utc_now(), job_id))


def save_review(job_id: str, finding_id: str, decision: str) -> None:
    with connection() as conn:
        conn.execute(
            "INSERT INTO reviews VALUES (?, ?, ?, ?) ON CONFLICT(job_id, finding_id) DO UPDATE SET decision=excluded.decision, updated_at=excluded.updated_at",
            (job_id, finding_id, decision, utc_now()),
        )


def reviews_for_job(job_id: str) -> dict[str, str]:
    with connection() as conn:
        rows = conn.execute("SELECT finding_id, decision FROM reviews WHERE job_id = ?", (job_id,)).fetchall()
    return {row["finding_id"]: row["decision"] for row in rows}
