from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.proxies import Proxy
from ..utils.repository import SQLAlchemyRepository


class ProxiesRepo(SQLAlchemyRepository):
    model = Proxy

    @classmethod
    async def exist(cls, proxy: dict, session: AsyncSession) -> bool:
        stmt = select(Proxy).where(
            cls.model.proxy_type == proxy['proxy_type'],
            cls.model.port == proxy['port'],
            cls.model.addr == proxy['addr'],
            cls.model.password == proxy['password'],
            cls.model.username == proxy['username'],
        )

        result = await session.scalars(stmt)
        return bool(len(result.all()))
