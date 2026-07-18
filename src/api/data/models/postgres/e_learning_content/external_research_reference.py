import uuid

from sqlalchemy import Column, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

from src.api.data.clients.postgres import Base
from src.api.utils.common_utils import utc_now


class ExternalResearchReference(Base):
    __tablename__ = "externalresearchreference"
    __table_args__ = (
        UniqueConstraint("nodeid", name="uq_externalresearchreference_node"),
    )

    external_research_id = Column(
        "externalresearchid", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
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
        index=True,
    )
    # 'success' | 'fail_soft'
    status = Column(String(20), nullable=False)
    fail_reason = Column("failreason", String(100), nullable=True)
    search_query_used = Column("searchqueryused", Text, nullable=True)
    resolved_topic = Column("resolvedtopic", Text, nullable=True)
    resolved_subtopic = Column("resolvedsubtopic", Text, nullable=True)
    # NULL when status='fail_soft'
    ground_truth_reference = Column("groundtruthreference", Text, nullable=True)
    # Only URLs that survived into the final merge
    source_urls = Column("sourceurls", JSONB, nullable=False, default=list)
    per_website_summary_count = Column(
        "perwebsitesummarycount", Integer, nullable=False, default=0
    )
    token_count = Column("tokencount", Integer, nullable=True)
    knowledge_distillation_model_used = Column(
        "knowledgedistillationmodelused", Text, nullable=True
    )
    requested_by = Column(
        "requestedby",
        UUID(as_uuid=True),
        ForeignKey("mentors.mentorid", ondelete="RESTRICT"),
        nullable=False,
    )
    # Write-once cache row — no updated_at (no refresh path in MVP)
    created_at = Column(
        "createdat", TIMESTAMP(timezone=True), nullable=False, default=utc_now
    )
