from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime
from sqlalchemy.orm import mapped_column, Mapped, relationship

from .. import Base


class Chat(Base):
    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    chat_type: Mapped[Optional[str]]
    date_added: Mapped[datetime]
    title: Mapped[Optional[str]]
    invite_link: Mapped[str]

    subscribed: Mapped[bool] = mapped_column(default=False)
    subscriber_id: Mapped[Optional[int]] = mapped_column(BigInteger)

