import uuid

from sqlalchemy import Column, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

from src.api.data.clients.postgres import Base
from src.api.utils.common_utils import utc_now


class StudyMaterialBatchRun(Base):
    __tablename__ = "studymaterialbatchruns"

    batch_id = Column(
        "batchid", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
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
    status = Column(String(20), nullable=False, default="queued")
    queue_position = Column("queueposition", Integer, nullable=False)
    selected_root_node_ids = Column(
        "selectedrootnodeids", JSONB, nullable=False, default=list
    )
    policy = Column("policy", JSONB, nullable=False, default=dict)
    total_items = Column(
        "totalitems", Integer, nullable=False, default=0, server_default="0"
    )
    completed_items = Column(
        "completeditems", Integer, nullable=False, default=0, server_default="0"
    )
    failed_items = Column(
        "faileditems", Integer, nullable=False, default=0, server_default="0"
    )
    skipped_items = Column(
        "skippeditems", Integer, nullable=False, default=0, server_default="0"
    )
    current_item_id = Column(
        "currentitemid",
        UUID(as_uuid=True),
        ForeignKey("studymaterialbatchitems.itemid", ondelete="SET NULL"),
        nullable=True,
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

    __table_args__ = (
        Index(
            "ix_studymaterialbatchruns_space_status_queue",
            "spaceid",
            "status",
            "queueposition",
        ),
        Index(
            "ix_studymaterialbatchruns_mentor_space_status",
            "mentorid",
            "spaceid",
            "status",
        ),
    )


class StudyMaterialBatchItem(Base):
    __tablename__ = "studymaterialbatchitems"

    item_id = Column("itemid", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_id = Column(
        "batchid",
        UUID(as_uuid=True),
        ForeignKey("studymaterialbatchruns.batchid", ondelete="CASCADE"),
        nullable=False,
    )
    node_id = Column(
        "nodeid",
        UUID(as_uuid=True),
        ForeignKey("topicnodes.nodeid", ondelete="RESTRICT"),
        nullable=False,
    )
    root_segment_node_id = Column(
        "rootsegmentnodeid",
        UUID(as_uuid=True),
        ForeignKey("topicnodes.nodeid", ondelete="RESTRICT"),
        nullable=False,
    )
    position = Column(Integer, nullable=False)
    depth_level = Column("depthlevel", Integer, nullable=False)
    path_node_ids = Column("pathnodeids", JSONB, nullable=False, default=list)
    path_titles = Column("pathtitles", JSONB, nullable=False, default=list)
    node_title = Column("nodetitle", String(300), nullable=False)
    status = Column(String(20), nullable=False, default="queued")
    generation_run_id = Column(
        "generationrunid",
        UUID(as_uuid=True),
        ForeignKey("generationruns.runid", ondelete="SET NULL"),
        nullable=True,
    )
    version_id = Column(
        "versionid",
        UUID(as_uuid=True),
        ForeignKey("studymaterialversions.versionid", ondelete="SET NULL"),
        nullable=True,
    )
    error_message = Column("errormessage", Text, nullable=True)
    completed_at = Column("completedat", TIMESTAMP(timezone=True), nullable=True)
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

    __table_args__ = (
        Index("ix_studymaterialbatchitems_batch_position", "batchid", "position"),
    )
