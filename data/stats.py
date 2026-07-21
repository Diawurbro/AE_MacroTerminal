"""SQLite run history (Phase 5). Backs the status panel summary and the
Discord loss-streak alert."""

import os
import sqlite3
import time
from contextlib import closing

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stage TEXT NOT NULL,
    started_at REAL NOT NULL,
    ended_at REAL NOT NULL,
    result TEXT NOT NULL,       -- 'win' | 'loss' | 'abort'
    loop_no INTEGER NOT NULL,
    screenshot TEXT,
    note TEXT
);
"""


class StatsDB:
    def __init__(self, path: str):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.path = path
        with closing(sqlite3.connect(self.path)) as con:
            con.execute(SCHEMA)
            con.commit()

    def record(self, stage: str, result: str, loop_no: int, started_at: float,
               screenshot: str | None = None, note: str = ""):
        with closing(sqlite3.connect(self.path)) as con:
            con.execute(
                "INSERT INTO runs (stage, started_at, ended_at, result, loop_no, "
                "screenshot, note) VALUES (?,?,?,?,?,?,?)",
                (stage, started_at, time.time(), result, loop_no, screenshot, note))
            con.commit()

    def loss_streak(self, stage: str) -> int:
        """Consecutive losses at the tail of history; aborts don't break it
        and don't count towards it - they're not a game result."""
        with closing(sqlite3.connect(self.path)) as con:
            rows = con.execute(
                "SELECT result FROM runs WHERE stage=? AND result IN ('win','loss') "
                "ORDER BY id DESC", (stage,)).fetchall()
        streak = 0
        for (result,) in rows:
            if result == "loss":
                streak += 1
            else:
                break
        return streak

    def summary(self, stage: str) -> tuple[int, int]:
        """Returns (wins, losses) for the stage."""
        with closing(sqlite3.connect(self.path)) as con:
            row = con.execute(
                "SELECT SUM(result='win'), SUM(result='loss') FROM runs "
                "WHERE stage=?", (stage,)).fetchone()
        return (row[0] or 0, row[1] or 0)
