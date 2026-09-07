from datetime import UTC, datetime

from news_platform.modules.public_site.application.service import (
    PublicNotFoundError,
    PublicSiteService,
)
from news_platform.modules.search.application.port import SearchBackend
from news_platform.modules.search.domain.schemas import SearchCursor, SearchPage, SearchQuery


class SearchService:
    def __init__(self, public: PublicSiteService, backend: SearchBackend) -> None:
        self.public = public
        self.backend = backend

    async def page(self, portal_slug: str, query: SearchQuery) -> SearchPage:
        generation = await self.backend.generation()
        now = datetime.now(UTC)
        portal = await self.public.repository.get_portal(portal_slug)
        if portal is None:
            raise PublicNotFoundError("portal not found")
        if query.language not in portal.supported_languages:
            raise PublicNotFoundError("language not supported by portal")
        categories = await self.public.repository.portal_categories(portal)
        context = query.context(portal.id)
        cursor = (
            SearchCursor.decode(query.cursor, context, generation, now) if query.cursor else None
        )
        snapshot_at = cursor.snapshot_at if cursor else now
        records, has_more = await self.backend.search(portal, query, snapshot_at, cursor)
        next_cursor = None
        if has_more:
            last = records[-1]
            assert last.record.content.site_published_at is not None and last.score is not None
            next_cursor = SearchCursor(
                context=context,
                generation=generation,
                snapshot_at=snapshot_at,
                published_at=last.record.content.site_published_at,
                content_id=last.record.content.id,
                score=last.score,
            ).encode()
        return SearchPage(
            portal=self.public.portal_view(portal, categories),
            language=query.language,
            query=query.q,
            items=[self.public.story_summary(portal, r.record) for r in records],
            next_cursor=next_cursor,
        )
