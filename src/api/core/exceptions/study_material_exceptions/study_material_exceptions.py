# C:\CapStone\study_agent_service\src\api\core\exceptions\study_material_exceptions\study_material_exceptions.py
from fastapi import HTTPException, status


class StudyMaterialNotFoundException(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="We could not find that study material version.",
        )


class StudyMaterialNoActiveVersionException(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This topic has no active draft to work on. "
                "Generate a new draft or restore one from your archive."
            ),
        )


class StudyMaterialNoPublishedVersionException(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No published study material is available for students on this topic yet.",
        )


class StudyMaterialVersionAlreadyPublishedException(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="This version is already live for students.",
        )


class StudyMaterialPublishBlockedSpaceUnpublishedException(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "ESPACE_NOT_PUBLISHED",
                "message": (
                    "Publish this course space first before making topic content "
                    "visible to students. Individual topics cannot go live while "
                    "the space is unpublished."
                ),
            },
        )


class StudyMaterialVersionNotPublishedException(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="This version is not live for students, so it cannot be removed from them.",
        )


class StudyMaterialVersionMismatchException(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That study material version does not belong to this topic.",
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
            detail="This draft is already in your archive.",
        )


class StudyMaterialVersionNotArchivedException(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="This draft is not in your archive, so it cannot be restored from there.",
        )


class StudyMaterialCannotArchivePublishedException(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "You cannot archive material that is live for students. "
                "Remove it from students first if you no longer want it visible."
            ),
        )


class StudyMaterialCannotArchiveNonDraftException(HTTPException):
    """M12: mentor archive applies only to WIP drafts, not student-history rows."""

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Only unpublished drafts can be moved to your archive. "
                "Older versions that students can still read in Previous versions "
                "cannot be archived this way—use Remove from students instead."
            ),
        )


class StudyMaterialCannotUnarchiveTraineeHistoryException(HTTPException):
    """M12: trainee lifecycle archive rows must not re-enter the mentor workspace."""

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This version is kept for students in Previous versions and "
                "cannot be restored to your working drafts. Publish it again if "
                "you want students to see it as the live version."
            ),
        )


class StudyMaterialReferenceParseMissingException(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "A reference PDF was attached, but its text is not available yet. "
                "Run Generate again with the reference PDF attached."
            ),
        )


class StudyMaterialClearDraftsBlockedByQuizException(HTTPException):
    def __init__(self, quiz_count: int = 1) -> None:
        noun = "quiz" if quiz_count == 1 else "quizzes"
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"This topic still has {quiz_count} {noun}. "
                "Delete or unpublish the quiz before discarding study material drafts."
            ),
        )


class StudyMaterialNoDraftsException(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "There are no unpublished drafts to discard. "
                "Restore a draft from your archive or generate new material."
            ),
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
            detail="We could not create the PDF. Please try again.",
        )


class StudyMaterialPublishBlockedReferenceMaterialRequiredException(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "This draft still needs a reference PDF before it can go live "
                "for students. Add the reference and generate the material first."
            ),
        )


class StudyMaterialModificationBlockedReferenceMaterialRequiredException(HTTPException):
    def __init__(self, action: str = "modify") -> None:
        verb = action.replace("_", " ")
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"You cannot {verb} this study material yet because a reference PDF "
                "is required. Upload the reference PDF and generate the material first."
            ),
        )


class StudyMaterialArchiveNotAvailableException(HTTPException):
    """Raised when archive access is blocked (no active SM on node)."""

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="There are no previous versions for students to view on this topic.",
        )


class StudyMaterialVersionNotInStudentArchiveException(HTTPException):
    """Raised when a trainee requests a version that is not in Previous versions."""

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="That version is not available in Previous versions for students.",
        )
