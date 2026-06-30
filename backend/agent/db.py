"""
Agent 会话持久化 — SQLite 存储
"""
import json
import sqlite3
from datetime import datetime
from typing import Optional

from config import AGENT_DB_PATH

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS agent_sessions (
    session_id TEXT PRIMARY KEY,
    messages JSON NOT NULL,
    context JSON NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def _conn():
    conn = sqlite3.connect(AGENT_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = _conn()
    try:
        conn.execute(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()


def save_session(session_id: str, messages: list, context: dict,
                 status: str = "running") -> None:
    now = datetime.now().isoformat()
    conn = _conn()
    try:
        conn.execute(
            """INSERT OR REPLACE INTO agent_sessions
               (session_id, messages, context, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, COALESCE(
                   (SELECT created_at FROM agent_sessions WHERE session_id = ?),
                   ?
               ), ?)""",
            (
                session_id,
                json.dumps(messages, ensure_ascii=False),
                json.dumps(context, ensure_ascii=False),
                status,
                session_id,
                now,
                now,
            )
        )
        conn.commit()
    finally:
        conn.close()


def load_session(session_id: str) -> Optional[dict]:
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT * FROM agent_sessions WHERE session_id = ?",
            (session_id,)
        ).fetchone()
        if row is None:
            return None
        return {
            "session_id": row["session_id"],
            "messages": json.loads(row["messages"]),
            "context": json.loads(row["context"]),
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
    finally:
        conn.close()


def load_all_sessions(max_count: int = 50) -> list:
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT * FROM agent_sessions ORDER BY updated_at DESC LIMIT ?",
            (max_count,)
        ).fetchall()
        result = []
        for row in rows:
            result.append({
                "session_id": row["session_id"],
                "messages": json.loads(row["messages"]),
                "context": json.loads(row["context"]),
                "status": row["status"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            })
        return result
    finally:
        conn.close()


def delete_session(session_id: str) -> None:
    conn = _conn()
    try:
        conn.execute("DELETE FROM agent_sessions WHERE session_id = ?", (session_id,))
        conn.commit()
    finally:
        conn.close()


def cleanup_old_sessions(keep_count: int = 50) -> None:
    conn = _conn()
    try:
        conn.execute(
            """DELETE FROM agent_sessions WHERE session_id NOT IN (
                SELECT session_id FROM agent_sessions
                ORDER BY updated_at DESC LIMIT ?
            )""",
            (keep_count,)
        )
        conn.commit()
    finally:
        conn.close()
