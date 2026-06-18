# C:\CapStone\study_agent_service\src\api\core\exceptions\study_material_exceptions\study_material_exceptions.py
from fastapi import HTTPException, status


class StudyMaterialNotFoundException(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Study material version not found.",
        )


class StudyMaterialNoActiveVersionException(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="No active study material version exists for this node.",
        )


class StudyMaterialNoPublishedVersionException(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No published study material is available for this node.",
        )


class StudyMaterialVersionAlreadyPublishedException(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="This study material version is already published.",
        )


class StudyMaterialPublishBlockedSpaceUnpublishedException(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "ESPACE_NOT_PUBLISHED",
                "message": (
                    "Re-publish this space first to make content visible to trainees. "
                    "Individual content cannot be published while the space is unpublished."
                ),
            },
        )


class StudyMaterialVersionNotPublishedException(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="This study material version is not published.",
        )


class StudyMaterialVersionMismatchException(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Study material version does not belong to this node.",
        )


class LLMGenerationFailedException(HTTPException):
    def __init__(self, detail: str | None = None) -> None:
        super().__init__(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=detail or "Study material generation failed. Please try again.",
        )


class StudyMaterialVersionAlreadyArchivedException(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="This study material version is already archived.",
        )


class StudyMaterialVersionNotArchivedException(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="This study material version is not archived.",
        )


class StudyMaterialCannotArchivePublishedException(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="Published versions cannot be archived. Unpublish is not supported.",
        )


class StudyMaterialReferenceParseMissingException(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Reference material was used for this node but parsed content is not "
                "stored. Run a fresh generate with the reference PDF first."
            ),
        )


class StudyMaterialClearDraftsBlockedByQuizException(HTTPException):
    def __init__(self, quiz_count: int = 1) -> None:
        noun = "quiz" if quiz_count == 1 else "quizzes"
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"This topic has {quiz_count} {noun}. "
                "Delete the quiz first before clearing study material drafts."
            ),
        )


class StudyMaterialNoDraftsException(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No study material drafts exist for this topic.",
        )


class StudyMaterialPublishTransactionFailedException(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error_code": "PUBLISH_TRANSACTION_FAILED",
                "message": "Something went wrong. No changes were made. Please try again.",
            },
        )


class StudyMaterialUnpublishTransactionFailedException(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error_code": "UNPUBLISH_TRANSACTION_FAILED",
                "message": "Something went wrong. No changes were made. Please try again.",
            },
        )


class StudyMaterialPdfGenerationFailedException(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate study material PDF. Please try again.",
        )


class StudyMaterialPublishBlockedReferenceMaterialRequiredException(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot publish a study material version that requires reference material.",
        )


class StudyMaterialModificationBlockedReferenceMaterialRequiredException(HTTPException):
    def __init__(self, action: str = "modify") -> None:
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot {action} study material when reference material is required. Please upload reference material first.",
        )
