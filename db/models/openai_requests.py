from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Integer, ForeignKey
from sqlalchemy.orm import mapped_column, Mapped, relationship

from .. import Base


class OpenAIRequests(Base):
    __tablename__ = "openai_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    created_dt: Mapped[datetime]

    prompt_tokens: Mapped[int]
    completion_tokens: Mapped[Optional[int]]
    user_bot_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("accounts.id"))
