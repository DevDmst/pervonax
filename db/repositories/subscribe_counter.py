from datetime import datetime, timedelta

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from .. import Session
from ..models.openai_requests import OpenAIRequests
from ..models.subscribe_counter import SubscribeCounter
from ..utils.repository import SQLAlchemyRepository


class SubscribeCountersRepo(SQLAlchemyRepository):
    model = SubscribeCounter

    @classmethod
    async def add_one_number(cls):
        async with Session() as session:
            stmt = select(cls.model).where(cls.model.id == 1)
            result = await session.scalar(stmt)
            result.number += 1
            await session.commit()

