from datetime import datetime, timedelta

from sqlalchemy import select, func, update, case
from sqlalchemy.ext.asyncio import AsyncSession

from .. import Chat
from ..models.accounts import TelegramAccount
from ..models.proxies import Proxy
from ..utils.repository import SQLAlchemyRepository


class ChatsRepo(SQLAlchemyRepository):
    model = Chat

    @classmethod
    async def is_subscribed(cls, chat: str, acc_id: int, session: AsyncSession) -> bool:
        stmt = select(cls.model.id).where(cls.model.invite_link == chat,
                                          cls.model.subscriber_id == acc_id)
        stmt_ = await session.scalar(stmt)
        return stmt_


