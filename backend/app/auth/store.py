from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True, slots=True)
class UserRecord:
    id: str
    username: str
    password_hash: str
    created_at: datetime


class AuthStore:
    """使用 SQLite 保存用户和不可逆会话令牌摘要。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    username_key TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires_at REAL NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_sessions_user_id
                ON sessions(user_id);
                CREATE INDEX IF NOT EXISTS idx_sessions_expires_at
                ON sessions(expires_at);
                """
            )

    def create_user(
        self,
        *,
        user_id: str,
        username: str,
        password_hash: str,
    ) -> UserRecord:
        created_at = datetime.now(UTC)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO users(id, username, username_key, password_hash, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    username,
                    username.casefold(),
                    password_hash,
                    created_at.isoformat(),
                ),
            )
        return UserRecord(user_id, username, password_hash, created_at)

    def find_user_by_username(self, username: str) -> UserRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, username, password_hash, created_at
                FROM users WHERE username_key = ?
                """,
                (username.casefold(),),
            ).fetchone()
        return _user_from_row(row)

    def create_session(
        self,
        *,
        token_hash: str,
        user_id: str,
        expires_at: float,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO sessions(token_hash, user_id, expires_at, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (token_hash, user_id, expires_at, datetime.now(UTC).isoformat()),
            )

    def find_user_by_session(self, token_hash: str) -> UserRecord | None:
        now = datetime.now(UTC).timestamp()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT u.id, u.username, u.password_hash, u.created_at
                FROM sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.token_hash = ? AND s.expires_at > ?
                """,
                (token_hash, now),
            ).fetchone()
            connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
        return _user_from_row(row)

    def delete_session(self, token_hash: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM sessions WHERE token_hash = ?",
                (token_hash,),
            )

    def delete_expired_sessions(self) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM sessions WHERE expires_at <= ?",
                (datetime.now(UTC).timestamp(),),
            )


def _user_from_row(row: sqlite3.Row | None) -> UserRecord | None:
    if row is None:
        return None
    return UserRecord(
        id=str(row["id"]),
        username=str(row["username"]),
        password_hash=str(row["password_hash"]),
        created_at=datetime.fromisoformat(str(row["created_at"])),
    )
