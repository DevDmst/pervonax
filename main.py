import asyncio
import logging
import math
import os
import random
from datetime import datetime, timedelta

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

DATA_MAILING_TXT = "data/mailing.txt"
PATH_TO_FIRST_NAME_FILE = "data/profiles_info/first_names.txt"
PATH_TO_LAST_NAME_FILE = "data/profiles_info/last_names.txt"
PATH_TO_ABOUT_FILE = "data/profiles_info/about.txt"
PATH_TO_CHANNELS_FILE = "data/channels.txt"

PATH_TO_PHOTOS = "data/profiles_info/photos"

mode = ""


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


async def unsubscribe_all(user_bots: list[UserBot]):
    logging.info("Начинаю отписку")
    unsubscribe_tasks = []
    for user_bot in user_bots:
        unsubscribe_tasks.append(
            asyncio.create_task(user_bot.unsubscribe_all())
        )

    await asyncio.gather(*unsubscribe_tasks)
    logging.info("Отписка завершена")


async def subscribe_all(channels: list[str], active_user_bots: list[UserBot]):
    channels_per_acc = len(channels) / len(active_user_bots)
    secs_per_channel = int((sum(settings.delay_between_subscriptions) / 2))
    secs = math.ceil(channels_per_acc * secs_per_channel)
    working_time = str(timedelta(seconds=secs))
    logging.info("Начинаю подписку на каналы.\n"
                 f"Примерное время ожидания завершения: {working_time}\n")

    iterator = utils.cyclic_iterator(active_user_bots)
    number_of_user_bots = len(active_user_bots)

    if math.ceil(len(channels) / len(active_user_bots)) > settings.max_chat_on_acc:
        raise ValueError(f"Слишком много каналов для подписки,"
                         f" максимальное количество каналов на 1 аккаунт - {settings.max_chat_on_acc}")

    async with Session() as db_session:
        for i, channel in enumerate(channels):
            counter = 0
            while True:
                if counter > number_of_user_bots:
                    raise Exception("Все аккаунты уже были использованы в подписках")
                user_bot = next(iterator)
                if not await AccountsChatsRepo.is_subscribed(user_bot.db_acc_id, channel, db_session):
                    break
                counter += 1

            await AccountsChatsRepo.add_one({
                "account_id": user_bot.db_acc_id,
                "chat_link": channel,
            }, db_session)

            await user_bot.subscribe_queue.put(channel)
            # logging.info(f"Аккаунт {user_bot.account_name} -- канал {channel}")

    while True:
        flag = True
        for user_bot in active_user_bots:
            is_finish = user_bot.subscribe_queue.empty() and not user_bot.process_subscribe_pending
            flag *= is_finish
        if flag:
            break
        await asyncio.sleep(1)

    logging.info("Подписка завершена.\n")


async def edit_all(user_bots: list[UserBot]):
    logging.info("Начинаю редактирование аккаунтов\n")
    tasks = []
    for i, user_bot in enumerate(user_bots):
        profile_info = get_random_profile_info(PATH_TO_PHOTOS,
                                               PATH_TO_FIRST_NAME_FILE,
                                               PATH_TO_LAST_NAME_FILE,
                                               PATH_TO_ABOUT_FILE)

        async def change_profile(user_bot_, profile_info_param):
            await user_bot_.edit_profile(*profile_info_param)
            await TelegramAccountsRepo.set_edited(user_bot_.db_acc_id)

        tasks.append(
            asyncio.ensure_future(change_profile(user_bot, profile_info))
        )

    await asyncio.gather(*tasks)
    logging.info("Аккаунты отредактированы\n")


def run_pervonax(user_bots: list[UserBot]):
    for user_bot in user_bots:
        user_bot.run_writing_comments()

    logging.info("Написание комментариев активировано")


def rm_chat(channels: list[str], chat_link: str):
    channels.remove(chat_link)
    utils.save_file(PATH_TO_CHANNELS_FILE, channels)


async def main():
    logging.info("Аккаунты запускаются.. ожидайте..")
    await create_tables()

    counter = [0]
    tg_sessions = utils.get_sessions(PATH_TO_SESSIONS_FOLDER)
    proxies = utils.get_proxies(PATH_TO_PROXY_FILE, settings.type_proxy)
    channels = utils.get_channels(PATH_TO_CHANNELS_FILE)
    active_user_bots = []
    accounts = []

    message_generator = MessageGenerator(DATA_MAILING_TXT)
    notifier = Notifier(config.bot_token)

    async with Session() as db_session:
        # добавляем прокси в бд
        for proxy in proxies:
            if not await ProxiesRepo.exist(proxy, db_session):
                await ProxiesRepo.add_one(proxy, db_session)

        proxies_db = await ProxiesRepo.get_all(db_session)

        for name, tg_session in tg_sessions.items():
            acc = await TelegramAccountsRepo.get_by_name(name, db_session)
            if not acc:
                acc = await TelegramAccountsRepo.add_one({"session_name": name}, db_session)

            proxy = None
            if settings.use_proxy:
                proxy = await acc.awaitable_attrs.proxy
                if not proxy:
                    proxy = utils.get_next(proxies_db, counter)
                    acc.proxy_id = proxy.id
                    await db_session.commit()
                proxy = proxy.to_dict()

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
                rm_chat=rm_chat
            )
            me = await user_bot.start()
            if me:
                active_user_bots.append(user_bot)
                accounts.append(acc)
                acc.active = True
                acc.tg_id = me.id
                await db_session.commit()
                user_bot.tg_id = me.id
            else:
                logging.info(f"Не удалось запустить сессию {name}")
                acc.active = False
                await db_session.commit()

    while True:
        await asyncio.sleep(0.1)  # для того, чтобы текст в консоли успел отобразиться
        point = input("\nВыберите пункт:"
                      "\n1. Отредактировать все профили"
                      "\n2. Отписаться от всего"
                      "\n3. Подписаться на каналы"
                      "\n4. Отписаться от всего и подписаться на каналы из channels.txt"
                      "\n5. Первонах\n")
        if point == "1":
            await edit_all(active_user_bots)
            logging.info("Аккаунты завершили редактирование")

        elif point == "2":
            await unsubscribe_all(active_user_bots)
            await notifier.notify(config.admin_id, "Аккаунты завершили отписку")

        elif point == "3":
            try:
                await subscribe_all(channels, active_user_bots)
            except Exception as e:
                logging.exception(e)
            await notifier.notify(config.admin_id, "Аккаунты завершили подписку")

        elif point == "4":
            await unsubscribe_all(active_user_bots)
            try:
                await subscribe_all(channels, active_user_bots)
            except Exception as e:
                logging.exception(e)
            await notifier.notify(config.admin_id, "Аккаунты завершили подписку")

        elif point == "5":
            run_pervonax(active_user_bots)
            break
        else:
            raise ValueError("Неверный аргумент. Выберите один из пунктов")


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.create_task(main())
    loop.run_forever()
