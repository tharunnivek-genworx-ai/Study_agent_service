import uuid

from sqlalchemy import BigInteger, Boolean, Column, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID

from src.api.data.clients.postgres.database import Base
from src.api.utils.common_utils.time import utc_now


class ReferenceMaterial(Base):
    __tablename__ = "referencematerials"

    material_id = Column(
        "materialid", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
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
        nullable=True,
    )
    title = Column(String(300), nullable=False)
    file_url = Column("fileurl", Text, nullable=False)
    file_name = Column("filename", String(300), nullable=False)
    file_size_bytes = Column("filesizebytes", BigInteger, nullable=True)
    mime_type = Column("mimetype", String(100), nullable=False)
    scope = Column(String(20), nullable=False)
    is_visible_to_trainees = Column(
        "isvisibletotrainees", Boolean, nullable=False, default=True
    )
    uploaded_by = Column(
        "uploadedby",
        UUID(as_uuid=True),
        ForeignKey("mentors.mentorid", ondelete="RESTRICT"),
        nullable=False,
    )
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
    deleted_at = Column("deletedat", TIMESTAMP(timezone=True), nullable=True)
