import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from voz_codex.history import History


class ChatRouteTests(unittest.TestCase):
    def test_resume_recommendation_and_explicit_switch(self):
        with TemporaryDirectory() as folder:
            db = History(Path(folder) / "history.sqlite3")
            db.thread("active", "default")
            db.thread("other", "graph")
            db.topic("graphs", "Graphify")
            db.attach_topic("other", "graphs")
            db.message("active", "turn1", "user", "continuidad de la voz")
            db.set_state("active_thread", "active")
            db.db.execute("UPDATE threads SET available=0 WHERE id='active'")
            db.db.commit()
            active = db.get_state("active_thread")
            self.assertEqual(db.route("Hola", "default", active)["thread_id"], "active")
            route = db.route("Revisa Graphify", "default", active)
            self.assertEqual(route["thread_id"], "active")
            self.assertEqual(route["suggestion"]["thread_id"], "other")
            route = db.route("Cambia a Graphify", "default", active)
            self.assertEqual(route["destination"]["thread_id"], "other")
            self.assertEqual(db.search_threads("continuidad")[0]["id"], "active")
            db.project("Fichas", root=folder)
            route = db.route("Revisa Fichas", "default", active)
            self.assertEqual(route["suggestion"]["root"], folder)
            self.assertEqual(db.route("Cambia a Fichas", "default", active)["action"], "workspace")
            db.db.close()
