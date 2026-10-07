from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import secrets
from threading import RLock
from typing import Iterator
from uuid import UUID

from app.core.errors import KycError
from app.models.state import Session


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class SessionStore:
    """One-process reference store. Replace with shared storage for replication."""
    def __init__(self, max_sessions: int) -> None:
        self.max_sessions = max_sessions
        self.sessions: dict[UUID, Session] = {}
        self.lock = RLock()

    def prune(self) -> None:
        now = datetime.now(timezone.utc)
        with self.lock:
            expired = [self.sessions.pop(key) for key, value in list(self.sessions.items()) if value.expires_at <= now]
        for session in expired:
            with session.lock:
                session.revoked = True
                session.clear_biometrics()

    def put(self, session: Session) -> None:
        self.prune()
        with self.lock:
            if len(self.sessions) >= self.max_sessions:
                raise KycError("capacity", "Verification capacity reached. Please try again shortly", 503)
            self.sessions[session.id] = session

    @contextmanager
    def authorized(self, key: UUID, token: str) -> Iterator[Session]:
        # Never hold the global store lock while waiting for a session lock.
        with self.lock:
            session = self.sessions.get(key)
        if session is None or not secrets.compare_digest(session.token_hash, token_digest(token)):
            raise KycError("invalid_session", "Session or authorization token is invalid", 401)
        with session.lock:
            if session.revoked or session.expires_at <= datetime.now(timezone.utc):
                raise KycError("session_expired", "Session expired. Upload the document again", 410)
            yield session

    def delete(self, session: Session) -> None:
        with self.lock:
            self.sessions.pop(session.id, None)
        session.revoked = True
        session.clear_biometrics()

    def clear(self) -> None:
        with self.lock:
            sessions = list(self.sessions.values())
            self.sessions.clear()
        for session in sessions:
            with session.lock:
                session.revoked = True
                session.clear_biometrics()

