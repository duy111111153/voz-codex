from __future__ import annotations

import hashlib
from pathlib import Path

from .history import History


TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".rst", ".csv", ".json", ".jsonl", ".py", ".js", ".ts", ".toml", ".yaml", ".yml"}


def refresh(history: History, project_id: str, root: Path, description: str = "") -> int:
    history.project(project_id, description, str(root))
    count = 0
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES or ".git" in path.parts or "node_modules" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        source_id = hashlib.sha256(f"{project_id}:{path}".encode()).hexdigest()[:24]
        fingerprint = hashlib.sha256(text.encode()).hexdigest()
        history.db.execute("INSERT INTO sources(id,project_id,kind,path,description,fingerprint,updated_at) VALUES(?,?,?,?,?,?,strftime('%s','now')) ON CONFLICT(id) DO UPDATE SET fingerprint=excluded.fingerprint,updated_at=excluded.updated_at", (source_id, project_id, "file", str(path), "", fingerprint))
        history.db.execute("DELETE FROM chunks WHERE source_id=?", (source_id,))
        chunks = [text[i:i + 1600] for i in range(0, len(text), 1440)] or [""]
        for index, chunk in enumerate(chunks):
            history.db.execute("INSERT INTO chunks(source_id,locator,text,fingerprint,updated_at) VALUES(?,?,?,?,strftime('%s','now'))", (source_id, f"{path}:{index + 1}", chunk, hashlib.sha256(chunk.encode()).hexdigest()))
            count += 1
    history.db.commit()
    return count
