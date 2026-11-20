from __future__ import annotations

import sqlite3
import time
from pathlib import Path


class History:
    def __init__(self, path: Path):
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS projects(
          id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', root TEXT,
          created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS threads(
          id TEXT PRIMARY KEY, title TEXT NOT NULL DEFAULT '', project_id TEXT NOT NULL,
          source TEXT NOT NULL DEFAULT 'codex', updated_at REAL NOT NULL,
          FOREIGN KEY(project_id) REFERENCES projects(id)
        );
        CREATE TABLE IF NOT EXISTS messages(
          id INTEGER PRIMARY KEY, thread_id TEXT NOT NULL, turn_id TEXT, role TEXT NOT NULL,
          text TEXT NOT NULL, created_at REAL NOT NULL, FOREIGN KEY(thread_id) REFERENCES threads(id)
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(text, content=messages, content_rowid=id);
        CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
          INSERT INTO messages_fts(rowid,text) VALUES(new.id,new.text);
        END;
        CREATE TABLE IF NOT EXISTS sources(
          id TEXT PRIMARY KEY, project_id TEXT NOT NULL, kind TEXT NOT NULL, path TEXT NOT NULL,
          description TEXT NOT NULL DEFAULT '', fingerprint TEXT, updated_at REAL,
          FOREIGN KEY(project_id) REFERENCES projects(id)
        );
        CREATE TABLE IF NOT EXISTS chunks(
          id INTEGER PRIMARY KEY, source_id TEXT NOT NULL, locator TEXT NOT NULL,
          text TEXT NOT NULL, fingerprint TEXT NOT NULL, updated_at REAL NOT NULL,
          FOREIGN KEY(source_id) REFERENCES sources(id) ON DELETE CASCADE
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(text, content=chunks, content_rowid=id);
        CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
          INSERT INTO chunks_fts(rowid,text) VALUES(new.id,new.text);
        END;
        """)
        self.db.commit()

    def project(self, project_id: str, description: str = "", root: str | None = None) -> None:
        self.db.execute("INSERT OR IGNORE INTO projects VALUES(?,?,?,?,?)", (project_id, project_id, description, root, time.time()))
        self.db.commit()

    def thread(self, thread_id: str, project_id: str, title: str = "", source: str = "codex") -> None:
        self.project(project_id)
        self.db.execute("INSERT INTO threads(id,title,project_id,source,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at,title=COALESCE(NULLIF(excluded.title,''),threads.title)", (thread_id, title, project_id, source, time.time()))
        self.db.commit()

    def message(self, thread_id: str, turn_id: str | None, role: str, text: str) -> None:
        self.db.execute("INSERT INTO messages(thread_id,turn_id,role,text,created_at) VALUES(?,?,?,?,?)", (thread_id, turn_id, role, text, time.time()))
        self.db.execute("UPDATE threads SET updated_at=? WHERE id=?", (time.time(), thread_id))
        self.db.commit()

    def search_threads(self, term: str, limit: int = 20) -> list[dict]:
        rows = self.db.execute("SELECT DISTINCT t.* FROM threads t JOIN messages m ON m.thread_id=t.id JOIN messages_fts f ON f.rowid=m.id WHERE messages_fts MATCH ? ORDER BY t.updated_at DESC LIMIT ?", (term.replace('"', ' '), limit)).fetchall()
        return [dict(row) for row in rows]

    def search_context(self, project_id: str, term: str, limit: int = 6) -> list[dict]:
        rows = self.db.execute("SELECT c.text,c.locator,s.path,s.description FROM chunks c JOIN chunks_fts f ON f.rowid=c.id JOIN sources s ON s.id=c.source_id WHERE s.project_id=? AND chunks_fts MATCH ? ORDER BY bm25(chunks_fts) LIMIT ?", (project_id, term.replace('"', ' '), limit)).fetchall()
        return [dict(row) for row in rows]
