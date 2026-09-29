"""Import all Phase 1 models so SQLAlchemy metadata is complete."""

from news_platform.modules.ai.domain.models import (
    AIExecution,
    AIExperiment,
    AIResult,
    AITaskConfig,
    PromptDefinition,
    PromptVersion,
)
from news_platform.modules.analytics.domain.models import BehaviorEvent, BehaviorEventAggregation
from news_platform.modules.community.domain.models import (
    Comment,
    CommentReport,
    Follow,
    ModerationAuditLog,
    Reaction,
    Save,
)
from news_platform.modules.content.domain.models import (
    ContentCategory,
    ContentEntity,
    ContentGeography,
    ContentItem,
    ContentTopic,
    ContentVersion,
    Source,
)
from news_platform.modules.editorial.domain.models import EditorialAuditLog
from news_platform.modules.engagement.domain.models import (
    ContentEngagementCounter,
    EngagementCounterUpdate,
)
from news_platform.modules.entities.domain.models import Entity
from news_platform.modules.geography.domain.models import GeographyNode
from news_platform.modules.ingestion.domain.models import (
    IncomingPackage,
    IncomingPackageVersion,
    IntegratorConnection,
)
from news_platform.modules.localization.domain.models import Translation
from news_platform.modules.media.domain.models import MediaAsset
from news_platform.modules.portals.domain.models import Portal
from news_platform.modules.recommendations.domain.models import (
    RecommendationGeneration,
    RecommendationSignalReceipt,
    UserAffinity,
    UserInterest,
)
from news_platform.modules.search.domain.models import SearchGeneration
from news_platform.modules.taxonomy.domain.models import Category, Topic
from news_platform.modules.users.domain.models import AuthSession, User, UserIdentity, UserProfile

__all__ = [
    "AIExecution",
    "AIExperiment",
    "AIResult",
    "AITaskConfig",
    "BehaviorEvent",
    "BehaviorEventAggregation",
    "Category",
    "AuthSession",
    "Comment",
    "CommentReport",
    "ContentCategory",
    "ContentEntity",
    "ContentEngagementCounter",
    "ContentGeography",
    "ContentItem",
    "ContentTopic",
    "ContentVersion",
    "Entity",
    "Follow",
    "EditorialAuditLog",
    "EngagementCounterUpdate",
    "GeographyNode",
    "IncomingPackage",
    "IncomingPackageVersion",
    "IntegratorConnection",
    "MediaAsset",
    "ModerationAuditLog",
    "Portal",
    "PromptDefinition",
    "PromptVersion",
    "Reaction",
    "RecommendationGeneration",
    "RecommendationSignalReceipt",
    "Save",
    "Source",
    "SearchGeneration",
    "Topic",
    "Translation",
    "User",
    "UserAffinity",
    "UserIdentity",
    "UserInterest",
    "UserProfile",
]
