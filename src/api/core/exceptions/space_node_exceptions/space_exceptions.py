from fastapi import HTTPException, status


class SpaceNotFoundException(HTTPException):
    """Raised when a space_id does not exist or is not active."""

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="E-learning space not found.",
        )


class SpaceForbiddenException(HTTPException):
    """Raised when a mentor attempts to modify a space they do not own."""

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to modify this space.",
        )


class SpaceArchivedConflictException(HTTPException):
    """Raised when attempting to modify an archived space."""

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot modify an archived space.",
        )
