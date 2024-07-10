from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime
from sqlalchemy.orm import mapped_column, Mapped, relationship

from .. import Base


class TelegramAccount(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tg_id: Mapped[Optional[int]] = mapped_column(BigInteger)

    session_name: Mapped[str]
    edited: Mapped[bool] = mapped_column(default=False)

    active: Mapped[bool] = mapped_column(default=False)

    proxy: Mapped["Proxy"] = relationship("Proxy")

