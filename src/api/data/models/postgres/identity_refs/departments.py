"""Minimal stub — departments table is owned by Identity & Spaces Service."""

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import UUID

from src.api.data.clients.postgres import Base


class Department(Base):
    """Registered so SQLAlchemy can resolve FK targets on e_spaces."""

    __tablename__ = "departments"

    department_id = Column("departmentid", UUID(as_uuid=True), primary_key=True)
