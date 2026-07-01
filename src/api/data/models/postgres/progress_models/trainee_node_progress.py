import uuid

from sqlalchemy import (
    Boolean,
    Column,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID

from src.api.data.clients.postgres import Base
from src.api.utils.common_utils import utc_now


class TraineeNodeProgress(Base):
    __tablename__ = "traineenodeprogress"

    progress_id = Column(
        "progressid", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    trainee_id = Column(
        "traineeid",
        UUID(as_uuid=True),
        ForeignKey("trainees.traineeid", ondelete="RESTRICT"),
        nullable=False,
    )
    node_id = Column(
        "nodeid",
        UUID(as_uuid=True),
        ForeignKey("topicnodes.nodeid", ondelete="RESTRICT"),
        nullable=False,
    )
    space_id = Column(
        "spaceid",
        UUID(as_uuid=True),
        ForeignKey("espaces.spaceid", ondelete="RESTRICT"),
        nullable=False,
    )
    study_material_viewed = Column(
        "studymaterialviewed", Boolean, nullable=False, default=False
    )
    first_viewed_at = Column("firstviewedat", TIMESTAMP(timezone=True), nullable=True)
    last_viewed_at = Column("lastviewedat", TIMESTAMP(timezone=True), nullable=True)
    study_material_read_percent = Column(
        "studymaterialreadpercent", Integer, nullable=False, default=0
    )
    study_material_completed = Column(
        "studymaterialcompleted", Boolean, nullable=False, default=False
    )
    quiz_best_score = Column("quizbestscore", Float, nullable=True)
    quiz_attempt_count = Column("quizattemptcount", Integer, nullable=False, default=0)
    quiz_passed = Column("quizpassed", Boolean, nullable=False, default=False)
    chat_session_count = Column("chatsessioncount", Integer, nullable=False, default=0)
    completion_status = Column(
        "completionstatus", String(20), nullable=False, default="not_started"
    )
    updated_at = Column(
        "updatedat",
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    __table_args__ = (
        UniqueConstraint(
            "traineeid", "nodeid", name="uq_traineenodeprogress_trainee_node"
        ),
    )
