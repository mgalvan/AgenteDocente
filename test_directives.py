import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import directives_store as store
import webapp


def directive(code="DET99", title="Titolo è <test>"):
    return dict(zip(store.FIELDS, ["DET", code, "TEST", title, "Testo della direttiva"]))


class DirectivesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original = store.DATABASE_FILE
        store.DATABASE_FILE = Path(self.temp.name) / "test.sqlite3"
        store.replace_directives([directive()])

    def tearDown(self):
        store.DATABASE_FILE = self.original
        self.temp.cleanup()

    def test_replacement_validation_and_empty_table(self):
        for invalid in ({}, [dict(directive(), Extra="x")], [{"Codice": "X"}],
                        [directive(), directive()], [dict(directive(), Titolo=None)]):
            with self.assertRaises(ValueError):
                store.replace_directives(invalid)
            self.assertEqual(store.load_directives(), [directive()])
        store.replace_directives([directive("DET98")])
        self.assertEqual(store.load_directives(), [directive("DET98")])
        store.replace_directives([])
        self.assertEqual(store.load_directives(), [])

    def test_failed_insert_rolls_back_deletion(self):
        with closing(sqlite3.connect(store.DATABASE_FILE)) as connection, connection:
            connection.execute("CREATE TRIGGER fail_import BEFORE INSERT ON direttive BEGIN SELECT RAISE(ABORT, 'test'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            store.replace_directives([directive("DET98")])
        self.assertEqual(store.load_directives(), [directive()])

    def test_http_import_and_composition_use_database(self):
        server = webapp.ThreadingHTTPServer(("127.0.0.1", 0), webapp.WebAppHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with urlopen(base + "/directives") as response:
                self.assertIn(b'Gestione direttive', response.read())
            with urlopen(base + "/api/directives") as response:
                self.assertEqual(json.load(response), [directive()])
            replacement = [directive("DET98", "Nuovo titolo")]
            request = Request(base + "/api/directives/import", json.dumps(replacement).encode(), {"Content-Type": "application/json"})
            with urlopen(request) as response:
                self.assertEqual(json.load(response)["rows"], replacement)
            with urlopen(base + "/api/catalogs") as response:
                self.assertEqual(json.load(response)["DET"], [{"code": "DET98", "title": "Nuovo titolo"}])
            composed = webapp.compose_request({"rows": [{"det": "DET98"}]})
            self.assertIn("[DET98] Nuovo titolo", composed["system_instruction"])
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(base + "/api/directives/import", b'[{}]'))
            self.assertEqual(error.exception.code, 400)
            error.exception.close()
            self.assertEqual(store.load_directives(), replacement)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
