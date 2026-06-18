import uuid

from sqlalchemy import Column, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from src.api.data.clients.postgres.database import Base


class NodeMedia(Base):
    __tablename__ = "nodemedia"

    media_id = Column(
        "mediaid", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
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
    media_type = Column("mediatype", String(20), nullable=False)
    title = Column(String(300), nullable=True)
    url = Column(Text, nullable=True)
    file_url = Column("fileurl", Text, nullable=True)
    order_index = Column("orderindex", Integer, nullable=False, default=0)
    uploaded_by = Column(
        "uploadedby",
        UUID(as_uuid=True),
        ForeignKey("mentors.mentorid", ondelete="RESTRICT"),
        nullable=False,
    )
