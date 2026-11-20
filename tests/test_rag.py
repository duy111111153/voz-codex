from pathlib import Path
from voz_codex.history import History
from voz_codex.rag import refresh


def test_rag_indexes_project(tmp_path: Path):
    root = tmp_path / "project"; root.mkdir(); (root / "README.md").write_text("estado del proyecto voz", encoding="utf-8")
    history = History(tmp_path / "db.sqlite")
    assert refresh(history, "demo", root) == 1
    assert history.search_context("demo", "voz")[0]["path"].endswith("README.md")
