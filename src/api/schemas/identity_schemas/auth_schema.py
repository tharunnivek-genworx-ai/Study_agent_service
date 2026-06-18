# C:\CapStone\study_agent_service\src\api\schemas\identity_schemas\auth_schema.py
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class TokenPayload(BaseModel):
    """Decoded JWT payload validated on every protected request."""

    sub: UUID
    role: Literal["itadmin", "mentor", "trainee"]
    exp: int
    iat: int
    jti: str
