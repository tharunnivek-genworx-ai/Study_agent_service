import uuid

from sqlalchemy import Column, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID

from src.api.data.clients.postgres.database import Base
from src.api.utils.time import utc_now


class QuizAttempt(Base):
    __tablename__ = "quizattempts"

    attempt_id = Column(
        "attemptid", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    quiz_id = Column(
        "quizid",
        UUID(as_uuid=True),
        ForeignKey("quizzes.quizid", ondelete="RESTRICT"),
        nullable=False,
    )
    trainee_id = Column(
        "traineeid",
        UUID(as_uuid=True),
        ForeignKey("trainees.traineeid", ondelete="RESTRICT"),
        nullable=False,
    )
    space_id = Column(
        "spaceid",
        UUID(as_uuid=True),
        ForeignKey("espaces.spaceid", ondelete="RESTRICT"),
        nullable=False,
    )
    node_id = Column(
        "nodeid",
        UUID(as_uuid=True),
        ForeignKey("topicnodes.nodeid", ondelete="RESTRICT"),
        nullable=False,
    )
    status = Column(String(20), nullable=False, default="in_progress")
    score = Column(Float, nullable=True)
    total_correct = Column("totalcorrect", Integer, nullable=True)
    total_with_hints = Column("totalwithhints", Integer, nullable=True)
    total_skipped = Column("totalskipped", Integer, nullable=True)
    started_at = Column(
        "startedat", TIMESTAMP(timezone=True), nullable=False, default=utc_now
    )
    submitted_at = Column("submittedat", TIMESTAMP(timezone=True), nullable=True)
