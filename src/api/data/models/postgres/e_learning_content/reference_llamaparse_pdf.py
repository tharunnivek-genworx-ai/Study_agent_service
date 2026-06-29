import uuid

from sqlalchemy import Column, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

from src.api.data.clients.postgres import Base
from src.api.utils.common_utils import utc_now


class ReferenceLlamaParsePdf(Base):
    __tablename__ = "referencellamaparsepdf"
    __table_args__ = (
        UniqueConstraint(
            "referencematerialid",
            "nodeid",
            name="uq_referencellamaparsepdf_material_node",
        ),
    )

    llamaparse_pdf_id = Column(
        "llamaparsepdfid", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    reference_material_id = Column(
        "referencematerialid",
        UUID(as_uuid=True),
        ForeignKey("referencematerials.materialid", ondelete="RESTRICT"),
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
    llama_parse_job_id = Column("llamaparsejobid", String(200), nullable=False)
    llama_parse_parse_job_id = Column(
        "llamaparseparsejobid", String(200), nullable=True
    )
    content_hash = Column("contenthash", String(64), nullable=False, index=True)
    structured_json = Column("structuredjson", JSONB, nullable=False)
    formatted_text = Column("formattedtext", Text, nullable=False)
    parsed_by = Column(
        "parsedby",
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
