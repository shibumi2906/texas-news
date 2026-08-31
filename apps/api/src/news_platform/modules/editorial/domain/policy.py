from news_platform.modules.content.domain.models import ContentStatus

ALLOWED_TRANSITIONS: dict[ContentStatus, frozenset[ContentStatus]] = {
    ContentStatus.RECEIVED: frozenset({ContentStatus.READY}),
    ContentStatus.PROCESSING: frozenset({ContentStatus.READY}),
    ContentStatus.READY: frozenset({ContentStatus.SCHEDULED, ContentStatus.PUBLISHED}),
    ContentStatus.SCHEDULED: frozenset({ContentStatus.READY, ContentStatus.PUBLISHED}),
    ContentStatus.PUBLISHED: frozenset({ContentStatus.UNPUBLISHED, ContentStatus.RETRACTED}),
    ContentStatus.UNPUBLISHED: frozenset(
        {ContentStatus.SCHEDULED, ContentStatus.PUBLISHED, ContentStatus.ARCHIVED}
    ),
    ContentStatus.ARCHIVED: frozenset({ContentStatus.READY, ContentStatus.UNPUBLISHED}),
    ContentStatus.RETRACTED: frozenset({ContentStatus.READY}),
}


class InvalidTransitionError(ValueError):
    pass


def require_transition(current: ContentStatus, target: ContentStatus) -> None:
    if target not in ALLOWED_TRANSITIONS.get(current, frozenset()):
        raise InvalidTransitionError(f"transition {current.value} -> {target.value} is not allowed")
