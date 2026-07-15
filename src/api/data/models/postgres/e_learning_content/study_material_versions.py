import uuid

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

from src.api.data.clients.postgres.database import Base
from src.api.utils.common_utils.time import utc_now


class StudyMaterialVersion(Base):
    __tablename__ = "studymaterialversions"

    version_id = Column(
        "versionid", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
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
    version_number = Column("versionnumber", Integer, nullable=False)
    content = Column(Text, nullable=False)
    generation_type = Column("generationtype", String(20), nullable=False)
    mentor_feedback_used = Column("mentorfeedbackused", Text, nullable=True)
    reference_material_id = Column(
        "referencematerialid",
        UUID(as_uuid=True),
        ForeignKey("referencematerials.materialid", ondelete="RESTRICT"),
        nullable=True,
    )
    based_on_version_id = Column(
        "basedonversionid",
        UUID(as_uuid=True),
        ForeignKey("studymaterialversions.versionid", ondelete="RESTRICT"),
        nullable=True,
    )
    llm_model_used = Column("llmmodelused", String(100), nullable=True)
    prompt_snapshot = Column("promptsnapshot", Text, nullable=True)
    token_usage = Column("tokenusage", Integer, nullable=True)
    is_active = Column("isactive", Boolean, nullable=False, default=False)
    is_published = Column("ispublished", Boolean, nullable=False, default=False)
    published_at = Column("publishedat", TIMESTAMP(timezone=True), nullable=True)
    published_by = Column(
        "publishedby",
        UUID(as_uuid=True),
        ForeignKey("mentors.mentorid", ondelete="RESTRICT"),
        nullable=True,
    )
    created_by = Column(
        "createdby",
        UUID(as_uuid=True),
        ForeignKey("mentors.mentorid", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at = Column(
        "createdat", TIMESTAMP(timezone=True), nullable=False, default=utc_now
    )
    is_archived = Column("isarchived", Boolean, nullable=False, default=False)
    archived_at = Column("archivedat", TIMESTAMP(timezone=True), nullable=True)
    archived_by = Column(
        "archivedby",
        UUID(as_uuid=True),
        ForeignKey("mentors.mentorid", ondelete="RESTRICT"),
        nullable=True,
    )
    lifecycle_status = Column(
        "lifecyclestatus", String(20), nullable=False, default="draft"
    )
    superseded_at = Column("supersededat", TIMESTAMP(timezone=True), nullable=True)
    qc_failed_permanently = Column(
        "qcfailedpermanently", Boolean, nullable=False, default=False
    )
    qc_result = Column("qcresult", JSONB, nullable=True)
    qc_passed = Column(
        "qcpassed", Boolean, nullable=False, server_default="false", default=False
    )
    qc_attempt_count = Column(
        "qcattemptcount", Integer, nullable=False, server_default="0", default=0
    )
    generation_run_id = Column("generationrunid", String(64), nullable=True)
    concept_plan = Column("conceptplan", JSONB, nullable=True)
    checklist_llm_model_used = Column(
        "checklistllmmodelused", String(100), nullable=True
    )
    qc_verification_mode = Column("qcverificationmode", String(20), nullable=True)
    qc_frozen_check_ids = Column("qcfrozencheckids", JSONB, nullable=True)
    qc_frozen_section_keys = Column("qcfrozensectionkeys", JSONB, nullable=True)
    qc_section_content_hashes = Column("qcsectioncontenthashes", JSONB, nullable=True)
    next_llm_retry_at = Column(
        "nextllmretryat", TIMESTAMP(timezone=True), nullable=True
    )
    generation_outcome = Column("generationoutcome", String(32), nullable=True)
    generation_outcome_detail = Column("generationoutcomedetail", JSONB, nullable=True)
    qc_evaluated = Column(
        "qcevaluated", Boolean, nullable=False, server_default="false", default=False
    )
