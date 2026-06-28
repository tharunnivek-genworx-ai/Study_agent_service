import uuid

from sqlalchemy import Column, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

from src.api.data.clients.postgres.database import Base
from src.api.utils.common_utils.time import utc_now


class GenerationRun(Base):
    """Durable checkpoint for long-running study material, quiz, and hint pipelines."""

    __tablename__ = "generationruns"

    run_id = Column("runid", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pipeline = Column(String(30), nullable=False)
    resource_type = Column("resourcetype", String(20), nullable=False)
    resource_id = Column("resourceid", UUID(as_uuid=True), nullable=False)
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
    mentor_id = Column(
        "mentorid",
        UUID(as_uuid=True),
        ForeignKey("mentors.mentorid", ondelete="RESTRICT"),
        nullable=False,
    )
    status = Column(String(20), nullable=False, default="running")
    last_completed_node = Column("lastcompletednode", String(80), nullable=True)
    checkpoint_state = Column("checkpointstate", JSONB, nullable=True)
    request_params = Column("requestparams", JSONB, nullable=True)
    generation_mode = Column("generationmode", String(20), nullable=False)
    artifact_run_id = Column("artifactrunid", String(32), nullable=True)
    progress_step_index = Column(
        "progressstepindex", Integer, nullable=False, default=0, server_default="0"
    )
    error_message = Column("errormessage", Text, nullable=True)
    error_type = Column("errortype", String(80), nullable=True)
    next_llm_retry_at = Column(
        "nextllmretryat", TIMESTAMP(timezone=True), nullable=True
    )
    attempt_count = Column(
        "attemptcount", Integer, nullable=False, default=0, server_default="0"
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
    completed_at = Column("completedat", TIMESTAMP(timezone=True), nullable=True)
