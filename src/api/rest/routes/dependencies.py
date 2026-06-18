"""Shared FastAPI dependencies for the Study Agent Service."""

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.api.schemas.identity_schemas.auth_schema import TokenPayload
from src.api.utils.common_utils.tokens import decode_token

bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
) -> TokenPayload:
    payload = decode_token(
        credentials.credentials,
        expired_message="Access token has expired.",
        invalid_message="Access token is invalid.",
    )
    return TokenPayload(**payload)
