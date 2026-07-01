import uuid

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from src.api.data.clients.postgres import Base


class QuizQuestion(Base):
    __tablename__ = "quizquestions"

    question_id = Column(
        "questionid", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    quiz_id = Column(
        "quizid",
        UUID(as_uuid=True),
        ForeignKey("quizzes.quizid", ondelete="RESTRICT"),
        nullable=False,
    )
    node_id = Column(
        "nodeid",
        UUID(as_uuid=True),
        ForeignKey("topicnodes.nodeid", ondelete="RESTRICT"),
        nullable=False,
    )
    question_text = Column("questiontext", Text, nullable=False)
    option_a = Column("optiona", Text, nullable=False)
    option_b = Column("optionb", Text, nullable=False)
    option_c = Column("optionc", Text, nullable=True)
    option_d = Column("optiond", Text, nullable=True)
    correct_option = Column("correctoption", String(1), nullable=False)
    hint_1 = Column("hint1", Text, nullable=True)
    hint_2 = Column("hint2", Text, nullable=True)
    hint_3 = Column("hint3", Text, nullable=True)
    explanation = Column(Text, nullable=True)
    order_index = Column("orderindex", Integer, nullable=False)
    is_active = Column("isactive", Boolean, nullable=False, default=True)
    source = Column(String(20), nullable=False, default="ai_generated")
