import uuid

from sqlalchemy import Column, Float, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import relationship

from src.api.data.clients.postgres.database import Base
from src.api.utils.common_utils.time import utc_now


class TraineeSpaceProgress(Base):
    __tablename__ = "traineespaceprogress"

    space_progress_id = Column(
        "spaceprogressid", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
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

    # Recomputed whenever nodes are added/archived or study material published/unpublished (EC-23)
    # COUNT of active nodes with >= 1 published study material version at any depth
    total_nodes = Column("totalnodes", Integer, nullable=False, default=0)
    # COUNT of nodes where trainee's completionstatus = 'completed'
    completed_nodes = Column("completednodes", Integer, nullable=False, default=0)
    # Average quizbestscore across all nodes the trainee has attempted
    overall_score_avg = Column("overallscoreavg", Float, nullable=True)

    last_activity_at = Column("lastactivityat", TIMESTAMP(timezone=True), nullable=True)
    updated_at = Column(
        "updatedat",
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    __table_args__ = (
        UniqueConstraint(
            "traineeid", "spaceid", name="uq_traineespaceprogress_trainee_space"
        ),
    )

    trainee = relationship("Trainee", foreign_keys=[trainee_id])
    space = relationship("ESpace", foreign_keys=[space_id])
