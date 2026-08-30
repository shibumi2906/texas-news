from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime

from news_platform.modules.ingestion.application.errors import AuthenticationError
from news_platform.modules.ingestion.domain.models import IntegratorConnection


def sign_request(secret: str, timestamp: str, body: bytes) -> str:
    """Sign the documented timestamp followed by the exact request bytes."""
    message = timestamp.encode("utf-8") + body
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def validate_timestamp(timestamp: str, allowed_clock_skew_seconds: int) -> None:
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AuthenticationError("malformed request timestamp") from exc
    if parsed.tzinfo is None:
        raise AuthenticationError("request timestamp must include a timezone")
    if abs((datetime.now(UTC) - parsed).total_seconds()) > allowed_clock_skew_seconds:
        raise AuthenticationError("request timestamp outside allowed clock skew")


def verification_secret(connection: IntegratorConnection, signing_key_id: str) -> str | None:
    if signing_key_id == connection.active_key_id:
        return connection.active_secret
    if signing_key_id == connection.previous_key_id:
        return connection.previous_secret
    return None


def verify_signature(secret: str, timestamp: str, body: bytes, signature: str) -> None:
    if len(signature) != 64:
        raise AuthenticationError("invalid request signature")
    expected = sign_request(secret, timestamp, body)
    if not hmac.compare_digest(expected, signature.lower()):
        raise AuthenticationError("invalid request signature")
