"""Пароли и токены входа — на стандартной библиотеке, без внешних зависимостей.

Пароль хранится хэшем scrypt с солью: «scrypt$n$r$p$соль$хэш». Токен — подписанная HMAC
строка «данные.подпись»: в данных номер пользователя и срок действия. Подделать токен
без AUTH_SECRET нельзя, а проверка не ходит в БД за сессией.
"""

import base64
import hashlib
import hmac
import json
import secrets
import time

from src.core.config import settings

SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1


def _encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_encode(salt)}${_encode(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        candidate = hashlib.scrypt(
            password.encode(), salt=_decode(salt), n=int(n), r=int(r), p=int(p)
        )
        return hmac.compare_digest(candidate, _decode(digest))
    except (TypeError, ValueError):
        # Повреждённый или устаревший хэш одной учётки не должен превращать вход в 500.
        return False


def _sign(payload: str) -> str:
    return _encode(hmac.new(settings.auth_secret.encode(), payload.encode(), "sha256").digest())


def create_token(user_id: int, *, now: float | None = None) -> str:
    current = time.time() if now is None else now
    expires = int(current + settings.auth_token_hours * 3600)
    payload = _encode(json.dumps({"uid": user_id, "exp": expires}).encode())
    return f"{payload}.{_sign(payload)}"


def read_token(token: str, *, now: float | None = None) -> int | None:
    """Номер пользователя из токена; None — токен подделан, испорчен или истёк."""
    try:
        payload, signature = token.split(".")
    except ValueError:
        return None
    if not hmac.compare_digest(signature, _sign(payload)):
        return None
    try:
        data = json.loads(_decode(payload))
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    uid = data.get("uid")
    expires = data.get("exp")
    # bool является подклассом int, но номером пользователя быть не должен.
    if not isinstance(uid, int) or isinstance(uid, bool):
        return None
    if not isinstance(expires, (int, float)) or isinstance(expires, bool):
        return None
    current = time.time() if now is None else now
    if expires < current:
        return None
    return uid
