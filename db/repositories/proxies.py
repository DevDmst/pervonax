from datetime import datetime, timedelta

from sqlalchemy import select, func, update, case
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.accounts import TelegramAccount
from ..models.proxies import Proxy
from ..utils.repository import SQLAlchemyRepository


class ProxiesRepo(SQLAlchemyRepository):
    model = Proxy

    # @classmethod
    # async def get_by_name(cls, name: str, session: AsyncSession) -> TelegramAccount:
    #     return await session.scalar(
    #         select(cls.model)
    #         .where(cls.model.session_name == name)
    #     )
