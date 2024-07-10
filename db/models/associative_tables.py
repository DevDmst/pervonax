from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, ForeignKey, Integer
from sqlalchemy.orm import mapped_column, Mapped

from .. import Base


class AccountsChats(Base):
    __tablename__ = "accounts_chats"
    account_id: Mapped[int] = mapped_column(Integer, ForeignKey('accounts.id'), primary_key=True)
    chat_id: Mapped[int] = mapped_column(Integer, ForeignKey('chats.id'), primary_key=True)

    banned: Mapped[bool] = mapped_column(default=False)
    banned_date: Mapped[Optional[datetime]]
