"""SQLite storage with FTS5 for session/handoff indexing and text search."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from briefbridge.models.handoff import HandoffPack

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    started_at TEXT,
    ended_at TEXT,
    repo_path TEXT,
    repo_name TEXT,
    branch TEXT,
    title TEXT,
    source_path TEXT,
    files_touched TEXT,
    parsed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS handoffs (
    handoff_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    created_at TEXT NOT NULL,
    pack_json TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS handoffs_fts USING fts5(
    session_id,
    title,
    objective,
    errors,
    commands,
    files,
    decisions,
    pending,
    content='handoffs_fts_content'
);

CREATE TABLE IF NOT EXISTS handoffs_fts_content (
    rowid INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    title TEXT,
    objective TEXT,
    errors TEXT,
    commands TEXT,
    files TEXT,
    decisions TEXT,
    pending TEXT
);
"""


@dataclass
class SessionSummary:
    id: str
    provider: str
    started_at: str | None
    ended_at: str | None
    repo_path: str | None
    repo_name: str | None
    branch: str | None
    title: str | None
    files_touched: list[str]


@dataclass
class SearchResult:
    session_id: str
    title: str
    snippet: str
    rank: float


class StorageBackend:
    def __init__(self, db_path: Path | str = ":memory:") -> None:
        self.db_path = str(db_path)
        self._conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._init_schema()
        return self._conn

    def _init_schema(self) -> None:
        cur = self.conn.cursor()
        for statement in _SCHEMA.split(";"):
            statement = statement.strip()
            if statement:
                cur.execute(statement)
        self.conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------

    def upsert_session(
        self,
        *,
        id: str,
        provider: str,
        started_at: datetime | None = None,
        ended_at: datetime | None = None,
        repo_path: str | None = None,
        repo_name: str | None = None,
        branch: str | None = None,
        title: str | None = None,
        source_path: str | None = None,
        files_touched: list[str] | None = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO sessions (id, provider, started_at, ended_at, repo_path,
                                  repo_name, branch, title, source_path, files_touched, parsed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                provider=excluded.provider,
                started_at=excluded.started_at,
                ended_at=excluded.ended_at,
                repo_path=excluded.repo_path,
                repo_name=excluded.repo_name,
                branch=excluded.branch,
                title=excluded.title,
                source_path=excluded.source_path,
                files_touched=excluded.files_touched,
                parsed_at=excluded.parsed_at
            """,
            (
                id,
                provider,
                started_at.isoformat() if started_at else None,
                ended_at.isoformat() if ended_at else None,
                repo_path,
                repo_name,
                branch,
                title,
                source_path,
                json.dumps(files_touched or []),
                datetime.now().isoformat(),
            ),
        )
        self.conn.commit()

    def list_sessions(
        self,
        *,
        last_hours: float | None = None,
        repo: str | None = None,
        branch: str | None = None,
        provider: str | None = None,
    ) -> list[SessionSummary]:
        query = "SELECT * FROM sessions WHERE 1=1"
        params: list = []

        if provider:
            query += " AND provider = ?"
            params.append(provider)
        if repo:
            query += " AND repo_path LIKE ?"
            params.append(f"%{repo}%")
        if branch:
            query += " AND branch LIKE ?"
            params.append(f"%{branch}%")
        if last_hours:
            cutoff = datetime.now().timestamp() - last_hours * 3600
            cutoff_iso = datetime.fromtimestamp(cutoff).isoformat()
            query += " AND started_at >= ?"
            params.append(cutoff_iso)

        query += " ORDER BY started_at DESC"
        rows = self.conn.execute(query, params).fetchall()
        return [
            SessionSummary(
                id=r["id"],
                provider=r["provider"],
                started_at=r["started_at"],
                ended_at=r["ended_at"],
                repo_path=r["repo_path"],
                repo_name=r["repo_name"],
                branch=r["branch"],
                title=r["title"],
                files_touched=json.loads(r["files_touched"]) if r["files_touched"] else [],
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Handoffs
    # ------------------------------------------------------------------

    def upsert_handoff(self, pack: HandoffPack) -> None:
        pack_json = pack.model_dump_json()

        self.conn.execute(
            """
            INSERT INTO handoffs (handoff_id, session_id, provider, created_at, pack_json)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(handoff_id) DO UPDATE SET
                pack_json=excluded.pack_json,
                created_at=excluded.created_at
            """,
            (
                pack.handoff_id,
                pack.source_session_id,
                pack.source_provider,
                pack.created_at.isoformat(),
                pack_json,
            ),
        )

        # Update FTS
        errors_text = " | ".join(e.summary for e in pack.errors_found)
        commands_text = " | ".join(c.command for c in pack.important_commands)
        files_text = " | ".join(f.path for f in pack.relevant_files)
        decisions_text = " | ".join(d.text for d in pack.decisions_made)
        pending_text = " | ".join(p.text for p in pack.pending_items)

        self.conn.execute(
            """
            INSERT INTO handoffs_fts_content
                (session_id, title, objective, errors, commands, files, decisions, pending)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pack.source_session_id,
                pack.title or "",
                pack.objective or "",
                errors_text,
                commands_text,
                files_text,
                decisions_text,
                pending_text,
            ),
        )

        # Sync FTS index
        rowid = self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        self.conn.execute(
            """
            INSERT INTO handoffs_fts (rowid, session_id, title, objective, errors, commands, files, decisions, pending)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rowid,
                pack.source_session_id,
                pack.title or "",
                pack.objective or "",
                errors_text,
                commands_text,
                files_text,
                decisions_text,
                pending_text,
            ),
        )

        self.conn.commit()

    def get_handoff(self, session_id: str) -> HandoffPack | None:
        row = self.conn.execute(
            "SELECT pack_json FROM handoffs WHERE session_id = ? ORDER BY created_at DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        if row:
            return HandoffPack.model_validate_json(row["pack_json"])
        return None

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, query: str, limit: int = 20) -> list[SearchResult]:
        rows = self.conn.execute(
            """
            SELECT session_id, title, snippet(handoffs_fts, 2, '<b>', '</b>', '...', 32) as snippet,
                   rank
            FROM handoffs_fts
            WHERE handoffs_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (query, limit),
        ).fetchall()
        return [
            SearchResult(
                session_id=r["session_id"],
                title=r["title"],
                snippet=r["snippet"],
                rank=r["rank"],
            )
            for r in rows
        ]
