from __future__ import annotations

import sqlite3
import hashlib
import json
import re
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
        CREATE TABLE IF NOT EXISTS topics(
          id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
          aliases TEXT NOT NULL DEFAULT '[]', created_at REAL NOT NULL, updated_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS thread_topics(
          thread_id TEXT NOT NULL, topic_id TEXT NOT NULL, score REAL NOT NULL DEFAULT 1,
          source TEXT NOT NULL DEFAULT 'auto', updated_at REAL NOT NULL,
          PRIMARY KEY(thread_id, topic_id), FOREIGN KEY(thread_id) REFERENCES threads(id) ON DELETE CASCADE,
          FOREIGN KEY(topic_id) REFERENCES topics(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS app_state(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events(
          id INTEGER PRIMARY KEY, event_key TEXT NOT NULL UNIQUE, kind TEXT NOT NULL,
          payload TEXT NOT NULL, created_at REAL NOT NULL, processed_at REAL
        );
        CREATE TABLE IF NOT EXISTS outbox(
          id INTEGER PRIMARY KEY, event_key TEXT NOT NULL UNIQUE, kind TEXT NOT NULL,
          payload TEXT NOT NULL, created_at REAL NOT NULL, processed_at REAL
        );
        """)
        self._migrate()
        self.db.commit()

    def _migrate(self) -> None:
        """Small, repeatable migrations; never rebuilds or drops user history."""
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(messages)")}
        if "upstream_id" not in columns:
            self.db.execute("ALTER TABLE messages ADD COLUMN upstream_id TEXT")
        self.db.execute("CREATE UNIQUE INDEX IF NOT EXISTS messages_upstream_idx ON messages(upstream_id) WHERE upstream_id IS NOT NULL")
        thread_columns = {row[1] for row in self.db.execute("PRAGMA table_info(threads)")}
        if "available" not in thread_columns:
            self.db.execute("ALTER TABLE threads ADD COLUMN available INTEGER NOT NULL DEFAULT 1")
        self.db.execute("PRAGMA user_version=2")

    def project(self, project_id: str, description: str = "", root: str | None = None) -> None:
        self.db.execute("INSERT OR IGNORE INTO projects VALUES(?,?,?,?,?)", (project_id, project_id, description, root, time.time()))
        self.db.commit()

    def thread(self, thread_id: str, project_id: str, title: str = "", source: str = "codex") -> None:
        self.project(project_id)
        self.db.execute("INSERT INTO threads(id,title,project_id,source,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at,title=COALESCE(NULLIF(excluded.title,''),threads.title)", (thread_id, title, project_id, source, time.time()))
        self.db.commit()

    def sync_thread(self, thread_id: str, project_id: str, title: str = "", source: str = "codex") -> None:
        """Upsert remote metadata without making every sync look like activity."""
        self.project(project_id)
        self.db.execute("INSERT INTO threads(id,title,project_id,source,updated_at,available) VALUES(?,?,?,?,?,1) ON CONFLICT(id) DO UPDATE SET title=COALESCE(NULLIF(excluded.title,''),threads.title),source=excluded.source,available=1", (thread_id, title, project_id, source, time.time()))
        self.db.commit()

    def message(self, thread_id: str, turn_id: str | None, role: str, text: str, upstream_id: str | None = None) -> int:
        if upstream_id:
            existing = self.db.execute("SELECT id FROM messages WHERE upstream_id=?", (upstream_id,)).fetchone()
            if existing:
                return int(existing[0])
        cur = self.db.execute("INSERT INTO messages(thread_id,turn_id,role,text,created_at,upstream_id) VALUES(?,?,?,?,?,?)", (thread_id, turn_id, role, text, time.time(), upstream_id))
        self.db.execute("UPDATE threads SET updated_at=? WHERE id=?", (time.time(), thread_id))
        self.db.commit()
        self.enqueue("message", {"id": cur.lastrowid, "thread_id": thread_id, "role": role, "text": text}, f"message:{cur.lastrowid}")
        return int(cur.lastrowid)

    def set_state(self, key: str, value: str) -> None:
        self.db.execute("INSERT INTO app_state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
        self.db.commit()

    def get_state(self, key: str, default: str | None = None) -> str | None:
        row = self.db.execute("SELECT value FROM app_state WHERE key=?", (key,)).fetchone()
        return str(row[0]) if row else default

    def topic(self, topic_id: str, name: str, description: str = "", aliases: list[str] | None = None) -> None:
        now = time.time()
        self.db.execute("INSERT INTO topics(id,name,description,aliases,created_at,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,description=CASE WHEN excluded.description='' THEN topics.description ELSE excluded.description END,aliases=CASE WHEN excluded.aliases='[]' THEN topics.aliases ELSE excluded.aliases END,updated_at=excluded.updated_at", (topic_id, name, description, json.dumps(aliases or [], ensure_ascii=False), now, now))
        self.db.commit()

    def attach_topic(self, thread_id: str, topic_id: str, score: float = 1.0, source: str = "auto") -> None:
        self.db.execute("INSERT INTO thread_topics(thread_id,topic_id,score,source,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(thread_id,topic_id) DO UPDATE SET score=MAX(thread_topics.score,excluded.score),source=excluded.source,updated_at=excluded.updated_at", (thread_id, topic_id, score, source, time.time()))
        self.db.commit()

    def topic_for_thread(self, thread_id: str) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT t.*,tt.score,tt.source FROM topics t JOIN thread_topics tt ON tt.topic_id=t.id WHERE tt.thread_id=? ORDER BY tt.score DESC", (thread_id,))]

    def list_topics(self) -> list[dict]:
        rows = self.db.execute("SELECT t.id,t.name,t.description,t.aliases,t.updated_at,COUNT(tt.thread_id) AS thread_count FROM topics t LEFT JOIN thread_topics tt ON tt.topic_id=t.id GROUP BY t.id ORDER BY t.updated_at DESC").fetchall()
        return [dict(r) for r in rows]

    def list_threads(self, term: str = "", limit: int = 50) -> list[dict]:
        if term.strip():
            return self.search_threads(term, limit)
        rows = self.db.execute("SELECT * FROM threads ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]

    def add_alias(self, topic_id: str, alias: str) -> None:
        row = self.db.execute("SELECT aliases FROM topics WHERE id=?", (topic_id,)).fetchone()
        if not row: raise KeyError(topic_id)
        aliases = json.loads(row[0]); normalized = alias.strip().lower()
        if normalized and normalized not in aliases: aliases.append(normalized)
        self.db.execute("UPDATE topics SET aliases=?,updated_at=? WHERE id=?", (json.dumps(aliases, ensure_ascii=False), time.time(), topic_id)); self.db.commit()

    def route(self, text: str, project_id: str, active_thread: str | None = None) -> dict:
        """Deterministic, local route. Scores are ranking signals, never probabilities."""
        lowered = text.casefold()
        explicit_switch = bool(re.match(
            r"\s*(?:por favor[, ]+)?(?:retoma\s+lo de|(?:cambia (?:a|al)|abre|continúa en|sigue en)\s+(?:(?:el|la)\s+)?(?:chat|conversaci[oó]n|tema|proyecto)\b|cambia (?:a|al)\s+)",
            lowered,
        ))
        explicit_continue = any(x in lowered for x in ("sigue aquí", "sigue aqui", "continuemos aquí", "continuemos aqui"))
        topics = self.list_topics()
        candidates = []
        for topic in topics:
            aliases = [topic["name"].casefold(), *json.loads(topic["aliases"] or "[]")]
            alias_hit = max((len(a) for a in aliases if a and re.search(r"(?<!\w)" + re.escape(a) + r"(?!\w)", lowered)), default=0)
            if not alias_hit:
                # Legacy threads often have no title. A distinctive token from
                # their generated topic label still gives a cheap local anchor.
                query_words = set(re.findall(r"[\wáéíóúüñ-]{4,}", lowered))
                topic_words = {w for a in aliases for w in re.findall(r"[\wáéíóúüñ-]{4,}", a)}
                if query_words & topic_words:
                    alias_hit = max(len(w) for w in query_words & topic_words)
            if not alias_hit:
                continue
            threads = self.db.execute("SELECT tt.thread_id,tt.score,t.updated_at,t.title,t.project_id FROM thread_topics tt JOIN threads t ON t.id=tt.thread_id WHERE tt.topic_id=? AND t.available=1 AND t.source='codex' AND t.id!='local-exec' ORDER BY t.updated_at DESC LIMIT 3", (topic["id"],)).fetchall()
            for thread in threads:
                score = (2.0 if active_thread == thread[0] and explicit_continue else 0) + min(alias_hit / 10, 1.0) + float(thread[1]) * .1
                candidates.append({"thread_id": thread[0], "topic_id": topic["id"], "topic": topic["name"], "title": thread[3], "project_id": thread[4], "score": score, "alias_hit": alias_hit})
        matched_projects = {candidate["project_id"] for candidate in candidates}
        if len(lowered.split()) >= 2:
            for row in self.db.execute("SELECT id,name,root FROM projects WHERE root IS NOT NULL AND id!=?", (project_id,)):
                if row["id"] in matched_projects:
                    continue
                if len(row["name"]) >= 3 and re.search(r"(?<!\w)" + re.escape(row["name"].casefold()) + r"(?!\w)", lowered):
                    candidates.append({"thread_id": None, "topic": row["name"], "project_id": row["id"],
                                       "root": row["root"], "score": .8, "alias_hit": len(row["name"])})
        try:
            terms = " OR ".join("\"" + p.replace('"',' ') + "\"" for p in lowered.split() if len(p) > 2) or '""'
            rows = self.db.execute("SELECT m.thread_id,COUNT(*) AS hits,MAX(t.updated_at) AS updated_at,t.title FROM messages_fts f JOIN messages m ON m.id=f.rowid JOIN threads t ON t.id=m.thread_id WHERE t.project_id=? AND t.available=1 AND t.id!='local-exec' AND messages_fts MATCH ? GROUP BY m.thread_id ORDER BY hits DESC,updated_at DESC LIMIT 8", (project_id, terms)).fetchall()
            for row in rows:
                candidates.append({"thread_id": row[0], "topic_id": None, "topic": "", "title": row[3], "score": min(float(row[1]) * .12, .9), "alias_hit": 0})
        except sqlite3.Error:
            pass
        dedup = {}
        for candidate in candidates:
            key = (candidate["thread_id"], candidate.get("project_id") if not candidate["thread_id"] else None)
            if key not in dedup or candidate["score"] > dedup[key]["score"]:
                dedup[key] = candidate
        ordered = sorted(dedup.values(), key=lambda x: (x["score"], x["thread_id"] == active_thread), reverse=True)
        best = ordered[0] if ordered else None
        second = ordered[1] if len(ordered) > 1 else None
        confident = bool(best and best["alias_hit"] >= 3 and (not second or best["score"] - second["score"] >= .08))
        if explicit_continue and active_thread:
            return {"action": "continue", "thread_id": active_thread, "confidence": 1.0, "candidates": ordered[:2]}
        if active_thread and not explicit_switch:
            suggestion = best if confident and best["thread_id"] != active_thread else None
            return {"action": "continue", "thread_id": active_thread, "suggestion": suggestion, "candidates": ordered[:2]}
        if explicit_switch:
            return {"action": ("continue" if best["thread_id"] else "workspace") if confident else "clarify",
                    "thread_id": best["thread_id"] if confident else None,
                    "destination": best if confident else None, "candidates": ordered[:2]}
        return {"action": "new", "thread_id": None, "candidates": ordered[:2]}

    def enqueue(self, kind: str, payload: dict, event_key: str | None = None) -> None:
        event_key = event_key or hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        self.db.execute("INSERT OR IGNORE INTO outbox(event_key,kind,payload,created_at) VALUES(?,?,?,?)", (event_key, kind, json.dumps(payload, ensure_ascii=False), time.time()))
        self.db.commit()

    def pending_events(self, limit: int = 100) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM outbox WHERE processed_at IS NULL ORDER BY id LIMIT ?", (limit,))]

    def mark_event(self, event_id: int) -> None:
        self.db.execute("UPDATE outbox SET processed_at=? WHERE id=?", (time.time(), event_id)); self.db.commit()

    def graph_rows(self) -> dict:
        nodes, edges = [], []
        for row in self.db.execute("SELECT id,name,description FROM topics"):
            nodes.append({"id": f"topic:{row[0]}", "label": row[1], "type": "topic", "description": row[2]})
        for row in self.db.execute("SELECT id,title,project_id,updated_at FROM threads"):
            nodes.append({"id": f"thread:{row[0]}", "label": row[1] or row[0][:12], "type": "conversation", "updated_at": row[3]})
        for row in self.db.execute("SELECT id,thread_id,role,text,created_at FROM messages ORDER BY id"):
            nodes.append({"id": f"message:{row[0]}", "label": row[3][:180], "type": "message", "role": row[2], "created_at": row[4]})
            edges.append({"source": f"thread:{row[1]}", "target": f"message:{row[0]}", "type": "contains", "provenance": "sqlite"})
        for row in self.db.execute("SELECT thread_id,topic_id,score FROM thread_topics"):
            edges.append({"source": f"topic:{row[1]}", "target": f"thread:{row[0]}", "type": "contains", "weight": row[2], "provenance": "sqlite"})
        return {"nodes": nodes, "edges": edges, "generated_at": time.time(), "schema": "voz-codex.graph.v1"}

    def search_threads(self, term: str, limit: int = 20) -> list[dict]:
        rows = self.db.execute("SELECT DISTINCT t.* FROM threads t JOIN messages m ON m.thread_id=t.id JOIN messages_fts f ON f.rowid=m.id WHERE messages_fts MATCH ? ORDER BY t.updated_at DESC LIMIT ?", (term.replace('"', ' '), limit)).fetchall()
        return [dict(row) for row in rows]

    def search_context(self, project_id: str, term: str, limit: int = 6) -> list[dict]:
        rows = self.db.execute("SELECT c.text,c.locator,s.path,s.description FROM chunks c JOIN chunks_fts f ON f.rowid=c.id JOIN sources s ON s.id=c.source_id WHERE s.project_id=? AND chunks_fts MATCH ? ORDER BY bm25(chunks_fts) LIMIT ?", (project_id, term.replace('"', ' '), limit)).fetchall()
        return [dict(row) for row in rows]
