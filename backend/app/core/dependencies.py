from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import UnauthorizedError
from app.modules.authorization.application.ports import PolicyDecisionPoint
from app.modules.authorization.application.wave1_pdp import Wave1PolicyPDP
from app.modules.iam.application.ports import AuthContext, TokenValidator


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    factory = request.app.state.session_factory
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_token_validator(request: Request) -> TokenValidator:
    validator: TokenValidator = request.app.state.token_validator
    return validator


def get_pdp(request: Request) -> PolicyDecisionPoint:
    pdp: PolicyDecisionPoint = request.app.state.pdp
    return pdp


async def get_auth_context(
    request: Request,
    validator: Annotated[TokenValidator, Depends(get_token_validator)],
) -> AuthContext:
    header = request.headers.get("Authorization")
    if header is None or not header.startswith("Bearer "):
        raise UnauthorizedError("Authentication required")
    token = header.removeprefix("Bearer ").strip()
    if not token:
        raise UnauthorizedError("Authentication required")
    return await validator.validate(token)


DbSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentAuth = Annotated[AuthContext, Depends(get_auth_context)]
CurrentPDP = Annotated[PolicyDecisionPoint, Depends(get_pdp)]


def default_pdp() -> Wave1PolicyPDP:
    return Wave1PolicyPDP()
