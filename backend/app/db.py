import sqlite3
import threading
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  llm_provider TEXT,
  llm_model TEXT,
  llm_key_enc TEXT
);
CREATE TABLE IF NOT EXISTS quizzes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  questions_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS attempts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  quiz_id INTEGER NOT NULL REFERENCES quizzes(id),
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  score INTEGER NOT NULL,
  total INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS attempt_answers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  attempt_id INTEGER NOT NULL REFERENCES attempts(id),
  question_id INTEGER NOT NULL,
  topic TEXT NOT NULL,
  selected_index INTEGER,
  correct INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS revision_plans (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  note TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS revision_tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  plan_id INTEGER NOT NULL REFERENCES revision_plans(id),
  day INTEGER NOT NULL,
  topic TEXT NOT NULL,
  minutes INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'todo'
);
CREATE TABLE IF NOT EXISTS llm_usage (
  user_id INTEGER NOT NULL,
  day TEXT NOT NULL,
  calls INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (user_id, day)
);
"""


class Database:
    def __init__(self, path: str):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.lock = threading.Lock()
        with self.lock:
            self.conn.executescript(SCHEMA)
            # Personal API keys are never persisted any more. Wipe anything saved by older versions.
            self.conn.execute("UPDATE users SET llm_provider=NULL, llm_model=NULL, llm_key_enc=NULL "
                              "WHERE llm_key_enc IS NOT NULL OR llm_provider IS NOT NULL")
            self.conn.commit()

    def execute(self, sql: str, params: tuple = ()) -> int:
        with self.lock:
            cur = self.conn.execute(sql, params)
            self.conn.commit()
            return cur.lastrowid

    def query(self, sql: str, params: tuple = ()) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    def reserve_llm_call(self, user_id: int, day: str, user_cap: int, global_cap: int) -> str | None:
        """Atomically check both daily caps and count one server-key call.
        Returns None if reserved, otherwise 'user' or 'global' for the cap that was hit."""
        with self.lock:
            mine = self.conn.execute(
                "SELECT calls FROM llm_usage WHERE user_id=? AND day=?", (user_id, day)).fetchone()
            total = self.conn.execute(
                "SELECT COALESCE(SUM(calls),0) FROM llm_usage WHERE day=?", (day,)).fetchone()[0]
            if (mine["calls"] if mine else 0) >= user_cap:
                return "user"
            if total >= global_cap:
                return "global"
            self.conn.execute(
                "INSERT INTO llm_usage (user_id, day, calls) VALUES (?,?,1) "
                "ON CONFLICT(user_id, day) DO UPDATE SET calls = calls + 1", (user_id, day))
            self.conn.commit()
            return None

    def release_llm_call(self, user_id: int, day: str) -> None:
        """Give back a reserved demo call when the provider call did not produce an answer."""
        with self.lock:
            self.conn.execute("UPDATE llm_usage SET calls = MAX(calls - 1, 0) WHERE user_id=? AND day=?",
                              (user_id, day))
            self.conn.commit()

    def delete_user_data(self, user_id: int) -> None:
        with self.lock:
            c = self.conn
            c.execute("DELETE FROM attempt_answers WHERE attempt_id IN (SELECT id FROM attempts WHERE user_id=?)", (user_id,))
            c.execute("DELETE FROM attempts WHERE user_id=?", (user_id,))
            c.execute("DELETE FROM quizzes WHERE user_id=?", (user_id,))
            c.execute("DELETE FROM revision_tasks WHERE plan_id IN (SELECT id FROM revision_plans WHERE user_id=?)", (user_id,))
            c.execute("DELETE FROM revision_plans WHERE user_id=?", (user_id,))
            c.execute("DELETE FROM llm_usage WHERE user_id=?", (user_id,))
            c.execute("DELETE FROM users WHERE id=?", (user_id,))
            c.commit()
