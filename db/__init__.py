import os

from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncAttrs


class Base(AsyncAttrs, DeclarativeBase):
    pass


os.makedirs("database", exist_ok=True)

db_url = f"sqlite+aiosqlite:///database/database.sqlite3"
engine = create_async_engine(url=db_url, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)

from .models import Proxy
from .models import TelegramAccount
from .models import Proxy
from .models import Chat
from .models import AccountsChats
