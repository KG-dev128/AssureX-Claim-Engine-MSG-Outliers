"""Database compatibility layer: Neon PostgreSQL when configured, SQLite locally."""
from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

try:
    import psycopg2
    from psycopg2 import Error as PostgreSQLError, IntegrityError as PostgreSQLIntegrityError
except ImportError:
    psycopg2 = None
    class PostgreSQLError(Exception):
        pass
    class PostgreSQLIntegrityError(PostgreSQLError):
        pass

DatabaseError = (sqlite3.Error, PostgreSQLError)
IntegrityError = (sqlite3.IntegrityError, PostgreSQLIntegrityError)


class _Row(dict):
    """Mapping row that also preserves SQLite's row[0] access pattern."""
    def __getitem__(self, key):
        if isinstance(key, int):
            return tuple(self.values())[key]
        return super().__getitem__(key)


class _Cursor:
    def __init__(self, cursor):
        self.cursor = cursor

    def execute(self, sql, params=()):
        self.cursor.execute(_postgres_sql(sql), params)
        return self

    def executemany(self, sql, params):
        self.cursor.executemany(_postgres_sql(sql), params)
        return self

    def _row(self, values):
        if values is None:
            return None
        names = [column[0] for column in self.cursor.description]
        return _Row(zip(names, values))

    def fetchone(self):
        return self._row(self.cursor.fetchone())

    def fetchall(self):
        return [self._row(row) for row in self.cursor.fetchall()]

    def __iter__(self):
        while True:
            row = self.fetchone()
            if row is None:
                return
            yield row

    @property
    def rowcount(self):
        return self.cursor.rowcount


class _Connection:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, sql, params=()):
        return _Cursor(self.connection.cursor()).execute(sql, params)

    def executemany(self, sql, params):
        return _Cursor(self.connection.cursor()).executemany(sql, params)

    def commit(self):
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        try:
            self.connection.rollback() if exc_type else self.connection.commit()
        finally:
            self.connection.close()
        return False


def _postgres_sql(sql: str) -> str:
    """Translate the small set of SQLite SQL forms used by this application."""
    pragma = re.fullmatch(r"\s*PRAGMA\s+table_info\((\w+)\)\s*;?\s*", sql, re.I)
    if pragma:
        table = pragma.group(1).lower()
        return ("SELECT column_name AS name FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = '" + table + "' "
                "ORDER BY ordinal_position")

    query = re.sub(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", "INSERT INTO", sql, flags=re.I)
    ignore = bool(re.search(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", sql, re.I))
    query = re.sub(r"\bINSERT\s+OR\s+REPLACE\s+INTO\b", "INSERT INTO", query, flags=re.I)
    replace = bool(re.search(r"\bINSERT\s+OR\s+REPLACE\s+INTO\b", sql, re.I))
    query = re.sub(r"\bINTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b", "BIGSERIAL PRIMARY KEY", query, flags=re.I)
    query = re.sub(r"date\('now'\s*,\s*\?\)", "to_char(CURRENT_DATE + (%s)::interval, 'YYYY-MM-DD')", query, flags=re.I)
    query = re.sub(r"date\('now'\s*,\s*'\+([0-9]+)\s+day'\)", r"to_char(CURRENT_DATE + INTERVAL '\1 days', 'YYYY-MM-DD')", query, flags=re.I)
    query = re.sub(r"date\('now'\)", "to_char(CURRENT_DATE, 'YYYY-MM-DD')", query, flags=re.I)
    query = query.replace("?", "%s")

    query = query.rstrip().rstrip(";")
    if replace:
        match = re.search(r"\bINSERT\s+INTO\s+(claims|prediction_records)\s*\(([^)]+)\)\s*VALUES\s*\(([^)]+)\)", query, re.I | re.S)
        if match:
            table, columns = match.group(1), [c.strip() for c in match.group(2).split(",")]
            key = "claim_id"
            updates = [f"{col}=EXCLUDED.{col}" for col in columns if col.lower() != key]
            query += f" ON CONFLICT ({key}) DO UPDATE SET " + ", ".join(updates)
    elif ignore:
        query += " ON CONFLICT DO NOTHING"
    return query


def get_db(sqlite_path=None):
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if database_url:
        if psycopg2 is None:
            raise RuntimeError("DATABASE_URL is set but psycopg2 is missing. Install requirements.txt.")
        # Neon may need a few seconds for DNS/routing and cold starts; bound
        # startup so a bad network or endpoint reports an error instead of
        # leaving Flask apparently frozen forever.
        return _Connection(psycopg2.connect(database_url, connect_timeout=15))

    path = Path(sqlite_path) if sqlite_path else Path(__file__).resolve().parent / "instance" / "assurex.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection
