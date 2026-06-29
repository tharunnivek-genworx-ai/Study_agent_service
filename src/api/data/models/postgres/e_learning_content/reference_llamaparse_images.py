import uuid

from sqlalchemy import Column, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from src.api.data.clients.postgres import Base


class ReferenceLlamaParseImage(Base):
    __tablename__ = "referencellamaparseimages"

    llamaparse_image_id = Column(
        "llamaparseimageid", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    llamaparse_pdf_id = Column(
        "llamaparsepdfid",
        UUID(as_uuid=True),
        ForeignKey("referencellamaparsepdf.llamaparsepdfid", ondelete="CASCADE"),
        nullable=False,
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
    title = Column(String(300), nullable=True)
    filename = Column(String(300), nullable=False)
    file_url = Column("fileurl", Text, nullable=False)
    source_page_number = Column("sourcepagenumber", Integer, nullable=True)
    figure_index_on_page = Column("figureindexonpage", Integer, nullable=True)
    parse_index = Column("parseindex", Integer, nullable=True)
    category = Column(String(50), nullable=True)
    order_index = Column("orderindex", Integer, nullable=False, default=0)
