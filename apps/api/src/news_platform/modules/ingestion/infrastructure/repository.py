from __future__ import annotations

from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from news_platform.modules.ingestion.domain.models import (
    IncomingPackage,
    IncomingPackageVersion,
    IntegratorConnection,
)


class IngestionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_connection(self, instance_id: UUID) -> IntegratorConnection | None:
        return cast(
            IntegratorConnection | None,
            await self.session.scalar(
                select(IntegratorConnection).where(IntegratorConnection.instance_id == instance_id)
            ),
        )

    async def get_package(self, package_id: UUID, *, lock: bool = False) -> IncomingPackage | None:
        statement = select(IncomingPackage).where(IncomingPackage.package_id == package_id)
        if lock:
            statement = statement.with_for_update()
        return cast(IncomingPackage | None, await self.session.scalar(statement))

    async def get_version(
        self, package_id: UUID, package_version: int
    ) -> IncomingPackageVersion | None:
        return cast(
            IncomingPackageVersion | None,
            await self.session.scalar(
                select(IncomingPackageVersion).where(
                    IncomingPackageVersion.package_id == package_id,
                    IncomingPackageVersion.package_version == package_version,
                )
            ),
        )

    async def get_version_by_event(self, event_id: UUID) -> IncomingPackageVersion | None:
        return cast(
            IncomingPackageVersion | None,
            await self.session.scalar(
                select(IncomingPackageVersion).where(IncomingPackageVersion.event_id == event_id)
            ),
        )

    async def add_package(self, package: IncomingPackage) -> IncomingPackage:
        self.session.add(package)
        await self.session.flush()
        return package

    async def add_version(self, version: IncomingPackageVersion) -> IncomingPackageVersion:
        self.session.add(version)
        await self.session.flush()
        return version
