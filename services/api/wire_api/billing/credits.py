"""The credit ledger.

Rules enforced here, not by convention:
- Balance is ALWAYS sum(credit_ledger.delta_credits). Never a mutable column.
- Debit at job start, refund on failure, in one transaction.
- Reserve-then-commit: a queued job holds a reservation so ten videos can't
  be queued against credits for one.
- Concurrency: a per-user Postgres advisory transaction lock serialises
  balance-changing writes, so concurrent overdraws lose cleanly.
"""

import enum
import uuid

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from wire_api.models import CreditLedger, LedgerReason


class InsufficientCredits(RuntimeError):
    def __init__(self, needed: int, available: int) -> None:
        self.needed = needed
        self.available = available
        super().__init__(f"Needs {needed} credits; {available} available.")


class ContentPrice(enum.IntEnum):
    """Credits charged per action (~2x worst-case COGS)."""

    TEXT_VARIANT = 1
    IMAGE = 2
    GIF = 2
    VIDEO_SHORT = 100
    VIDEO_LONG = 900
    PUBLISH = 5


PRICE_BY_CONTENT_TYPE: dict[str, int] = {
    "text": ContentPrice.TEXT_VARIANT,
    "image": ContentPrice.IMAGE,
    "gif": ContentPrice.GIF,
    "video_short": ContentPrice.VIDEO_SHORT,
    "video_long": ContentPrice.VIDEO_LONG,
}


async def _lock_user(session: AsyncSession, user_id: uuid.UUID) -> None:
    """Advisory xact lock keyed on the user id — released at commit/rollback.
    SQLite is single-writer, so the lock is a no-op there."""
    from wire_api.dbcompat import is_postgres

    if is_postgres(session):
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:uid))"), {"uid": str(user_id)}
        )


async def balance(session: AsyncSession, user_id: uuid.UUID) -> int:
    result = (
        await session.execute(
            select(func.coalesce(func.sum(CreditLedger.delta_credits), 0)).where(
                CreditLedger.user_id == user_id
            )
        )
    ).scalar_one()
    return int(result)


async def grant(
    session: AsyncSession, user_id: uuid.UUID, amount: int,
    reason: LedgerReason = LedgerReason.PURCHASE,
    idempotency_key: str | None = None, note: str = "",
) -> None:
    """Credit top-up / period grant. Idempotent when a key is supplied."""
    if idempotency_key:
        exists = (
            await session.execute(
                select(CreditLedger.id).where(CreditLedger.idempotency_key == idempotency_key)
            )
        ).scalar_one_or_none()
        if exists is not None:
            return
    session.add(CreditLedger(
        user_id=user_id, delta_credits=amount, reason=reason,
        idempotency_key=idempotency_key, note=note,
    ))
    await session.flush()


async def reserve(
    session: AsyncSession, user_id: uuid.UUID, amount: int, job_id: uuid.UUID
) -> None:
    """Hold credits for a queued job. Raises InsufficientCredits atomically."""
    await _lock_user(session, user_id)
    available = await balance(session, user_id)
    if available < amount:
        raise InsufficientCredits(amount, available)
    session.add(CreditLedger(
        user_id=user_id, delta_credits=-amount, reason=LedgerReason.RESERVE,
        job_id=job_id, idempotency_key=f"reserve:{job_id}",
    ))
    await session.flush()


async def commit_reservation(
    session: AsyncSession, user_id: uuid.UUID, job_id: uuid.UUID, actual_amount: int
) -> None:
    """Job finished: release the hold, debit the real amount."""
    await _lock_user(session, user_id)
    held = await _held_amount(session, job_id)
    if held == 0:
        return  # already settled (idempotent path)
    session.add(CreditLedger(
        user_id=user_id, delta_credits=held, reason=LedgerReason.RESERVE_RELEASE,
        job_id=job_id, idempotency_key=f"release:{job_id}",
    ))
    session.add(CreditLedger(
        user_id=user_id, delta_credits=-actual_amount, reason=LedgerReason.DEBIT,
        job_id=job_id, idempotency_key=f"debit:{job_id}",
    ))
    await session.flush()


async def refund_reservation(
    session: AsyncSession, user_id: uuid.UUID, job_id: uuid.UUID
) -> None:
    """Job failed: the hold comes back in full."""
    await _lock_user(session, user_id)
    held = await _held_amount(session, job_id)
    if held == 0:
        return
    session.add(CreditLedger(
        user_id=user_id, delta_credits=held, reason=LedgerReason.REFUND,
        job_id=job_id, idempotency_key=f"refund:{job_id}",
    ))
    await session.flush()


async def _held_amount(session: AsyncSession, job_id: uuid.UUID) -> int:
    """Outstanding reservation for a job = -(sum of its reserve/release/refund rows)."""
    result = (
        await session.execute(
            select(func.coalesce(func.sum(CreditLedger.delta_credits), 0)).where(
                CreditLedger.job_id == job_id,
                CreditLedger.reason.in_(
                    [LedgerReason.RESERVE, LedgerReason.RESERVE_RELEASE, LedgerReason.REFUND]
                ),
            )
        )
    ).scalar_one()
    return -int(result)
