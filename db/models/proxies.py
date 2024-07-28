from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey
from sqlalchemy.orm import mapped_column, Mapped, relationship

from .. import Base


class Proxy(Base):
    __tablename__ = "proxies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    proxy_type: Mapped[str]
    addr: Mapped[str]
    port: Mapped[int]
    username: Mapped[str]
    password: Mapped[str]
    rdns: Mapped[bool]


    def to_dict(self):
        return {
            'proxy_type': self.proxy_type,
            'addr': self.addr,
            'port': self.port,
            'username': self.username,
            'password': self.password,
            'rdns': self.rdns
        }
