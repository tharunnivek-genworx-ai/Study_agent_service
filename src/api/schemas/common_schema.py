# src/api/schemas/common_schema.py
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class Timestamped(BaseModel):
    """
    Base for any ORM-mapped response that carries created_at / updated_at.
    Aliases map snake_case Python fields to the lowercase column names
    that SQLAlchemy returns from asyncpg (createdat / updatedat).

    All content schemas that expose timestamps inherit from this.
    """

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )

    created_at: datetime = Field(..., alias="createdat")
    updated_at: datetime = Field(..., alias="updatedat")
