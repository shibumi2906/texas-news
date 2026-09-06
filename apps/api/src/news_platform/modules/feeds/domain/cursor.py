from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID


class InvalidFeedCursorError(Exception):
    pass


@dataclass(frozen=True)
class FeedCursor:
    feed: str
    scope: str
    language: str
    generation: str
    snapshot_at: datetime
    published_at: datetime
    content_id: UUID
    score: Decimal | None = None

    def encode(self) -> str:
        payload = {
            "v": 2,
            "f": self.feed,
            "s": self.scope,
            "l": self.language,
            "g": self.generation,
            "t": self.snapshot_at.astimezone(UTC).isoformat(),
            "p": self.published_at.astimezone(UTC).isoformat(),
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
        feed: str,
        scope: str,
        language: str,
        generation: str,
    ) -> FeedCursor:
        try:
            padding = "=" * (-len(value) % 4)
            payload = json.loads(base64.urlsafe_b64decode(value + padding))
            if not isinstance(payload, dict) or payload.get("v") != 2:
                raise ValueError
            if payload.get("f") != feed or payload.get("s") != scope:
                raise ValueError
            if payload.get("l") != language:
                raise ValueError
            if payload.get("g") != generation:
                raise ValueError
            published_at = datetime.fromisoformat(str(payload["p"]))
            snapshot_at = datetime.fromisoformat(str(payload["t"]))
            if published_at.tzinfo is None or snapshot_at.tzinfo is None:
                raise ValueError
            score = Decimal(str(payload["r"])) if "r" in payload else None
            return cls(
                feed=feed,
                scope=scope,
                language=language,
                generation=generation,
                snapshot_at=snapshot_at,
                published_at=published_at,
                content_id=UUID(str(payload["i"])),
                score=score,
            )
        except (
            ValueError,
            KeyError,
            TypeError,
            json.JSONDecodeError,
            binascii.Error,
            InvalidOperation,
        ) as exc:
            raise InvalidFeedCursorError("invalid or mismatched feed cursor") from exc
