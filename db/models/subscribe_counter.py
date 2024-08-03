from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Integer, ForeignKey
from sqlalchemy.orm import mapped_column, Mapped, relationship

from .. import Base


class SubscribeCounter(Base):
    __tablename__ = "subscribe_counter"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    number: Mapped[int] = mapped_column(Integer, default=0)