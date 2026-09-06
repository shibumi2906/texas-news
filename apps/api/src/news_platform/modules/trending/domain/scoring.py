from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TrendingWeights:
    impressions: float = 0.05
    clicks: float = 1.5
    ctr: float = 25.0
    views: float = 1.0
    view_growth: float = 8.0
    comments: float = 4.0
    likes: float = 2.0
    shares: float = 5.0
    saves: float = 3.0
    watch_time_seconds: float = 0.01
    completions: float = 2.5
    freshness_half_life_hours: float = 18.0
    local_relevance: float = 1.0
    content_quality: float = 1.0

    @classmethod
    def from_portal(cls, ranking_settings: dict[str, Any]) -> TrendingWeights:
        configured = ranking_settings.get("trending", {})
        if not isinstance(configured, dict):
            return cls()
        defaults = cls()
        values: dict[str, float] = {}
        for name in defaults.__dataclass_fields__:
            raw = configured.get(name, getattr(defaults, name))
            if isinstance(raw, int | float) and raw >= 0:
                values[name] = float(raw)
        if values.get("freshness_half_life_hours", 0) == 0:
            values["freshness_half_life_hours"] = defaults.freshness_half_life_hours
        return cls(**values)
