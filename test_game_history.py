import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from docx import Document
import webapp
import DGM01_template


class GameHistoryTests(unittest.TestCase):
    def test_request_data_survives_history_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(webapp, "HISTORY_FILE", Path(tmp) / "history.json"):
            data = {"artifact": "Lezione", "classe": "3", "lesson_topic": "Derivate", "bes_dsa": True}
            webapp.save_prompt_history("prompt", "Gemini", "", [], [], request_data=data)
            self.assertEqual(webapp.load_history()[0]["request_data"], data)

    def test_legacy_history_regenerates_rules_and_survives_save(self):
        prompt = "Tipo di gioco: G01 - Test\nPAR01 (argomento matematico): Equazioni\nPAR02 (numero esercizi): 3"
        entries = [{"id": "old", "prompt": prompt, "response": "", "artifacts": []},
                   {"id": "ordinary", "prompt": "Lezione", "response": "", "artifacts": []}]
        rules = "Direttiva 01 presente una sola volta."
        directives = [{"Gruppo": "DGM01", "Codice": "DGM0101", "Titolo": "Test", "Direttiva completa": rules}]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            history = root / "history.json"
            history.write_text(json.dumps(entries), encoding="utf-8")
            with patch.object(webapp, "HISTORY_FILE", history), patch.object(DGM01_template, "STORE", root), patch.object(webapp, "load_directives", return_value=directives):
                loaded = webapp.load_history()
                self.assertEqual(loaded[0]["artifacts"][0]["artifact_id"], "history-game-old")
                self.assertEqual(loaded[1]["artifacts"], [])
                webapp.save_history(loaded)
                self.assertEqual(len(webapp.load_history()[0]["artifacts"]), 1)
                content, mime, name = webapp.regenerate_history_game("old")
                doc = Document(io.BytesIO(content))
                text = "\n".join(p.text for p in doc.paragraphs)
                self.assertEqual(text.count(rules), 1)
                self.assertIn("Equazioni", text)
                self.assertIn("3", text)
                self.assertEqual(name, "G01-Regolamento.docx")
                with self.assertRaises(ValueError):
                    webapp.regenerate_history_game("missing")
                with self.assertRaises(ValueError):
                    webapp.regenerate_history_game("ordinary")

    def test_new_history_preserves_structured_parameters(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(webapp, "HISTORY_FILE", Path(tmp) / "history.json"):
            params = {"PAR01": "Argomento\nsu due righe", "PAR02": "2"}
            webapp.save_prompt_history("prompt", "Gemini", "", [], [], game_parameters=params)
            entry = webapp.load_history()[0]
            self.assertEqual(webapp.history_game_parameters(entry), params)
            self.assertEqual(entry["artifacts"][0]["formats"], ["docx"])


if __name__ == "__main__":
    unittest.main()
