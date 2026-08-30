from __future__ import annotations

import argparse
import asyncio
import os
from uuid import UUID

from sqlalchemy import select

from news_platform.core.config import get_settings
from news_platform.infrastructure.database import create_db_engine, create_session_factory
from news_platform.modules.ingestion.domain.models import IntegratorConnection


async def provision(instance_id: UUID, name: str, key_id: str, secret: str) -> None:
    settings = get_settings()
    engine = create_db_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    try:
        async with session_factory() as session, session.begin():
            connection = await session.scalar(
                select(IntegratorConnection).where(IntegratorConnection.instance_id == instance_id)
            )
            if connection is None:
                session.add(
                    IntegratorConnection(
                        instance_id=instance_id,
                        name=name,
                        active_key_id=key_id,
                        active_secret=secret,
                    )
                )
            else:
                connection.name = name
                connection.is_active = True
                if connection.active_key_id != key_id:
                    connection.previous_key_id = connection.active_key_id
                    connection.previous_secret = connection.active_secret
                    connection.active_key_id = key_id
                    connection.active_secret = secret
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Provision a Site-side Integrator connection")
    parser.add_argument("--instance-id", required=True, type=UUID)
    parser.add_argument("--name", required=True)
    parser.add_argument("--key-id", required=True)
    args = parser.parse_args()
    secret = os.getenv("INTEGRATOR_HMAC_SECRET")
    if not secret or len(secret) < 16:
        raise SystemExit("INTEGRATOR_HMAC_SECRET must contain at least 16 characters")
    asyncio.run(provision(args.instance_id, args.name, args.key_id, secret))
    print(
        f"Integrator connection provisioned: instance_id={args.instance_id}, key_id={args.key_id}"
    )


if __name__ == "__main__":
    main()
