# C:\CapStone\study_agent_service\src\api\core\exceptions\space_node_exceptions\node_exceptions.py
from fastapi import HTTPException, status


class NodeNotFoundException(HTTPException):
    """Raised when a node_id does not exist or does not belong to the given space."""

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Topic node not found.",
        )


class NodeForbiddenException(HTTPException):
    """Raised when a user lacks permission to access or modify a node."""

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to modify this node.",
        )
