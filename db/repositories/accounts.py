from datetime import datetime, timedelta

from sqlalchemy import select, func, update, case
from sqlalchemy.ext.asyncio import AsyncSession

from .. import Session
from ..models.accounts import TelegramAccount
from ..utils.repository import SQLAlchemyRepository


class TelegramAccountsRepo(SQLAlchemyRepository):
    model = TelegramAccount

    @classmethod
    async def get_by_name(cls, name: str, session: AsyncSession) -> TelegramAccount:
        return await session.scalar(
            select(cls.model)
            .where(cls.model.session_name == name)
        )

    @classmethod
    async def set_edited(cls, acc_id: int):
        async with Session() as session:
            stmt = update(cls.model).where(cls.model.id == acc_id).values(edited=True)
            await session.execute(stmt)
            await session.commit()