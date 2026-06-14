import uuid

from sqlalchemy import Boolean, Column, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID

from src.api.data.clients.postgres.database import Base
from src.api.utils.time import utc_now


class ESpace(Base):
    __tablename__ = "espaces"

    space_id = Column(
        "spaceid", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    space_name = Column("spacename", String(200), nullable=False)
    description = Column(Text, nullable=True)
    department_id = Column(
        "departmentid",
        UUID(as_uuid=True),
        ForeignKey("departments.departmentid", ondelete="RESTRICT"),
        nullable=False,
    )
    mentor_id = Column(
        "mentorid",
        UUID(as_uuid=True),
        ForeignKey("mentors.mentorid", ondelete="RESTRICT"),
        nullable=False,
    )
    transferred_to_mentor_id = Column(
        "transferredtomentorid",
        UUID(as_uuid=True),
        ForeignKey("mentors.mentorid", ondelete="RESTRICT"),
        nullable=True,
    )
    invite_code = Column("invitecode", String(20), nullable=True, unique=True)
    is_published = Column("ispublished", Boolean, nullable=False, default=False)
    is_active = Column("isactive", Boolean, nullable=False, default=True)
    created_at = Column(
        "createdat", TIMESTAMP(timezone=True), nullable=False, default=utc_now
    )
    updated_at = Column(
        "updatedat",
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
    archived_at = Column("archivedat", TIMESTAMP(timezone=True), nullable=True)
