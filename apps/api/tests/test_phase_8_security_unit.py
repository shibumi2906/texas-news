from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError
from starlette.responses import Response

from news_platform.modules.analytics.domain.schemas import BehaviorEventCreate
from news_platform.modules.users.api.router import _set_cookie
from news_platform.modules.users.application.security import (
    SCRYPT_N,
    SCRYPT_P,
    SCRYPT_R,
    hash_password,
    verify_password,
)


def test_password_hash_is_salted_and_verifiable() -> None:
    first = hash_password("correct horse battery")
    second = hash_password("correct horse battery")
    assert first != second
    assert "correct horse battery" not in first
    assert verify_password("correct horse battery", first)
    assert not verify_password("incorrect horse battery", first)
    assert first.split("$")[1:4] == [str(SCRYPT_N), str(SCRYPT_R), str(SCRYPT_P)]
    assert (SCRYPT_N, SCRYPT_R, SCRYPT_P) == (2**15, 8, 3)


def test_auth_cookies_have_explicit_security_attributes() -> None:
    response = Response()
    _set_cookie(
        response,
        "raw-session",
        "raw-csrf",
        datetime.now(UTC) + timedelta(hours=1),
        production=True,
    )
    cookies = response.headers.getlist("set-cookie")
    session_cookie = next(value for value in cookies if value.startswith("news_session="))
    csrf_cookie = next(value for value in cookies if value.startswith("news_csrf="))
    assert "HttpOnly" in session_cookie
    assert "Secure" in session_cookie
    assert "SameSite=lax" in session_cookie
    assert "Path=/api/v1/portals/" in session_cookie
    assert "HttpOnly" not in csrf_cookie
    assert "Secure" in csrf_cookie


def test_public_analytics_cannot_impersonate_an_authenticated_user() -> None:
    with pytest.raises(ValidationError):
        BehaviorEventCreate.model_validate(
            {
                "id": str(uuid4()),
                "user_id": str(uuid4()),
                "anonymous_id": "browser-session",
                "session_id": "analytics-session",
                "event_type": "search",
                "timestamp": "2026-09-08T12:00:00Z",
                "properties": {"result_count": 1},
            }
        )
