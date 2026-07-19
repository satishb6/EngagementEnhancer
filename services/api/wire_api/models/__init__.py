"""All models, importable as a package so Base.metadata sees everything."""

from wire_api.models.base import EMBED_DIM, Base, uuid7, utcnow
from wire_api.models.corpus import Briefing, Cluster, ClusterMember, RawItem
from wire_api.models.feed import FeedItem, Swipe, SwipeDirection, Take, TakeSource
from wire_api.models.generation import (
    Artifact,
    ContentType,
    GenerationJob,
    GenerationTier,
    JobState,
)
from wire_api.models.learning import (
    FormatStat,
    LearningEvent,
    StyleProfile,
    TimingStat,
)
from wire_api.models.publishing import (
    Platform,
    Publication,
    PublicationStatus,
    SocialAccount,
)
from wire_api.models.sources import ProtocolSource, Source, SourceKind, UserProtocol
from wire_api.models.tracing import EventStatus, PipelineEvent, Stage
from wire_api.models.users import (
    ByokCredential,
    CreditLedger,
    Entitlement,
    LedgerReason,
    Tier,
    User,
    UserMode,
)

__all__ = [
    "EMBED_DIM",
    "Artifact",
    "Base",
    "Briefing",
    "ByokCredential",
    "Cluster",
    "ClusterMember",
    "ContentType",
    "CreditLedger",
    "Entitlement",
    "EventStatus",
    "FeedItem",
    "FormatStat",
    "GenerationJob",
    "GenerationTier",
    "JobState",
    "LearningEvent",
    "LedgerReason",
    "PipelineEvent",
    "Platform",
    "ProtocolSource",
    "Publication",
    "PublicationStatus",
    "RawItem",
    "SocialAccount",
    "Source",
    "SourceKind",
    "Stage",
    "StyleProfile",
    "Swipe",
    "SwipeDirection",
    "Take",
    "TakeSource",
    "Tier",
    "TimingStat",
    "User",
    "UserMode",
    "UserProtocol",
    "utcnow",
    "uuid7",
]
