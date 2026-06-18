# C:\CapStone\study_agent_service\src\api\core\exceptions\identity_exceptions\auth_exceptions.py
from fastapi import HTTPException, status


class InvalidTokenException(HTTPException):
    """Raised when a JWT access token is missing, expired, or tampered."""

    def __init__(self, detail: str = "Token is invalid or expired.") -> None:
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


class InsufficientPermissionsException(HTTPException):
    """Raised when the authenticated user's role is not allowed to access the route."""

    def __init__(self, required_role: str = "") -> None:
        detail = (
            f"Access denied. Required role: {required_role}."
            if required_role
            else "You do not have permission to perform this action."
        )
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
        )
