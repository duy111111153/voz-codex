from pathlib import Path
from voz_codex.history import History


def test_history_search(tmp_path: Path):
    history = History(tmp_path / "db.sqlite")
    history.thread("t1", "p1", "Demo")
    history.message("t1", "turn1", "user", "revisar tareas del proyecto")
    assert history.search_threads("tareas")[0]["id"] == "t1"
