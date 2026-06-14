"""Minimal stub — trainees table is owned by Identity & Spaces Service."""

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import UUID

from src.api.data.clients.postgres.database import Base


class Trainee(Base):
    """Registered so SQLAlchemy can resolve FK targets on content models."""

    __tablename__ = "trainees"

    trainee_id = Column("traineeid", UUID(as_uuid=True), primary_key=True)
