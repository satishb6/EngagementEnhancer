"""Billing endpoints: balance, history, Stripe webhooks, BYOK keys."""

import uuid
from typing import Any

import stripe
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from wire_api.auth.deps import DB, CurrentEntitlement, CurrentUser
from wire_api.billing.credits import balance, grant
from wire_api.logging import get_logger
from wire_api.models import ByokCredential, CreditLedger, LedgerReason, Tier
from wire_api.providers.byok import encrypt_key
from wire_api.settings import get_settings

log = get_logger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])

PRO_MONTHLY_CREDITS = 725


@router.get("/balance")
async def get_balance(user: CurrentUser, ent: CurrentEntitlement, session: DB) -> dict[str, Any]:
    return {
        "balance": await balance(session, user.id),
        "tier": ent.tier.value,
        "can_publish": ent.can_publish,
        "can_video": ent.can_video,
        "variant_count": ent.variant_count,
        "selections_per_day": ent.selections_per_day,
    }


@router.get("/ledger")
async def get_ledger(user: CurrentUser, session: DB, limit: int = 100) -> list[dict[str, Any]]:
    rows = (
        (
            await session.execute(
                select(CreditLedger)
                .where(CreditLedger.user_id == user.id)
                .order_by(CreditLedger.created_at.desc())
                .limit(min(limit, 500))
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": str(r.id), "delta": r.delta_credits, "reason": r.reason.value,
            "job_id": str(r.job_id) if r.job_id else None, "note": r.note,
            "at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request, session: DB) -> dict[str, str]:
    """Idempotent: the Stripe event id is the ledger idempotency key, so a
    retried webhook never double-grants."""
    settings = get_settings()
    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(
            payload, signature, settings.stripe_webhook_secret
        )
    except (ValueError, stripe.error.SignatureVerificationError) as exc:  # type: ignore[attr-defined]
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bad Stripe signature.") from exc

    kind = event["type"]
    data = event["data"]["object"]

    if kind == "checkout.session.completed":
        user_id = data.get("client_reference_id")
        credits = int(data.get("metadata", {}).get("credits", 0))
        if user_id and credits:
            await grant(
                session, uuid.UUID(user_id), credits,
                reason=LedgerReason.PURCHASE,
                idempotency_key=f"stripe:{event['id']}",
                note="credit top-up",
            )
    elif kind == "invoice.paid":
        # subscription renewal → period grant + tier upkeep
        sub_id = data.get("subscription", "")
        from wire_api.models import Entitlement

        ent = (
            await session.execute(
                select(Entitlement).where(Entitlement.stripe_subscription_id == sub_id)
            )
        ).scalar_one_or_none()
        if ent is not None:
            await grant(
                session, ent.user_id, PRO_MONTHLY_CREDITS,
                reason=LedgerReason.PERIOD_GRANT,
                idempotency_key=f"stripe:{event['id']}",
                note="monthly credit grant",
            )
    elif kind == "customer.subscription.deleted":
        sub_id = data.get("id", "")
        from wire_api.models import Entitlement

        ent = (
            await session.execute(
                select(Entitlement).where(Entitlement.stripe_subscription_id == sub_id)
            )
        ).scalar_one_or_none()
        if ent is not None:
            ent.tier = Tier.FREE
            ent.briefings_per_day = 20
            ent.selections_per_day = 3
            ent.variant_count = 1
            ent.can_publish = False
            ent.can_video = False

    await session.commit()
    log.info("stripe.webhook", kind=kind, event_id=event["id"])
    return {"status": "ok"}


class ByokIn(BaseModel):
    provider: str = Field(pattern="^(anthropic|openai|google|fal|deepgram)$")
    api_key: str = Field(min_length=8, max_length=400)
    daily_cap_cents: int = Field(ge=50, le=100_000, default=500)


@router.post("/byok", status_code=status.HTTP_201_CREATED)
async def add_byok_key(body: ByokIn, user: CurrentUser, session: DB) -> dict[str, Any]:
    """Store an encrypted BYOK key. The plaintext never appears in logs,
    traces, or any response — including this one."""
    existing = (
        await session.execute(
            select(ByokCredential).where(
                ByokCredential.user_id == user.id, ByokCredential.provider == body.provider
            )
        )
    ).scalar_one_or_none()
    encrypted = encrypt_key(body.api_key)
    if existing is None:
        session.add(ByokCredential(
            user_id=user.id, provider=body.provider, encrypted_key=encrypted,
            daily_cap_cents=body.daily_cap_cents,
        ))
    else:
        existing.encrypted_key = encrypted
        existing.daily_cap_cents = body.daily_cap_cents
        existing.is_active = True
    await session.commit()
    return {"provider": body.provider, "daily_cap_cents": body.daily_cap_cents, "stored": True}


@router.get("/byok")
async def list_byok_keys(user: CurrentUser, session: DB) -> list[dict[str, Any]]:
    rows = (
        (
            await session.execute(
                select(ByokCredential).where(
                    ByokCredential.user_id == user.id, ByokCredential.is_active.is_(True)
                )
            )
        )
        .scalars()
        .all()
    )
    # never the key, never a prefix of the key
    return [
        {
            "provider": r.provider,
            "daily_cap_cents": r.daily_cap_cents,
            "spent_today_cents": r.spent_today_cents,
            "connected_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.delete("/byok/{provider}")
async def remove_byok_key(provider: str, user: CurrentUser, session: DB) -> dict[str, str]:
    row = (
        await session.execute(
            select(ByokCredential).where(
                ByokCredential.user_id == user.id, ByokCredential.provider == provider
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No key stored for that provider.")
    row.is_active = False
    row.encrypted_key = ""
    await session.commit()
    return {"provider": provider, "removed": "true"}
