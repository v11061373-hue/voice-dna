"""会话元数据存储测试 — sessions 表 CRUD。"""

import os
import tempfile

from src.session_store import SessionStore


def test_upsert_and_list():
    with tempfile.TemporaryDirectory() as d, SessionStore(os.path.join(d, "sessions.db")) as s:
        s.upsert("a", profile="美妆博主", last_stage="trend_hunter")
        s.upsert("b", profile="数码测评", last_stage="script_writer")
        rows = s.list()
        assert [r["id"] for r in rows] == ["b", "a"]  # rowid DESC = 最近插入在前
        assert rows[0]["profile"] == "数码测评"
        assert rows[0]["last_stage"] == "script_writer"


def test_upsert_updates_last_stage():
    with tempfile.TemporaryDirectory() as d, SessionStore(os.path.join(d, "sessions.db")) as s:
        s.upsert("a", profile="美妆博主", last_stage="trend_hunter")
        s.upsert("a", last_stage="data_analyst")
        assert len(s.list()) == 1
        assert s.get("a")["last_stage"] == "data_analyst"
        assert s.get("a")["profile"] == "美妆博主"  # profile 不覆盖


def test_get_and_delete():
    with tempfile.TemporaryDirectory() as d, SessionStore(os.path.join(d, "sessions.db")) as s:
        s.upsert("a", profile="美妆博主")
        assert s.get("a")["profile"] == "美妆博主"
        assert s.get("missing") is None
        s.delete("a")
        assert s.get("a") is None
        assert s.list() == []
