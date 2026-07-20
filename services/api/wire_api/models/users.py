"""Users, entitlements, the credit ledger, and BYOK credentials.

Financial rules enforced structurally:
- credit_ledger is append-only; balance is ALWAYS sum(delta_credits), never a column
- nothing financial cascades on delete (user deletion keeps the ledger via RESTRICT)
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from wire_api.models.base import Base, GUID, JSONField, PKMixin, TimestampMixin, TZDateTime


class Tier(enum.StrEnum):
    FREE = "free"
    PRO = "pro"
    BYOK = "byok"


class UserMode(enum.StrEnum):
    CLOUD = "cloud"
    BYOK = "byok"
    LOCAL = "local"


class User(Base, PKMixin, TimestampMixin):
    __tablename__ = "app_user"

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), default="")
    mode: Mapped[UserMode] = mapped_column(
        Enum(UserMode, native_enum=False, length=16), default=UserMode.CLOUD
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    entitlement: Mapped["Entitlement"] = relationship(back_populates="user", uselist=False)


class Entitlement(Base, PKMixin, TimestampMixin):
    __tablename__ = "entitlement"

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("app_user.id", ondelete="RESTRICT"),
        unique=True, nullable=False,
    )
    tier: Mapped[Tier] = mapped_column(Enum(Tier, native_enum=False, length=16), default=Tier.FREE)
    briefings_per_day: Mapped[int] = mapped_column(Integer, default=20)
    selections_per_day: Mapped[int] = mapped_column(Integer, default=3)
    variant_count: Mapped[int] = mapped_column(Integer, default=1)
    can_publish: Mapped[bool] = mapped_column(Boolean, default=False)
    can_video: Mapped[bool] = mapped_column(Boolean, default=False)
    period_reset_at: Mapped[datetime | None] = mapped_column(TZDateTime())
    stripe_customer_id: Mapped[str] = mapped_column(String(64), default="")
    stripe_subscription_id: Mapped[str] = mapped_column(String(64), default="")

    user: Mapped[User] = relationship(back_populates="entitlement")


class LedgerReason(enum.StrEnum):
    PURCHASE = "purchase"
    PERIOD_GRANT = "period_grant"
    RESERVE = "reserve"
    RESERVE_RELEASE = "reserve_release"
    DEBIT = "debit"
    REFUND = "refund"
    ADJUSTMENT = "adjustment"


class CreditLedger(Base, PKMixin, TimestampMixin):
    """Append-only. Every debit and credit with its job reference.

    Balance is derived by SUM(delta_credits). Reservations are rows too:
    RESERVE is negative, RESERVE_RELEASE returns it, DEBIT after a release
    charges the real amount. One transaction covers reserve→(release+debit).
    """

    __tablename__ = "credit_ledger"

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False
    )
    delta_credits: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reason: Mapped[LedgerReason] = mapped_column(
        Enum(LedgerReason, native_enum=False, length=24), nullable=False
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(GUID)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True)
    note: Mapped[str] = mapped_column(Text, default="")

    __table_args__ = (
        Index("ix_credit_ledger_user_created", "user_id", "created_at"),
        Index("ix_credit_ledger_job", "job_id"),
    )


class ByokCredential(Base, PKMixin, TimestampMixin):
    __tablename__ = "byok_credential"

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    # Fernet-encrypted key. Never logged, never returned to any client.
    encrypted_key: Mapped[str] = mapped_column(Text, nullable=False)
    daily_cap_cents: Mapped[int] = mapped_column(Integer, default=500)
    spent_today_cents: Mapped[int] = mapped_column(Integer, default=0)
    spent_reset_at: Mapped[datetime | None] = mapped_column(TZDateTime())
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        Index("uq_byok_user_provider", "user_id", "provider", unique=True),
    )
