import asyncio
import logging
import os
import random
from datetime import datetime

from config_and_settings import config, settings
from db import Session
from db.repositories import AccountsChatsRepo
from db.repositories.accounts import TelegramAccountsRepo
from db.repositories.chats import ChatsRepo
from db.repositories.proxies import ProxiesRepo
from db.utils.utils import create_tables
from services.message_generator import MessageGenerator
from services.notifier import Notifier
from user_bot.user_bot import UserBot
import utils

PATH_TO_SESSIONS_FOLDER = "sessions"
PATH_TO_PROXY_FILE = "data/proxy.txt"

PATH_TO_FIRST_NAME_FILE = "data/profiles_info/first_names.txt"
PATH_TO_LAST_NAME_FILE = "data/profiles_info/last_names.txt"
PATH_TO_ABOUT_FILE = "data/profiles_info/about.txt"
PATH_TO_CHANNELS_FILE = "data/channels.txt"

PATH_TO_PHOTOS = "data/profiles_info/photos"


def get_random_profile_info(photos: str, first_names: str, last_names: str, about: str):
    photo = random.choice(os.listdir(photos))
    photo = os.path.join(photos, photo)
    with open(first_names, encoding="utf8") as f:
        first_name = random.choice(f.readlines())
    with open(last_names, encoding="utf8") as f:
        last_name = random.choice(f.readlines())
    with open(about, encoding="utf8") as f:
        about = random.choice(f.readlines())
    return photo, first_name, last_name, about


async def main():
    logging.info("Скрипт запущен")
    await create_tables()

    counter = [0]
    tg_sessions = utils.get_sessions(PATH_TO_SESSIONS_FOLDER)
    proxies = utils.get_proxies(PATH_TO_PROXY_FILE, settings.type_proxy)
    channels = utils.get_channels(PATH_TO_CHANNELS_FILE)
    active_user_bots = []
    tasks = []

    message_generator = MessageGenerator("data/mailing.txt")
    notifier = Notifier(config.bot_token)

    async with Session() as db_session:
        for name, tg_session in tg_sessions.items():
            acc = await TelegramAccountsRepo.get_by_name(name, db_session)
            if not acc:
                acc = await TelegramAccountsRepo.add_one({"session_name": name}, db_session)

            proxy = None
            if settings.use_proxy:
                proxy = await acc.awaitable_attrs.proxy
                if not proxy:  # or not utils.is_dict_exist(proxy, proxies)
                    proxy = utils.get_next(proxies, counter)
                    proxy["account_id"] = acc.id
                    proxy = await ProxiesRepo.add_one(proxy, db_session)

            user_bot = UserBot(
                acc.id,
                account_name=acc.session_name,
                delay_between_subscriptions=settings.delay_between_subscriptions,
                delay_between_comments=settings.delay_between_comments,
                delay_before_comment=settings.delay_before_comment,
                admin_id=config.admin_id,
                message_generator=message_generator,
                notifier=notifier,
                session_path=tg_session["session"],
                json_path=tg_session["json"],
                api_id=config.api_id,
                api_hash=config.api_hash,
                proxy=proxy,
            )
            me = await user_bot.start()
            if me:
                active_user_bots.append(user_bot)
                acc.active = True
                acc.tg_id = me.id
                await db_session.commit()
                user_bot.tg_id = me.id

                if not acc.edited:
                    profile_info = get_random_profile_info(PATH_TO_PHOTOS,
                                                           PATH_TO_FIRST_NAME_FILE,
                                                           PATH_TO_LAST_NAME_FILE,
                                                           PATH_TO_ABOUT_FILE)

                    async def change_profile(profile_info_param):
                        await user_bot.edit_profile(*profile_info_param)
                        await TelegramAccountsRepo.set_edited(acc.id)

                    tasks.append(asyncio.ensure_future(change_profile(profile_info)))
            else:
                logging.info(f"Не удалось запустить сессию {name}")
                acc.active = False

        await asyncio.gather(*tasks)

        number_of_user_bots = len(active_user_bots)
        for i, channel in enumerate(channels):
            user_bot_index = i % number_of_user_bots
            user_bot = active_user_bots[user_bot_index]

            async def save_subscription(chat: str, data: tuple):
                if data:
                    async with Session() as _db_session:
                        data = {
                            "chat_type": data[0],
                            "id": data[2],
                            "date_added": datetime.utcnow(),
                            "title": data[1],
                            "invite_link": chat,
                            "subscribed": True,
                            "subscriber_id": user_bot.db_acc_id,
                        }
                        try:
                            await ChatsRepo.add_one(data, _db_session)
                            await AccountsChatsRepo.add_one({"chat_id": data[2], "account_id": acc.id}, _db_session)
                        except Exception as e:
                            logging.exception(e)

            if not user_bot.subscribe_observers:
                user_bot.subscribe_observers.append(save_subscription)

            if not await ChatsRepo.is_subscribed(channel, acc.id, db_session):
                await user_bot.subscribe_queue.put(channel)


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.create_task(main())
    loop.run_forever()
