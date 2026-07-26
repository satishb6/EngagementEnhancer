"""Sign up / sign in. Deliberately plain."""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select

from wire_api.auth.deps import DB, CurrentUser
from wire_api.auth.security import create_token, hash_password, verify_password
from wire_api.models import Entitlement, Tier, User, UserProtocol

router = APIRouter(prefix="/auth", tags=["auth"])


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    display_name: str = ""


class TokenResponse(BaseModel):
    token: str
    user_id: str
    email: str
    display_name: str
    tier: str


@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def signup(body: Credentials, session: DB) -> TokenResponse:
    existing = (
        await session.execute(select(User).where(User.email == body.email.lower()))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "That email already has an account.")
    user = User(
        email=body.email.lower(),
        password_hash=hash_password(body.password),
        display_name=body.display_name or body.email.split("@")[0],
    )
    session.add(user)
    await session.flush()
    session.add(Entitlement(user_id=user.id, tier=Tier.FREE))
    session.add(UserProtocol(user_id=user.id, name="My wire", is_default=True))
    await session.commit()
    return TokenResponse(
        token=create_token(user.id), user_id=str(user.id), email=user.email,
        display_name=user.display_name, tier=Tier.FREE.value,
    )


@router.post("/guest", status_code=status.HTTP_201_CREATED)
async def guest(session: DB) -> TokenResponse:
    """Anonymous-first entry: one click of nothing. Creates a full-featured
    guest account so there is no sign-in wall. Guests run on the BYOK tier
    (no platform credits involved) — the demo engine plus any keys they add
    in Studio → Engine."""
    import secrets

    suffix = secrets.token_hex(6)
    user = User(
        email=f"guest-{suffix}@guest.wire",
        password_hash=hash_password(secrets.token_urlsafe(24)),
        display_name=f"Guest {suffix[:4]}",
    )
    session.add(user)
    await session.flush()
    session.add(Entitlement(
        user_id=user.id, tier=Tier.BYOK,
        briefings_per_day=50, selections_per_day=999, variant_count=3,
        can_publish=True, can_video=True,
    ))
    session.add(UserProtocol(user_id=user.id, name="My wire", is_default=True))
    await session.commit()
    return TokenResponse(
        token=create_token(user.id), user_id=str(user.id), email=user.email,
        display_name=user.display_name, tier=Tier.BYOK.value,
    )


@router.post("/login")
async def login(body: Credentials, session: DB) -> TokenResponse:
    user = (
        await session.execute(select(User).where(User.email == body.email.lower()))
    ).scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email or password is wrong.")
    ent = (
        await session.execute(select(Entitlement).where(Entitlement.user_id == user.id))
    ).scalar_one_or_none()
    return TokenResponse(
        token=create_token(user.id), user_id=str(user.id), email=user.email,
        display_name=user.display_name, tier=ent.tier.value if ent else Tier.FREE.value,
    )


@router.get("/me")
async def me(user: CurrentUser, session: DB) -> dict[str, str]:
    ent = (
        await session.execute(select(Entitlement).where(Entitlement.user_id == user.id))
    ).scalar_one_or_none()
    return {
        "user_id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
        "mode": user.mode.value,
        "tier": ent.tier.value if ent else Tier.FREE.value,
    }
