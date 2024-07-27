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
    async def set_ban(cls, acc_id: int, chat_id: int):
        async with Session() as session:
            stmt = select(cls.model).where(cls.model.chat_id == chat_id,
                                           cls.model.account_id == acc_id)

            item = await session.scalar(stmt)

            if not item:
                item = AccountsChats(account_id=acc_id, chat_id=chat_id, banned_date=datetime.utcnow(), banned=True)
                session.add(item)
            else:
                stmt = (update(cls.model)
                        .where(cls.model.chat_id == chat_id,
                               cls.model.account_id == acc_id)
                        .values(banned_date=datetime.utcnow(), banned=True))
                await session.execute(stmt)

            await session.commit()

    @classmethod
    async def get_quantity_by_account(cls, db_acc_id: int):
        pass #TODO

    @classmethod
    async def is_subscribed(cls, db_acc_id: int, channel: str, session: AsyncSession):
        stmt = (
            select(cls.model)
            .where(cls.model.account_id == db_acc_id, cls.model.chat_link == channel)
        )
        result = await session.scalars(stmt)
        return result.all()

