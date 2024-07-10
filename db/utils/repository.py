from abc import ABC, abstractmethod

from sqlalchemy import insert, select, delete, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from .. import Session


class AbstractRepository(ABC):
    @abstractmethod
    async def add_one(self, **kwargs):
        raise NotImplementedError

    @abstractmethod
    async def delete_one(self, **kwargs):
        raise NotImplementedError

    @abstractmethod
    async def get_all(self, **kwargs):
        raise NotImplementedError

    @abstractmethod
    async def get_quantity(self, **kwargs):
        raise NotImplementedError


class SQLAlchemyRepository(AbstractRepository):
    model = None

    @classmethod
    async def add_one(cls, data: dict, session: AsyncSession):
        instance = cls.model(**data)
        session.add(instance)
        await session.flush()
        await session.commit()
        return instance

    @classmethod
    async def add_many(cls, data: list[dict], session: AsyncSession):
        items = []
        for item in data:
            instance = cls.model(**item)
            session.add(instance)
            items.append(instance)
        await session.flush()
        await session.commit()
        return items

    @classmethod
    async def get_one(cls, item_id: int, session: AsyncSession):
        return await session.get(cls.model, item_id)

    @classmethod
    async def delete_one(cls, item_id: int, session: AsyncSession):
        item = await session.get(cls.model, item_id)
        if item:
            await session.delete(item)
            await session.commit()

    @classmethod
    async def get_all(cls, session: AsyncSession):
        stmt = select(cls.model)
        return (await session.scalars(stmt)).all()

    @classmethod
    async def delete_all(cls, session: AsyncSession):
        await session.execute(text(f"DELETE FROM {cls.model.__tablename__}"))

    @classmethod
    async def get_quantity(cls, session: AsyncSession):
        return await session.scalar(
            select(func.count())
            .select_from(cls.model)
        )
