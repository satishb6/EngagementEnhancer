"""FastAPI auth dependencies."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from wire_api.auth.security import decode_token
from wire_api.db import get_session
from wire_api.models import Entitlement, User

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in to continue.")
    user_id = decode_token(creds.credentials)
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired. Sign in again.")
    user = (
        await session.execute(select(User).where(User.id == user_id, User.is_active.is_(True)))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account not found.")
    return user


async def get_entitlement(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Entitlement:
    ent = (
        await session.execute(select(Entitlement).where(Entitlement.user_id == user.id))
    ).scalar_one_or_none()
    if ent is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No entitlement record.")
    return ent


CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentEntitlement = Annotated[Entitlement, Depends(get_entitlement)]
DB = Annotated[AsyncSession, Depends(get_session)]
