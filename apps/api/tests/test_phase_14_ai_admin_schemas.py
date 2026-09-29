from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from news_platform.core.config import Settings
from news_platform.modules.ai.application.service import _cache_key
from news_platform.modules.ai.application.tasks import TaskManager
from news_platform.modules.ai.domain.admin_schemas import AITaskConfigUpdate, ExperimentUpdate


def test_task_config_requires_allowed_provider_and_unique_routes() -> None:
    valid = {
        "primary_model": "local:summary-v2",
        "fallback_models": ["local:summary-v1"],
        "allowed_providers": ["local"],
        "max_cost": "0.01",
        "max_input_tokens": 3000,
        "max_output_tokens": 250,
        "max_retries": 1,
        "timeout_seconds": 8,
        "prompt_version": 1,
    }
    assert AITaskConfigUpdate.model_validate(valid).primary_model == "local:summary-v2"

    with pytest.raises(ValidationError, match="allowed provider"):
        AITaskConfigUpdate.model_validate({**valid, "fallback_models": ["gateway:remote"]})


def test_experiment_requires_distinct_prompt_versions() -> None:
    prompt_id = uuid4()
    with pytest.raises(ValidationError, match="two distinct"):
        ExperimentUpdate.model_validate(
            {
                "name": "Trial",
                "prompt_version_a_id": prompt_id,
                "prompt_version_b_id": prompt_id,
                "variant_b_percent": 50,
                "status": "running",
            }
        )


def test_ai_result_cache_key_changes_with_selected_prompt_version() -> None:
    task = TaskManager(Settings()).get("story_summary")
    key_a = _cache_key(task, "content-hash", "portal-id", "en", "local:summary")
    key_b = _cache_key(
        replace(task, prompt_version=task.prompt_version + 1),
        "content-hash",
        "portal-id",
        "en",
        "local:summary",
    )
    assert key_a != key_b
