from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from news_platform.modules.content.domain.models import ContentItem
from news_platform.modules.localization.domain.models import Translation
from news_platform.modules.localization.domain.schemas import TranslationCreate
from news_platform.modules.portals.domain.models import Portal


class InvalidTranslationError(ValueError):
    pass


class TranslationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, data: TranslationCreate) -> Translation:
        portal = await self.session.get(Portal, data.portal_id)
        content = await self.session.get(ContentItem, data.content_item_id)
        if portal is None or content is None:
            raise InvalidTranslationError("portal or content not found")
        language = data.language.lower()
        if language not in portal.supported_languages:
            raise InvalidTranslationError("language not supported by portal")
        if language == content.primary_language:
            raise InvalidTranslationError("canonical language does not require a translation")
        existing = await self.session.scalar(
            select(Translation).where(
                Translation.portal_id == portal.id,
                Translation.content_item_id == content.id,
                Translation.language == language,
            )
        )
        if existing is not None:
            raise InvalidTranslationError("translation already exists")
        translation = Translation(**data.model_dump(exclude={"language"}), language=language)
        self.session.add(translation)
        await self.session.flush()
        return translation
