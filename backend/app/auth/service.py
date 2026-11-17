from __future__ import annotations

import base64
import hashlib
import secrets
import time
import uuid
from sqlite3 import IntegrityError

from .errors import AuthError
from .models import UserView
from .store import AuthStore, UserRecord


class AuthService:
    """注册、登录和短生命周期服务端会话。"""

    def __init__(
        self,
        store: AuthStore,
        session_ttl_seconds: int,
        cookie_secure: bool,
    ) -> None:
        self.store = store
        self.session_ttl_seconds = session_ttl_seconds
        self.cookie_secure = cookie_secure

    def register(
        self,
        username: str,
        password: str,
    ) -> tuple[UserView, str, int]:
        password_hash = _hash_password(password)
        try:
            user = self.store.create_user(
                user_id=uuid.uuid4().hex,
                username=username,
                password_hash=password_hash,
            )
        except IntegrityError as exc:
            raise AuthError("USERNAME_TAKEN", "这个用户名已经被使用", 409) from exc
        token, expires_at = self._create_session(user.id)
        return _to_view(user), token, expires_at

    def login(
        self,
        username: str,
        password: str,
    ) -> tuple[UserView, str, int]:
        user = self.store.find_user_by_username(username)
        password_hash = user.password_hash if user is not None else _DUMMY_PASSWORD_HASH
        password_matches = _verify_password(password, password_hash)
        if user is None or not password_matches:
            raise AuthError("INVALID_CREDENTIALS", "用户名或密码不正确", 401)
        token, expires_at = self._create_session(user.id)
        return _to_view(user), token, expires_at

    def resolve(self, token: str | None) -> UserView | None:
        if not token:
            return None
        user = self.store.find_user_by_session(_token_hash(token))
        return _to_view(user) if user else None

    def logout(self, token: str | None) -> None:
        if token:
            self.store.delete_session(_token_hash(token))

    def _create_session(self, user_id: str) -> tuple[str, int]:
        token = secrets.token_urlsafe(32)
        expires_at = int(time.time()) + self.session_ttl_seconds
        self.store.create_session(
            token_hash=_token_hash(token),
            user_id=user_id,
            expires_at=float(expires_at),
        )
        return token, expires_at


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=2**14,
        r=8,
        p=1,
        dklen=32,
    )
    return "scrypt$16384$8$1${}${}".format(
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(digest).decode("ascii"),
    )


def _verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt_text, digest_text = encoded.split("$", 5)
        if algorithm != "scrypt":
            return False
        salt = base64.b64decode(salt_text)
        expected = base64.b64decode(digest_text)
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return secrets.compare_digest(actual, expected)


_DUMMY_PASSWORD_HASH = _hash_password("dummy-password-for-timing")


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _to_view(user: UserRecord) -> UserView:
    return UserView(
        id=user.id,
        username=user.username,
        created_at=user.created_at,
    )
