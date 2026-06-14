import uuid

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID

from src.api.data.clients.postgres.database import Base


class QuizQuestionResponse(Base):
    __tablename__ = "quizquestionresponses"

    response_id = Column(
        "responseid", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    attempt_id = Column(
        "attemptid",
        UUID(as_uuid=True),
        ForeignKey("quizattempts.attemptid", ondelete="RESTRICT"),
        nullable=False,
    )
    question_id = Column(
        "questionid",
        UUID(as_uuid=True),
        ForeignKey("quizquestions.questionid", ondelete="RESTRICT"),
        nullable=False,
    )
    trainee_id = Column(
        "traineeid",
        UUID(as_uuid=True),
        ForeignKey("trainees.traineeid", ondelete="RESTRICT"),
        nullable=False,
    )
    selected_option = Column("selectedoption", String(1), nullable=True)
    is_correct = Column("iscorrect", Boolean, nullable=True)
    attempt_count = Column("attemptcount", Integer, nullable=False, default=0)
    hint_level_reached = Column("hintlevelreached", Integer, nullable=False, default=0)
    was_skipped = Column("wasskipped", Boolean, nullable=False, default=False)
    was_locked = Column("waslocked", Boolean, nullable=False, default=False)
    responded_at = Column("respondedat", TIMESTAMP(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "attemptid", "questionid", name="uq_quizquestionresponses_attempt_question"
        ),
    )
