from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import Any

import httpx

from news_platform.core.config import Settings
from news_platform.modules.ai.application.ports import (
    ProviderAdapter,
    ProviderError,
    ProviderRequest,
    ProviderResponse,
)


def _sentences(value: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", value).strip()
    return [item.strip() for item in re.split(r"(?<=[.!?])\s+", normalized) if item.strip()]


def extractive_bullets(source: dict[str, Any]) -> list[str]:
    """Privacy-safe deterministic fallback using only the supplied public story."""
    candidates: list[str] = []
    for field in ("description", "subtitle", "body"):
        value = source.get(field)
        if isinstance(value, str):
            candidates.extend(_sentences(value))
    title = str(source.get("title") or "This story")
    unique: list[str] = []
    for candidate in candidates:
        clipped = candidate[:237].rstrip() + ("..." if len(candidate) > 240 else "")
        if clipped and clipped not in unique:
            unique.append(clipped)
        if len(unique) == 3:
            break
    if not unique:
        unique.append(title[:240])
    if len(unique) == 1:
        unique.append(f"Read the full story for details about {title}."[:240])
    return unique


class LocalSummaryAdapter:
    """Deterministic development adapter; it makes no external calls."""

    name = "local"

    def __init__(self, response_mode: str = "success") -> None:
        self.response_mode = response_mode

    async def execute(self, request: ProviderRequest) -> ProviderResponse:
        if self.response_mode == "malformed":
            return ProviderResponse(
                output_text="malformed local stub output",
                input_tokens=max(1, len(request.source_json) // 4),
                output_tokens=5,
                estimated_cost=Decimal("0"),
                gateway="local",
            )
        if self.response_mode in {"provider_error", "rate_limit", "timeout"}:
            raise ProviderError(self.response_mode)
        try:
            source = json.loads(request.source_json)
        except json.JSONDecodeError as exc:
            raise ProviderError("invalid_request") from exc
        output = json.dumps({"bullets": extractive_bullets(source)})
        return ProviderResponse(
            output_text=output,
            input_tokens=max(1, len(request.source_json) // 4),
            output_tokens=max(1, len(output) // 4),
            estimated_cost=Decimal("0"),
            gateway="local",
        )


class GatewayAdapter:
    """Adapter for an OpenAI-compatible external gateway hidden behind the AI port."""

    name = "gateway"

    def __init__(self, base_url: str, api_key: str, gateway_name: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.gateway_name = gateway_name

    async def execute(self, request: ProviderRequest) -> ProviderResponse:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "model": request.model,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {
                    "role": "user",
                    "content": "UNTRUSTED_SOURCE_DATA_JSON:\n" + request.source_json,
                },
            ],
            "max_tokens": request.max_output_tokens,
            "response_format": {"type": "json_object"},
        }
        try:
            async with httpx.AsyncClient(timeout=request.timeout_seconds) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions", headers=headers, json=payload
                )
        except httpx.TimeoutException as exc:
            raise ProviderError("timeout") from exc
        except httpx.HTTPError as exc:
            raise ProviderError("provider_error") from exc
        if response.status_code == 429:
            raise ProviderError("rate_limit")
        if response.status_code >= 400:
            raise ProviderError("provider_error")
        try:
            data = response.json()
            output = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            if not isinstance(output, str):
                raise TypeError
            input_tokens = int(usage.get("prompt_tokens", 0))
            output_tokens = int(usage.get("completion_tokens", 0))
            estimated_cost = Decimal(str(usage.get("cost", 0)))
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ProviderError("malformed_response") from exc
        return ProviderResponse(
            output_text=output,
            input_tokens=max(0, input_tokens),
            output_tokens=max(0, output_tokens),
            estimated_cost=max(Decimal("0"), estimated_cost),
            gateway=self.gateway_name,
        )


class ProviderRegistry:
    def __init__(self, adapters: list[ProviderAdapter]) -> None:
        self._adapters = {adapter.name: adapter for adapter in adapters}

    def get(self, name: str) -> ProviderAdapter:
        try:
            return self._adapters[name]
        except KeyError as exc:
            raise ProviderError("provider_unavailable") from exc

    @classmethod
    def from_settings(cls, settings: Settings) -> ProviderRegistry:
        adapters: list[ProviderAdapter] = [
            LocalSummaryAdapter(settings.ai_local_stub_response_mode)
        ]
        if settings.ai_gateway_url and settings.ai_gateway_api_key:
            adapters.append(
                GatewayAdapter(
                    settings.ai_gateway_url,
                    settings.ai_gateway_api_key.get_secret_value(),
                    settings.ai_gateway_name,
                )
            )
        return cls(adapters)
