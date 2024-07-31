from datetime import datetime, timedelta

from sqlalchemy import select, func, update, case
from sqlalchemy.ext.asyncio import AsyncSession

from .. import Chat, AccountsChats, Session
from ..models.accounts import TelegramAccount
from ..models.proxies import Proxy
from ..utils.repository import SQLAlchemyRepository


class AccountsChatsRepo(SQLAlchemyRepository):
    model = AccountsChats

    @classmethod
    async def set_ban(cls, acc_id: int, chat_id: int, session: AsyncSession):
        stmt = (
            update(cls.model)
            .where(cls.model.chat_tg_id == chat_id,
                   cls.model.account_id == acc_id)
            .values(banned_date=datetime.utcnow(), banned=True)
        )
        await session.execute(stmt)
        await session.commit()

    @classmethod
    async def get_quantity_by_account(cls, db_acc_id: int):
        pass  # TODO

    @classmethod
    async def is_subscribed(cls, db_acc_id: int, channel: str, session: AsyncSession):
        stmt = (
            select(cls.model)
            .where(cls.model.account_id == db_acc_id, cls.model.chat_link == channel)
        )
        result = await session.scalars(stmt)
        return result.all()

    @classmethod
    async def get_black_list(cls, acc_id: int, session: AsyncSession):
        stmt = (
            select(cls.model.chat_tg_id)
            .where(cls.model.account_id == acc_id, cls.model.banned.is_(True))
        )
        result = await session.scalars(stmt)
        return result.all()

    @classmethod
    async def set_tg_id(cls, acc_id: int, channel: str, channel_id: int, session: AsyncSession):
        stmt = (
            update(cls.model)
            .where(cls.model.account_id == acc_id,
                   cls.model.chat_link == channel)
            .values(chat_tg_id=channel_id)
        )
        await session.execute(stmt)
        await session.commit()
