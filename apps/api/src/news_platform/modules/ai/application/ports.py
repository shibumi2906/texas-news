from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class ProviderRequest:
    task: str
    model: str
    system_prompt: str
    source_json: str
    max_output_tokens: int
    timeout_seconds: float
    reasoning_level: str


@dataclass(frozen=True)
class ProviderResponse:
    output_text: str
    input_tokens: int
    output_tokens: int
    estimated_cost: Decimal
    gateway: str | None = None


class ProviderError(Exception):
    def __init__(self, error_type: str) -> None:
        super().__init__(error_type)
        self.error_type = error_type


class ProviderAdapter(Protocol):
    name: str

    async def execute(self, request: ProviderRequest) -> ProviderResponse: ...
