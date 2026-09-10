from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID


class InvalidRecommendationCursorError(Exception):
    pass


@dataclass(frozen=True)
class RecommendationCursor:
    portal_id: UUID
    user_id: UUID
    feed: str
    language: str
    generation: int
    snapshot_at: datetime
    published_at: datetime
    content_id: UUID
    score: Decimal | None = None

    def encode(self) -> str:
        payload = {
            "v": 1,
            "p": str(self.portal_id),
            "u": str(self.user_id),
            "f": self.feed,
            "l": self.language,
            "g": self.generation,
            "t": self.snapshot_at.astimezone(UTC).isoformat(),
            "a": self.published_at.astimezone(UTC).isoformat(),
            "i": str(self.content_id),
        }
        if self.score is not None:
            payload["r"] = str(self.score)
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    @classmethod
    def decode(
        cls,
        value: str,
        *,
        portal_id: UUID,
        user_id: UUID,
        feed: str,
        language: str,
        generation: int,
    ) -> RecommendationCursor:
        try:
            payload = json.loads(base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)))
            if not isinstance(payload, dict) or payload.get("v") != 1:
                raise ValueError
            if UUID(str(payload["p"])) != portal_id or UUID(str(payload["u"])) != user_id:
                raise ValueError
            if (
                payload.get("f") != feed
                or payload.get("l") != language
                or payload.get("g") != generation
            ):
                raise ValueError
            snapshot = datetime.fromisoformat(str(payload["t"]))
            published = datetime.fromisoformat(str(payload["a"]))
            if snapshot.tzinfo is None or published.tzinfo is None:
                raise ValueError
            return cls(
                portal_id,
                user_id,
                feed,
                language,
                generation,
                snapshot,
                published,
                UUID(str(payload["i"])),
                Decimal(str(payload["r"])) if "r" in payload else None,
            )
        except (
            ValueError,
            KeyError,
            TypeError,
            json.JSONDecodeError,
            binascii.Error,
            InvalidOperation,
        ) as exc:
            raise InvalidRecommendationCursorError(
                "invalid, stale, or mismatched recommendation cursor"
            ) from exc
