"""Minimal stub — mentors table is owned by Identity & Spaces Service."""

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import UUID

from src.api.data.clients.postgres import Base


class Mentor(Base):
    """Registered so SQLAlchemy can resolve FK targets on content models."""

    __tablename__ = "mentors"

    mentor_id = Column("mentorid", UUID(as_uuid=True), primary_key=True)
