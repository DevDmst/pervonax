import asyncio
import logging
import math
import os
import random
from datetime import datetime, timedelta

from aioconsole import ainput

from config_and_settings import config, settings
from db import Session
from db.repositories import AccountsChatsRepo
from db.repositories.accounts import TelegramAccountsRepo
from db.repositories.chats import ChatsRepo
from db.repositories.openai_requests import OpenAIRequestsRepo
from db.repositories.proxies import ProxiesRepo
from db.utils.utils import create_tables
from services.message_generator import MessageGenerator
from services.notifier import Notifier
from user_bot.user_bot import UserBot
import utils

import aioconsole

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


async def publish_new_story(story_link: str, active_user_bots: list[UserBot]):
    logging.info("Начинаю публиковать историю...")
    first_user_bot = active_user_bots[0]
    split = story_link.split("/")
    story_id = split[-1]
    user_id = split[-3]
    story, filename = await first_user_bot.get_story(int(story_id), user_id)
    for ub in active_user_bots:
        try:
            await ub.publish_story(story, filename)
            logging.info(f"Аккаунт: {ub.account_name} - История опубликована успешно")
        except Exception as e:
            logging.error(f"Аккаунт: {ub.account_name} - Не удалось опубликовать историю")
            logging.exception(e)
    try:
        os.remove(filename)
    except:
        pass


async def add_channel_to_black_list(acc_id: int, channel_id: int):
    async with Session() as session:
        await AccountsChatsRepo.set_ban(acc_id, channel_id, session)


async def save_chat_call(acc_id: int, channel: str, channel_id: int):
    async with Session() as session:
        await AccountsChatsRepo.set_tg_id(acc_id, channel, channel_id, session)


async def main():
    logging.info("Аккаунты запускаются.. ожидайте..")
    await create_tables()

    counter = [0]
    tg_sessions = utils.get_sessions(PATH_TO_SESSIONS_FOLDER)
    proxies = utils.get_proxies(PATH_TO_PROXY_FILE, settings.type_proxy)
    channels = utils.get_channels(PATH_TO_CHANNELS_FILE)
    active_user_bots = []
    accounts = []

    message_generator = MessageGenerator(DATA_MAILING_TXT,
                                         config.openai_token,
                                         settings.promts,
                                         proxies[0])
    notifier = Notifier(config.bot_token)

    def rm_chat(chat_link: str):
        channels.remove(chat_link)
        utils.save_file(PATH_TO_CHANNELS_FILE, channels)

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
                rm_chat=rm_chat,
                new_ch_blacklist_call=add_channel_to_black_list,
                save_chat_call=save_chat_call,
                use_ai_for_generate_message=settings.use_ai_for_generate_message,
            )
            me = await user_bot.start()
            if me:
                active_user_bots.append(user_bot)
                accounts.append(acc)
                acc.active = True
                acc.tg_id = me.id
                await db_session.commit()
                user_bot.blacklist = set(await AccountsChatsRepo.get_black_list(user_bot.db_acc_id, db_session))
                user_bot.tg_id = me.id
            else:
                logging.info(f"Не удалось запустить сессию {name}, перемещаю в bad_sessions")
                acc.active = False
                await user_bot.disconnect()
                session = tg_session.get("session", None)
                if session:
                    utils.move_file(session, user_bot.bad_sessions_folder)
                json_path = tg_session.get("json", None)
                if json_path:
                    utils.move_file(json_path, user_bot.bad_sessions_folder)
                logging.info(f"Account: {user_bot.account_name} is banned")
                await db_session.commit()

    while True:
        await asyncio.sleep(0.1)  # для того, чтобы текст в консоли успел отобразиться
        point = await ainput("\nВыберите пункт:"
                             "\n1. Отредактировать все профили"
                             "\n2. Узнать траты за текущий месяц"
                             "\n3. Опубликовать историю"
                             "\n4. Отписаться от всего"
                             "\n5. Подписаться на каналы"
                             "\n6. Отписаться от всего и подписаться на каналы из channels.txt"
                             "\n7. Первонах\n")
        if point == "1":
            await edit_all(active_user_bots)
            logging.info("Аккаунты завершили редактирование")

        elif point == "2":
            total_prompt_tokens, total_completion_tokens = await OpenAIRequestsRepo.get_sum_tokens()
            cost_promt = total_prompt_tokens / 1000 * settings.promt_token_price_1k
            cost_completion = total_completion_tokens / 1000 * settings.completion_token_price_1k
            print(f"Траты за этот месяц: {cost_completion + cost_promt}$")

        elif point == "3":
            story_link = await ainput("Введите ссылку на историю: ")
            story_link = story_link.strip()
            if story_link:
                await publish_new_story(story_link, active_user_bots)
                logging.info("Аккаунты опубликовали историю")
            else:
                logging.info("Ошибка: неверная ссылка")

        elif point == "4":
            await unsubscribe_all(active_user_bots)
            await notifier.notify(config.admin_id, "Аккаунты завершили отписку")

        elif point == "5":
            try:
                await subscribe_all(channels, active_user_bots)
            except Exception as e:
                logging.exception(e)
            await notifier.notify(config.admin_id, "Аккаунты завершили подписку")

        elif point == "6":
            await unsubscribe_all(active_user_bots)
            try:
                await subscribe_all(channels, active_user_bots)
            except Exception as e:
                logging.exception(e)
            await notifier.notify(config.admin_id, "Аккаунты завершили подписку")

        elif point == "7":
            if settings.timer_pervonax:
                dt_or_number: str = await ainput(
                    "Введите дату запуска (H:M d.m.Y) или кол-во часов от текущего момента\n")
                if not dt_or_number.split():
                    run_pervonax(active_user_bots)
                    break

                if utils.is_number(dt_or_number):  # кол-во часов
                    td = timedelta(hours=float(dt_or_number))
                elif dt := utils.is_datetime(dt_or_number):
                    if dt <= datetime.utcnow():
                        print("Дата должна быть больше текущего момента\n")
                        continue
                    td = dt - datetime.utcnow()
                else:
                    print("Ошибка формата\n")
                    continue
                print(f"Запущу первонах через {str(td)}\n")
                await asyncio.sleep(td.total_seconds())
            run_pervonax(active_user_bots)
            break
        else:
            logging.error("Неверный аргумент. Выберите один из пунктов")


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.create_task(main())
    loop.run_forever()
