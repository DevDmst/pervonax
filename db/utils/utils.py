import json

from sqlalchemy import TypeDecorator, String

from .. import engine, Base


class ListJson(TypeDecorator):
    impl = String

    def process_bind_param(self, value, dialect):
        if value is not None:
            return json.dumps(value, ensure_ascii=False)
        else:
            return "[]"

    def process_result_value(self, value, dialect):
        if value is not None:
            return json.loads(value)
        else:
            return []


async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def delete_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
