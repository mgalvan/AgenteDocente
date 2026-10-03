"""Persistent directives shared by the server and desktop composer."""
from contextlib import closing
from pathlib import Path
import sqlite3

DATABASE_FILE = Path(__file__).resolve().parent / "directives.sqlite3"
FIELDS = ("Gruppo", "Codice", "Ambito", "Titolo", "Direttiva completa")


def validate_directives(rows: object) -> list[dict[str, str]]:
    if not isinstance(rows, list):
        raise ValueError("Il JSON deve contenere una lista di direttive.")
    codes = set()
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict) or set(row) != set(FIELDS):
            raise ValueError(f"Riga {index}: campi richiesti: {', '.join(FIELDS)}. Non sono ammessi campi aggiuntivi.")
        for field in FIELDS:
            if not isinstance(row[field], str) or not row[field].strip():
                raise ValueError(f"Riga {index}: {field} deve essere una stringa non vuota.")
        code = row["Codice"].strip().upper()
        if code in codes:
            raise ValueError(f"Riga {index}: codice duplicato {code}.")
        if row["Codice"] != code or row["Gruppo"] != row["Gruppo"].strip().upper():
            raise ValueError(f"Riga {index}: Codice e Gruppo devono essere maiuscoli e senza spazi esterni.")
        codes.add(code)
    return rows


def initialize_database() -> None:
    with closing(sqlite3.connect(DATABASE_FILE)) as connection, connection:
        connection.execute('''CREATE TABLE IF NOT EXISTS direttive (
            "Gruppo" TEXT NOT NULL,
            "Codice" TEXT PRIMARY KEY COLLATE NOCASE,
            "Ambito" TEXT NOT NULL,
            "Titolo" TEXT NOT NULL,
            "Direttiva completa" TEXT NOT NULL
        )''')


def load_directives() -> list[dict[str, str]]:
    initialize_database()
    with closing(sqlite3.connect(DATABASE_FILE)) as connection:
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute('SELECT * FROM direttive ORDER BY rowid')]


def replace_directives(rows: object) -> list[dict[str, str]]:
    validated = validate_directives(rows)
    initialize_database()
    with closing(sqlite3.connect(DATABASE_FILE)) as connection, connection:
        connection.execute('DELETE FROM direttive')
        connection.executemany(
            'INSERT INTO direttive ("Gruppo", "Codice", "Ambito", "Titolo", "Direttiva completa") VALUES (?, ?, ?, ?, ?)',
            [tuple(row[field] for field in FIELDS) for row in validated],
        )
    return validated
