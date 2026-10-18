"""会话元数据存储 — sqlite3，sessions 表（checkpoint 在 langgraph 的 SqliteSaver）。

会话的节点产物存在 checkpoints.db 由 LangGraph 管理，这里只存轻量索引
id / profile / created / updated / last_stage，供左边栏历史列表与恢复。
"""

from __future__ import annotations

import sqlite3
import time
from typing import Any, Self

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS sessions ("
    " id TEXT PRIMARY KEY,"
    " profile TEXT,"
    " created REAL,"
    " updated REAL,"
    " last_stage TEXT)"
)


class SessionStore:
    def __init__(self, path: str) -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute(_SCHEMA)

    def upsert(self, id: str, profile: str = "", last_stage: str = "") -> None:
        now = time.time()
        self._conn.execute(
            "INSERT INTO sessions(id, profile, created, updated, last_stage)"
            " VALUES(?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET updated=excluded.updated,"
            " last_stage=excluded.last_stage",
            (id, profile, now, now, last_stage),
        )
        self._conn.commit()

    def get(self, id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT id, profile, created, updated, last_stage"
            " FROM sessions WHERE id=?",
            (id,),
        ).fetchone()
        return self._row(row) if row else None

    def list(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT id, profile, created, updated, last_stage"
            " FROM sessions ORDER BY rowid DESC"
        ).fetchall()
        return [self._row(r) for r in rows]

    def delete(self, id: str) -> None:
        self._conn.execute("DELETE FROM sessions WHERE id=?", (id,))
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @staticmethod
    def _row(row: tuple) -> dict[str, Any]:
        return {
            "id": row[0],
            "profile": row[1],
            "created": row[2],
            "updated": row[3],
            "last_stage": row[4],
        }
