from __future__ import annotations

import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from news_platform.infrastructure.database import get_db_session
from news_platform.modules.feeds.infrastructure.cache import invalidate_public_feed_cache
from news_platform.modules.ingestion.application.errors import IngestionError
from news_platform.modules.ingestion.application.service import IngestionService
from news_platform.modules.ingestion.domain.schemas import IncomingPackageReceipt

router = APIRouter(prefix="/internal/v1/ingestion", tags=["internal-ingestion"])
logger = logging.getLogger("news_platform.ingestion")
DatabaseSession = Depends(get_db_session)


def _required_header(value: str | None, name: str) -> str:
    if not value:
        raise HTTPException(
            status_code=401,
            detail={"code": "MISSING_SIGNATURE_HEADER", "message": f"missing {name}"},
        )
    return value


@router.post("/content", response_model=IncomingPackageReceipt)
async def receive_content(
    request: Request,
    response: Response,
    session: AsyncSession = DatabaseSession,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    instance_header: str | None = Header(default=None, alias="X-Integrator-Instance-Id"),
    signing_key_id: str | None = Header(default=None, alias="X-Signing-Key-Id"),
    timestamp: str | None = Header(default=None, alias="X-Timestamp"),
    signature: str | None = Header(default=None, alias="X-Signature"),
) -> IncomingPackageReceipt:
    idempotency_key = _required_header(idempotency_key, "Idempotency-Key")
    instance_header = _required_header(instance_header, "X-Integrator-Instance-Id")
    signing_key_id = _required_header(signing_key_id, "X-Signing-Key-Id")
    timestamp = _required_header(timestamp, "X-Timestamp")
    signature = _required_header(signature, "X-Signature")
    try:
        instance_id = UUID(instance_header)
    except ValueError as exc:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "INGESTION_AUTHENTICATION_FAILED",
                "message": "malformed X-Integrator-Instance-Id",
            },
        ) from exc

    body = await request.body()
    try:
        async with session.begin():
            receipt = await IngestionService(session).ingest(
                body=body,
                instance_id=instance_id,
                signing_key_id=signing_key_id,
                timestamp=timestamp,
                signature=signature,
                idempotency_key=idempotency_key,
                clock_skew_seconds=request.app.state.settings.ingestion_clock_skew_seconds,
                redis_client=request.app.state.redis,
                rate_limit=request.app.state.settings.ingestion_rate_limit,
                rate_limit_window_seconds=(
                    request.app.state.settings.ingestion_rate_limit_window_seconds
                ),
            )
    except IngestionError as exc:
        logger.warning(
            "ingestion_rejected",
            extra={
                "instance_id": str(instance_id),
                "signing_key_id": signing_key_id,
                "result": exc.code,
            },
        )
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc

    await invalidate_public_feed_cache(request.app.state.redis)

    response.status_code = 201 if receipt.status == "accepted" else 200
    validated_payload = json.loads(body)
    logger.info(
        "ingestion_complete",
        extra={
            "package_id": str(receipt.package_id),
            "package_version": receipt.package_version,
            "schema_version": validated_payload["schema_version"],
            "operation": validated_payload.get("operation", "created"),
            "instance_id": str(instance_id),
            "signing_key_id": signing_key_id,
            "result": receipt.status,
        },
    )
    return receipt
