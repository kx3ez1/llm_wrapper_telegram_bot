import sqlite3
import logging
import os
import secrets
import threading
from datetime import datetime
from typing import Optional, Dict, List, Tuple

logger = logging.getLogger(__name__)

MAX_MESSAGES_PER_USER = 10000

_TOKEN_WORDS = [
    "RED", "BLUE", "GOLD", "PINK", "LIME", "CYAN", "GRAY", "ROSE",
    "TEAL", "JADE", "NAVY", "SAGE", "FIRE", "IRON", "WAVE", "BOLT",
    "DAWN", "DUSK", "MIST", "SNOW", "RUBY", "ONYX", "SAND", "FERN",
]
_TOKEN_CHARS = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0 O I L 1


def _make_token() -> str:
    word = secrets.choice(_TOKEN_WORDS)
    code = "".join(secrets.choice(_TOKEN_CHARS) for _ in range(4))
    return f"{word}-{code}"


class SQLiteThreadStore:
    """
    Persistent, per-user thread message store backed by SQLite.
    Thread-safe via a single lock around all DB operations.
    Fixed capacity: oldest messages are pruned when a user exceeds MAX_MESSAGES_PER_USER.
    Also manages access tokens for bot authentication.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()
        logger.info(f"SQLiteThreadStore initialised at {db_path}")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")   # better concurrent read performance
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS thread_messages (
                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id     INTEGER NOT NULL,
                        message_id  INTEGER NOT NULL,
                        chat_id     INTEGER NOT NULL,
                        role        TEXT    NOT NULL,
                        content     TEXT    NOT NULL,
                        parent_id   INTEGER,
                        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(user_id, message_id)
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_thread_user
                    ON thread_messages(user_id, id)
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS tokens (
                        token       TEXT PRIMARY KEY,
                        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        created_by  INTEGER NOT NULL,
                        used_by     INTEGER,
                        used_at     TIMESTAMP,
                        is_active   INTEGER DEFAULT 1
                    )
                """)
                conn.commit()
            finally:
                conn.close()

    def store(
        self,
        user_id: int,
        message_id: int,
        chat_id: int,
        role: str,
        content: str,
        parent_id: Optional[int] = None,
    ) -> None:
        """
        Insert a message. If user exceeds MAX_MESSAGES_PER_USER, oldest rows are deleted.
        Uses INSERT OR IGNORE so duplicate (user_id, message_id) pairs are silently skipped.
        """
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO thread_messages
                        (user_id, message_id, chat_id, role, content, parent_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (user_id, message_id, chat_id, role, content, parent_id))

                # Enforce per-user cap
                row = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM thread_messages WHERE user_id = ?",
                    (user_id,)
                ).fetchone()
                count = row["cnt"]

                if count > MAX_MESSAGES_PER_USER:
                    excess = count - MAX_MESSAGES_PER_USER
                    conn.execute("""
                        DELETE FROM thread_messages
                        WHERE user_id = ? AND id IN (
                            SELECT id FROM thread_messages
                            WHERE user_id = ?
                            ORDER BY id ASC
                            LIMIT ?
                        )
                    """, (user_id, user_id, excess))
                    logger.info(f"Pruned {excess} oldest message(s) for user {user_id}")

                conn.commit()
            except Exception as e:
                logger.error(f"ThreadStore.store failed: {e}")
                conn.rollback()
            finally:
                conn.close()

    def get(self, user_id: int, message_id: int) -> Optional[Dict]:
        """Return a single entry for (user_id, message_id), or None if not found."""
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute("""
                    SELECT role, content, parent_id, chat_id
                    FROM thread_messages
                    WHERE user_id = ? AND message_id = ?
                """, (user_id, message_id)).fetchone()
                if row:
                    return {
                        "role": row["role"],
                        "content": row["content"],
                        "parent_id": row["parent_id"],
                        "chat_id": row["chat_id"],
                    }
                return None
            finally:
                conn.close()

    def user_message_count(self, user_id: int) -> int:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM thread_messages WHERE user_id = ?",
                    (user_id,)
                ).fetchone()
                return row["cnt"]
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    def create_token(self, created_by: int) -> str:
        """Generate a unique token and persist it. Returns the token string."""
        with self._lock:
            conn = self._connect()
            try:
                for _ in range(10):  # retry on collision (astronomically rare)
                    token = _make_token()
                    existing = conn.execute(
                        "SELECT 1 FROM tokens WHERE token = ?", (token,)
                    ).fetchone()
                    if not existing:
                        conn.execute(
                            "INSERT INTO tokens (token, created_by) VALUES (?, ?)",
                            (token, created_by),
                        )
                        conn.commit()
                        logger.info(f"Token {token} created by {created_by}")
                        return token
                raise RuntimeError("Failed to generate unique token after 10 attempts")
            finally:
                conn.close()

    def claim_token(self, token: str, user_id: int) -> bool:
        """
        Bind a token to a user. Returns True on success.
        Fails if token doesn't exist, is inactive, or already claimed by someone else.
        If the same user re-sends their own token, returns True (idempotent).
        """
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT used_by, is_active FROM tokens WHERE token = ?",
                    (token,),
                ).fetchone()
                if not row:
                    return False
                if not row["is_active"]:
                    return False
                if row["used_by"] is not None:
                    return row["used_by"] == user_id  # already theirs → ok
                conn.execute(
                    "UPDATE tokens SET used_by = ?, used_at = ? WHERE token = ?",
                    (user_id, datetime.utcnow().isoformat(), token),
                )
                conn.commit()
                logger.info(f"Token {token} claimed by user {user_id}")
                return True
            finally:
                conn.close()

    def revoke_token(self, token: str) -> bool:
        """Deactivate a token. Returns True if it existed."""
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "UPDATE tokens SET is_active = 0 WHERE token = ?", (token,)
                )
                conn.commit()
                changed = cur.rowcount > 0
                if changed:
                    logger.info(f"Token {token} revoked")
                return changed
            finally:
                conn.close()

    def is_user_authenticated(self, user_id: int) -> bool:
        """True if the user has claimed at least one active token."""
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT 1 FROM tokens WHERE used_by = ? AND is_active = 1 LIMIT 1",
                    (user_id,),
                ).fetchone()
                return row is not None
            finally:
                conn.close()

    def get_user_id_for_token(self, token: str) -> Optional[int]:
        """Return user_id that claimed this token, or None."""
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT used_by FROM tokens WHERE token = ?", (token,)
                ).fetchone()
                return row["used_by"] if row else None
            finally:
                conn.close()

    def list_tokens(self) -> List[Dict]:
        """Return all tokens with their status, newest first."""
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT token, created_at, created_by, used_by, used_at, is_active "
                    "FROM tokens ORDER BY created_at DESC"
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def load_authenticated_user_ids(self) -> set:
        """Return set of user_ids that have an active claimed token (for in-memory cache)."""
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT used_by FROM tokens WHERE used_by IS NOT NULL AND is_active = 1"
                ).fetchall()
                return {r["used_by"] for r in rows}
            finally:
                conn.close()
