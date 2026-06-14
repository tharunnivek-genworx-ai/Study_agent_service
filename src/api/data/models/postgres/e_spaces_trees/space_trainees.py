import uuid

from sqlalchemy import Boolean, Column, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID

from src.api.data.clients.postgres.database import Base
from src.api.utils.time import utc_now


class SpaceTrainee(Base):
    __tablename__ = "spacetrainees"

    space_trainee_id = Column(
        "spacetraineeid", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    space_id = Column(
        "spaceid",
        UUID(as_uuid=True),
        ForeignKey("espaces.spaceid", ondelete="RESTRICT"),
        nullable=False,
    )
    trainee_id = Column(
        "traineeid",
        UUID(as_uuid=True),
        ForeignKey("trainees.traineeid", ondelete="RESTRICT"),
        nullable=False,
    )
    joined_via = Column("joinedvia", String(20), nullable=False)
    joined_at = Column(
        "joinedat", TIMESTAMP(timezone=True), nullable=False, default=utc_now
    )
    is_active = Column("isactive", Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint("spaceid", "traineeid", name="uq_spacetrainees_space_trainee"),
    )
