"""Social accounts and publications."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from wire_api.models.base import Base, GUID, JSONField, PKMixin, TimestampMixin, TZDateTime


class Platform(enum.StrEnum):
    X = "x"
    LINKEDIN = "linkedin"
    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"
    YOUTUBE = "youtube"
    THREADS = "threads"
    FACEBOOK = "facebook"


class PublicationStatus(enum.StrEnum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    POSTING = "posting"
    POSTED = "posted"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


class SocialAccount(Base, PKMixin, TimestampMixin):
    __tablename__ = "social_account"

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[Platform] = mapped_column(
        Enum(Platform, native_enum=False, length=16), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(128), default="")
    handle: Mapped[str] = mapped_column(String(128), default="")
    # encrypted vendor profile key / oauth token ref — never plaintext
    encrypted_token: Mapped[str] = mapped_column(Text, default="")
    connected_at: Mapped[datetime | None] = mapped_column(TZDateTime())
    is_active: Mapped[bool] = mapped_column(default=True)
    # anti-flagging: default 4 posts/day, hard cap 8 — enforced server-side
    daily_post_ceiling: Mapped[int] = mapped_column(Integer, default=4)

    __table_args__ = (
        Index("uq_social_account_user_platform_ext", "user_id", "platform", "external_id",
              unique=True),
    )


class Publication(Base, PKMixin, TimestampMixin):
    __tablename__ = "publication"

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False
    )
    artifact_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("artifact.id", ondelete="RESTRICT"), nullable=False
    )
    social_account_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("social_account.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[PublicationStatus] = mapped_column(
        Enum(PublicationStatus, native_enum=False, length=16), default=PublicationStatus.DRAFT
    )
    scheduled_for: Mapped[datetime | None] = mapped_column(TZDateTime())
    posted_at: Mapped[datetime | None] = mapped_column(TZDateTime())
    external_post_id: Mapped[str] = mapped_column(String(128), default="")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSONField)
    # engagement metrics harvested later — feeds learning loops 3 & 4
    engagement: Mapped[dict[str, Any]] = mapped_column(JSONField, default=dict)
    engagement_synced_at: Mapped[datetime | None] = mapped_column(TZDateTime())

    __table_args__ = (
        Index("ix_publication_user_scheduled", "user_id", "scheduled_for"),
        Index("ix_publication_account_posted", "social_account_id", "posted_at"),
    )
