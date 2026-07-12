import uuid

from sqlalchemy import Column, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

from src.api.data.clients.postgres import Base
from src.api.utils.common_utils import utc_now


class BatchJob(Base):
    __tablename__ = "batch_jobs"

    batch_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id = Column(
        UUID(as_uuid=True),
        ForeignKey("espaces.spaceid", ondelete="RESTRICT"),
        nullable=False,
    )
    mentor_id = Column(
        UUID(as_uuid=True),
        ForeignKey("mentors.mentorid", ondelete="RESTRICT"),
        nullable=False,
    )
    status = Column(String(20), nullable=False, default="pending")
    policy = Column(JSONB, nullable=False, default=dict)
    selected_root_node_ids = Column(JSONB, nullable=False, default=list)
    total_steps = Column(Integer, nullable=False, default=0, server_default="0")
    completed_steps = Column(Integer, nullable=False, default=0, server_default="0")
    failed_steps = Column(Integer, nullable=False, default=0, server_default="0")
    skipped_steps = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
    started_at = Column(TIMESTAMP(timezone=True), nullable=True)
    finished_at = Column(TIMESTAMP(timezone=True), nullable=True)

    __table_args__ = (Index("ix_batch_jobs_space_status", "space_id", "status"),)


class BatchJobStep(Base):
    __tablename__ = "batch_job_steps"

    step_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_id = Column(
        UUID(as_uuid=True),
        ForeignKey("batch_jobs.batch_id", ondelete="CASCADE"),
        nullable=False,
    )
    position = Column(Integer, nullable=False)
    node_id = Column(
        UUID(as_uuid=True),
        ForeignKey("topicnodes.nodeid", ondelete="RESTRICT"),
        nullable=False,
    )
    node_title = Column(Text, nullable=False)
    path_titles = Column(JSONB, nullable=False, default=list)
    depth_level = Column(Integer, nullable=False)
    root_segment_node_id = Column(
        UUID(as_uuid=True),
        ForeignKey("topicnodes.nodeid", ondelete="RESTRICT"),
        nullable=False,
    )
    status = Column(String(20), nullable=False, default="pending")
    generation_run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("generationruns.runid", ondelete="SET NULL"),
        nullable=True,
    )
    error_message = Column(Text, nullable=True)
    started_at = Column(TIMESTAMP(timezone=True), nullable=True)
    completed_at = Column(TIMESTAMP(timezone=True), nullable=True)

    __table_args__ = (Index("ix_batch_job_steps_batch_status", "batch_id", "status"),)
