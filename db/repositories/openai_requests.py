from datetime import datetime, timedelta

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from .. import Session
from ..models.openai_requests import OpenAIRequests
from ..utils.repository import SQLAlchemyRepository


class OpenAIRequestsRepo(SQLAlchemyRepository):
    model = OpenAIRequests

    @classmethod
    async def add_request(cls, data: dict):
        async with Session() as session:
            instance = cls.model(**data)
            session.add(instance)
            await session.flush()
            await session.commit()
            return instance

    @classmethod
    async def get_sum_tokens(cls):
        async with Session() as session:
            now = datetime.now()
            start_date = datetime(now.year, now.month, 1, 0, 0, 0, 0)
            end_date = (start_date + timedelta(days=32)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)

            stmt = select(
                func.sum(OpenAIRequests.prompt_tokens).label('total_prompt_tokens'),
                func.sum(OpenAIRequests.completion_tokens).label('total_completion_tokens')
            ).filter(
                and_(
                    OpenAIRequests.created_dt >= start_date,
                    OpenAIRequests.created_dt < end_date
                )
            )
            result = (await session.execute(stmt)).one()

            total_prompt_tokens = result.total_prompt_tokens or 0
            total_completion_tokens = result.total_completion_tokens or 0

            return total_prompt_tokens, total_completion_tokens
