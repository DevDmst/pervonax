import asyncio
import copy
import functools
import json
import logging
import os
import random
import re
import traceback
from asyncio import Task
from datetime import datetime, timedelta
from typing import Callable

from openai import APIConnectionError, AuthenticationError, RateLimitError
from telethon import TelegramClient, events, functions
from telethon.errors import AuthKeyDuplicatedError, UnauthorizedError, AuthKeyNotFound, UsernameInvalidError, \
    UsernameOccupiedError, UsernameNotModifiedError, FloodWaitError, InviteRequestSentError, \
    UserAlreadyParticipantError, ChannelPrivateError, PeerFloodError, UserBannedInChannelError, ChatWriteForbiddenError, \
    ForbiddenError, ChatAdminRequiredError, InviteHashExpiredError, ChatGuestSendForbiddenError, MsgIdInvalidError, \
    SlowModeWaitError, UserDeactivatedBanError, RPCError, UserDeactivatedError, AuthKeyUnregisteredError, \
    AuthKeyPermEmptyError
from telethon.tl import types
from telethon.tl.functions.account import UpdateProfileRequest, UpdateUsernameRequest
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest, CheckChatInviteRequest
from telethon.tl.functions.photos import DeletePhotosRequest, UploadProfilePhotoRequest
from telethon.tl.functions.stories import GetStoriesByIDRequest, SendStoryRequest
from telethon.tl.types import InputPhoto, ChatInviteAlready, Chat, Channel, PeerStories, InputPrivacyKeyStatusTimestamp, \
    InputPrivacyValueAllowContacts, InputPrivacyKeyProfilePhoto, InputPrivacyKeyAbout, InputPrivacyKeyPhoneNumber, \
    InputPrivacyKeyChatInvite, InputPrivacyKeyForwards, InputPrivacyKeyPhoneCall, InputPrivacyKeyPhoneP2P, \
    InputPrivacyKeyVoiceMessages, InputPrivacyKeyBirthday, InputPrivacyValueDisallowAll, InputPrivacyValueAllowAll, \
    TypeStoryItem, InputMediaEmpty, MessageMediaEmpty, MessageMediaPhoto, InputMediaPhoto, Photo, \
    InputMediaUploadedPhoto, InputFile, Message
from telethon.tl.types.stories import Stories

import utils
from config_and_settings import settings
from db.repositories import AccountsChatsRepo
from services.message_generator import MessageGenerator
from services.notifier import Notifier
from user_bot.exceptions import LinkBioBan, BadChatLink


def log_decorator(func):
    @functools.wraps(func)
    async def wrapper(self, *args, **kwargs):
        logger = logging.getLogger(func.__qualname__)

        try:
            result = await func(self, *args, **kwargs)
            logger.info(f"Account: {self.account_name} | Успешно")
            return result
        except Exception as e:
            logger.error(f"Account: {self.account_name} "
                         f"| Метод {func.__name__} завершился с ошибкой: {e}, тип ошибки {type(e)}")
            raise e
        except:
            logging.error(f"WTF IS GOING ON!")

    return wrapper


class UserBot:
    counter_messages: int = 0

    def __init__(self,
                 account_id: int,
                 account_name: str,
                 message_generator: MessageGenerator,
                 notifier: Notifier,
                 admin_id: int,
                 delay_between_subscriptions: list[int],
                 delay_before_comment: list[int],
                 delay_between_comments: list[int],
                 session_path: str,
                 json_path: str | None,
                 rm_chat: Callable,
                 new_ch_blacklist_call: Callable,
                 save_chat_call: Callable,
                 use_ai_for_generate_message: bool = False,
                 api_id: str = None,
                 api_hash: str = None,
                 proxy: dict | None = None,
                 ):
        self.bad_sessions_folder = "bad_sessions"
        self._rm_chat = rm_chat
        self._tg_id = None
        self.db_acc_id = account_id
        self._session_path = session_path
        self._json_path = json_path
        self._api_id = api_id
        self._api_hash = api_hash
        self._message_generator = message_generator
        self._notifier = notifier
        self._delay_between_subscriptions = delay_between_subscriptions
        self._delay_before_comment = delay_before_comment
        self._delay_between_comments = delay_between_comments
        self._admin_id = admin_id
        self.account_name = account_name
        self._use_ai_for_generate_message = use_ai_for_generate_message

        self._client = TelegramClient(
            session=session_path,
            proxy=proxy,
            **self._get_session_params
        )
        event = events.NewMessage(incoming=True, func=lambda e: e.is_channel)
        self._client.add_event_handler(self._handle_new_msg, event)

        self._semaphore = asyncio.Semaphore(1)
        self._last_subscribe_datetime = datetime.utcnow().replace(year=2000)

        self.subscribe_queue = asyncio.Queue()

        self.subscribe_observers = []
        self._subscribe_task = asyncio.create_task(self._process_sub_queue())

        self._comment_queue = asyncio.Queue()
        self._comment_task = asyncio.create_task(self._process_comment_queue())

        self._counter_messages = 0
        self.blacklist = set()
        self.new_ch_blacklist_call = new_ch_blacklist_call

        self.save_chat_call = save_chat_call

        self.is_writing_comments_enabled = False
        self.process_subscribe_pending = False

    async def start(self):
        try:
            await self._client.connect()
            me_ = await self._client.get_me()
            self._tg_id = me_.id
            asyncio.create_task(self.disconnect_watcher())
            return me_
        except Exception as e:
            return False

    async def disconnect_watcher(self):
        while True:
            await asyncio.sleep(5)
            if not self._client.is_connected():
                try:
                    await self._client.connect()
                    await self._client.get_me()
                except Exception as e:
                    await self._notifier.notify(
                        self._admin_id,
                        f"Аккаунт {self.account_name} похоже ушёл в бан."
                        f" Файл сессии был перемещён в папку невалидных сессий."
                    )
                    try:
                        await self._client.disconnect()
                    except:
                        pass
                    if self._session_path:
                        utils.move_file(self._session_path, self.bad_sessions_folder)
                    if self._json_path:
                        utils.move_file(self._json_path, self.bad_sessions_folder)

                    logging.info(f"Account: {self.account_name} is banned")
                    break

    def run_writing_comments(self):
        self.is_writing_comments_enabled = True

    @log_decorator
    async def edit_profile(self, photo: str, first_name: str, last_name: str, about: str):
        if not settings.update_fio:
            first_name = None
            last_name = None
        if not settings.update_bio:
            about = None
        await self._edit_name_and_about(first_name, last_name, about)
        await asyncio.sleep(1)

        if settings.delete_avatar_before_set_new:
            await self._delete_profile_photos()
            await asyncio.sleep(1)

        if settings.update_avatar:
            await self._upload_new_profile_photo(photo)
            await asyncio.sleep(1)

        if settings.set_random_username:
            await self._set_username(True)
            await asyncio.sleep(1)
        elif settings.delete_username:
            await self._set_username(False)
            await asyncio.sleep(1)

        if settings.delete_stories:
            await self._delete_stories()
            await asyncio.sleep(1)

        if settings.close_other_sessions:
            await self._close_other_sessions()
            await asyncio.sleep(1)

        if settings.edit_privacy:
            await self._set_privacy()

    async def disconnect(self):
        await self._client.disconnect()

    async def _notify_sub_observers(self, chat: str, data):
        for observer_func in self.subscribe_observers:
            await observer_func(self.db_acc_id, chat, data)

    async def _handle_new_msg(self, event):
        if not self.is_writing_comments_enabled:
            return

        if event.message and event.message.replies is not None:
            chat_id = event.message.peer_id.channel_id
            if event.replies.comments and chat_id not in self.blacklist:
                await self._comment_queue.put(event)

    @log_decorator
    async def _delete_profile_photos(self):
        await self._client(DeletePhotosRequest(
            id=[
                InputPhoto(
                    id=p.id,
                    access_hash=p.access_hash,
                    file_reference=p.file_reference
                )
                async for p in self._client.iter_profile_photos("me")
            ],
        ))

    @log_decorator
    async def _upload_new_profile_photo(self, photo: str):
        upload_photo = await self._client.upload_file(photo)
        await self._client(UploadProfilePhotoRequest(file=upload_photo))

    @log_decorator
    async def _edit_name_and_about(self, first_name: str, last_name: str, about: str):
        if first_name or last_name or about:
            await self._client(UpdateProfileRequest(
                first_name=first_name,
                last_name=last_name,
                about=about
            ))

    @log_decorator
    async def _set_username(self, set_new_username=False):
        for i in range(5):
            new_username = ""
            if set_new_username:
                new_username = utils.random_string()
            try:
                await self._client(UpdateUsernameRequest(username=new_username))
                break
            except (UsernameInvalidError, UsernameOccupiedError) as e:
                await asyncio.sleep(5)
            except UsernameNotModifiedError as e:
                break
            except FloodWaitError as e:
                logging.info(f"FloodWaitError - function: edit_username - delay: {e.seconds}")
                await asyncio.sleep(e.seconds)

    async def _write_comment(self, event):
        count_lbb = 0
        time_out_counter = 0
        first_try = True
        post_text = event.message.raw_text.strip()
        message = await self._generate_comment(post_text)
        while True:
            chat_id = event.message.peer_id.channel_id
            try:
                result = await self._client.send_message(
                    entity=event.message.peer_id.channel_id,
                    message=message,
                    comment_to=event.message)

                if result is None:
                    count_lbb += 1
                    raise LinkBioBan

                logging.info(f'{self.account_name} | Сообщение №{UserBot.counter_messages} - message({message}) '
                             f'отправлено в комментарий канала: id{event.message.peer_id.channel_id}')
                UserBot.counter_messages += 1
                return result

            except ConnectionError as e:
                raise e

            except TimeoutError:
                await asyncio.sleep(5)
                time_out_counter += 1
                if time_out_counter > 4:
                    await self._notifier.notify(
                        self._admin_id,
                        f'{self.account_name} | Ошибка TimeoutError после 5-и попыток отправить комментарий')
                    break

            except FloodWaitError as e:
                logging.warning(f'{self.account_name} | FloodWaitError, ожидание {e.seconds + 20} секунд')
                await asyncio.sleep(e.seconds + 20)

            except ChannelPrivateError:
                logging.info(
                    f'{self.account_name} | Указанный канал id{event.message.peer_id.channel_id} является частным,'
                    f' и у вас нет прав на доступ к нему. Другая причина может заключаться в том, что вас забанили. '
                    f'Добавлен в чс')
                self.blacklist.add(event.message.peer_id.channel_id)
                await self.new_ch_blacklist_call(self.db_acc_id, chat_id)
                break

            except ChatGuestSendForbiddenError as e:
                if not first_try:
                    logging.info(
                        f"{self.account_name} - ChatGuestSendForbiddenError - не удалось отправить комментарий")
                    break
                await self._subscribe(event.replies.channel_id)
                first_try = False

            except MsgIdInvalidError as e:
                # возможно сообщение было удалено, комментарий невозможен
                break

            except SlowModeWaitError as e:
                seconds = e.seconds
                channel_id = event.message.peer_id.channel_id
                self.blacklist.add(channel_id)
                asyncio.create_task(self._remove_channel_from_bl_after(channel_id, seconds))
                break

            except UserBannedInChannelError:
                # await AccountsChatsRepo.set_ban(self.db_acc_id, chat_id=chat_id)
                logging.info(
                    f'{self.account_name} | Вам запрещено отправлять сообщения в супергруппах/каналах. '
                    f'Группа канала id{event.message.peer_id.channel_id} - публичная! Добавлен в чс')
                self.blacklist.add(event.message.peer_id.channel_id)
                await self.new_ch_blacklist_call(self.db_acc_id, chat_id)
                break

            except UserDeactivatedBanError as e:
                logging.info(f"{self.account_name} | Невозможно отправить комментарий (UserDeactivatedBanError)")
                break

            except (ValueError, ChatWriteForbiddenError):
                # await AccountsChatsRepo.set_ban(self.db_acc_id, chat_id=chat_id)
                logging.info(
                    f'{self.account_name} | Запрещено писать! Вы больше не можете оставлять комментарии в группе канала '
                    f'id{event.message.peer_id.channel_id}. Добавлен в чс')
                self.blacklist.add(event.message.peer_id.channel_id)
                await self.new_ch_blacklist_call(self.db_acc_id, chat_id)
                break

            except LinkBioBan:
                await asyncio.sleep(10)
                if count_lbb > 10:
                    await self._client.disconnect()
                    msg = f"Клиент {self.account_name} был отключён, причина: LinkBioBan"
                    logging.info(msg)
                    await self._notifier.notify(self._admin_id, msg)
                    break

            except ForbiddenError as e:
                msg = f'{self.account_name} | Действия в канале id{event.message.peer_id.channel_id} ограничены админами'
                logging.error(msg)
                # await AccountsChatsRepo.set_ban(self.db_acc_id, chat_id=chat_id)
                self.blacklist.add(event.message.peer_id.channel_id)
                await self.new_ch_blacklist_call(self.db_acc_id, chat_id)
                break

            except Exception as e:
                msg = f'{self.account_name} | Действия в канале id{event.message.peer_id.channel_id} ограничены админами. Добавлен в чс'
                logging.error(msg)
                logging.error(f'{self.account_name} | {traceback.format_exc()}')
                # await AccountsChatsRepo.set_ban(self.db_acc_id, chat_id=chat_id)
                self.blacklist.add(event.message.peer_id.channel_id)
                await self.new_ch_blacklist_call(self.db_acc_id, chat_id)
                raise e

    async def _subscribe(self, chat_link: str):
        try:
            response = await self._send_subscribe_request(chat_link)
            if response and response.chats and len(response.chats) > 0:
                chat = response.chats[0]
                if isinstance(chat, Channel):
                    username = chat.username if hasattr(chat, "username") else None
                    return "channel", chat.title, chat.id, username, chat_link
                elif isinstance(chat, Chat):
                    username = chat.username if hasattr(chat, "username") else None
                    return "chat", chat.title, chat.id, username, chat_link
                raise ChatGuestSendForbiddenError

        except InviteRequestSentError as e:
            await asyncio.sleep(10)
            data = await self._get_chat_info_by_invite_link(chat_link)
            return data

        except UserAlreadyParticipantError as e:
            data = await self.get_info_about_entity(chat_link)
            return data

        except FloodWaitError as e:
            seconds_ = e.seconds + 30
            logging.info(f"{self.account_name} - FloodWaitError - подписка - жду {seconds_} сек.")
            await asyncio.sleep(seconds_)
            return await self._subscribe(chat_link)

        except InviteHashExpiredError as e:
            logging.error(f"{self.account_name} - InviteHashExpiredError - {chat_link}")
            raise BadChatLink(chat_link)

        except ConnectionError as e:
            await asyncio.sleep(60)
            try:
                await self._client.connect()
            except OSError:
                raise e

            return await self._subscribe(chat_link)

        except ValueError as e:
            logging.exception(e)
            if str(e).startswith("No user has"):
                return None
            else:
                raise e

    async def _send_subscribe_request(self, chat_link):
        if isinstance(chat_link, str):
            if "+" in chat_link:  # invite link
                hash_ = chat_link[chat_link.index("+") + 1:]
                response = await self._client(ImportChatInviteRequest(hash_))
            elif 'joinchat' in chat_link:
                index = chat_link.index("joinchat") + 9
                response = await self._client(ImportChatInviteRequest(chat_link[index:]))
            else:
                raise ValueError(f"Неверный аргумент подписки {chat_link}")
        else:  # username or link
            response = await self._client(JoinChannelRequest(chat_link))
        return response

    async def _get_chat_info_by_invite_link(self, invite_link: str):
        try:
            entity = await self._client(CheckChatInviteRequest(invite_link[invite_link.index("+") + 1:]))
            if isinstance(entity, ChatInviteAlready):
                chat = entity.chat
                if isinstance(chat, Channel):
                    username = chat.username if hasattr(chat, "username") else None
                    return "channel", chat.title, chat.id, username, invite_link
                elif isinstance(chat, Chat):
                    username = chat.username if hasattr(chat, "username") else None
                    return "chat", chat.title, chat.id, username, invite_link
                return None
        except:
            return None
        return None

    async def get_info_about_entity(self, link: str):
        if self.is_inviting_link(link):
            data = await self._get_chat_info_by_invite_link(link)
            return data
        chat = await self._client.get_entity(link)
        if isinstance(chat, Channel):
            username = chat.username if hasattr(chat, "username") else None
            return "channel", chat.title, chat.id, username, link
        elif isinstance(chat, Chat):
            username = chat.username if hasattr(chat, "username") else None
            return "chat", chat.title, chat.id, username, link
        return None

    @property
    def _get_session_params(self):
        if not self._json_path:
            return self._default_session_params

        with open(self._json_path, 'r') as f:
            json_params = json.load(f)

        if not self._is_valid_json(json_params):
            return self._default_session_params
        else:
            api_id = json_params.pop('app_id')
            api_hash = json_params.pop('app_hash')
            device_model = json_params.pop('device')
            system_version = json_params.pop('sdk')
            app_version = json_params.pop('app_version')
            lang_code = json_params.pop('lang_pack')
            system_lang_code = json_params.pop('system_lang_pack')

            json_params.clear()

            json_params['api_id'] = api_id
            json_params['api_hash'] = api_hash
            json_params['device_model'] = device_model
            json_params['system_version'] = system_version
            json_params['app_version'] = app_version
            json_params['lang_code'] = lang_code
            json_params['system_lang_code'] = system_lang_code

            return json_params

    @property
    def _default_session_params(self):
        return {
            "api_id": self._api_id,
            "api_hash": self._api_hash,
            "device_model": 'PC 64bit',
            "system_version": '4.16.30-vxCUSTOM',
            "app_version": '3.1.8 x64',
            "lang_code": 'en',
            "system_lang_code": 'en-US'
        }

    @classmethod
    def is_inviting_link(cls, user_text: str):
        telegram_invite_link_pattern = r'https://t.me/\+.+'
        if re.match(telegram_invite_link_pattern, user_text):
            return True
        return False

    @classmethod
    def _is_valid_json(cls, json_params: dict) -> bool:
        values_list = ['app_id', 'app_hash', 'device', 'sdk', 'app_version', 'lang_pack', 'system_lang_pack']
        for value in values_list:
            if value not in json_params:
                return False
        return True

    async def _process_sub_queue(self):
        while True:
            chat = await self.subscribe_queue.get()
            self.process_subscribe_pending = True
            time_from_last_sub = datetime.utcnow() - self._last_subscribe_datetime
            delay = timedelta(seconds=random.randint(*self._delay_between_subscriptions))

            if time_from_last_sub < delay:
                seconds = (delay - time_from_last_sub).total_seconds()
                logging.info(f"{self.account_name} - пауза в подписке {seconds} сек.")
                await asyncio.sleep(seconds)

            try:
                data = await self._subscribe(chat)
                # обновляем время последней подписки только в том случае, если она была успешной
                self._last_subscribe_datetime = datetime.utcnow()
                if data:
                    await self.save_chat_call(self.db_acc_id, data[4], data[2])
                logging.info(f"Аккаунт {self.account_name} подписался на канал {chat}")
            except ConnectionError as e:  # если мы тут, значит аккаунт скорее всего в бане
                logging.exception(e)
                await self._notifier.notify(
                    self._admin_id,
                    f"Аккаунт {self.account_name} похоже ушёл в бан."
                    f" Файл сессии был перемещён в папку невалидных сессий."
                )
                try:
                    await self._client.disconnect()
                except:
                    pass
                if self._session_path:
                    utils.move_file(self._session_path, self.bad_sessions_folder)
                if self._json_path:
                    utils.move_file(self._json_path, self.bad_sessions_folder)
                break
            except BadChatLink as e:
                # нужно удалить этот чат из файла channels.txt
                chat_link = e.chat_link
                self._rm_chat(chat_link)
                logging.info(f"Ссылка {chat_link} была удалена из channels.txt")
                await asyncio.sleep(5)

            except Exception as e:
                logging.exception(e)

            self.process_subscribe_pending = False

    async def _process_comment_queue(self):
        while True:
            event = await self._comment_queue.get()

            try:
                chat_id = event.message.peer_id.channel_id
                if chat_id not in self.blacklist:
                    await asyncio.sleep(random.randint(*self._delay_before_comment))
                    message = await self._write_comment(event)
                    if settings.need_edit_comment:
                        self._schedule_edit_comment(copy.copy(message), chat_id)
            except Exception as e:
                msg = f"{self.account_name} - {type(e)} - {str(e)}"
                logging.error(msg)
                logging.exception(e)
                await self._notifier.notify(self._admin_id, msg)

            await asyncio.sleep(random.randint(*self._delay_between_comments))

    async def unsubscribe_all(self):
        i = 0
        async for dialog in self._client.iter_dialogs():
            while True:
                try:
                    await self._client.delete_dialog(dialog, revoke=True)
                    i += 1
                    logging.info(f"{self.account_name} - Удалил чат №{i}")
                    break
                except FloodWaitError as e:
                    logging.info(f"{self.account_name} - FloodWaitError - {e.seconds + 30}")
                    await asyncio.sleep(e.seconds + 30)
                except ChannelPrivateError as e:
                    break
                except ChatAdminRequiredError as e:
                    break
                except Exception as e:
                    msg = f"{self.account_name} - Неожиданное исключение - {type(e)} - {e}"
                    logging.error(msg)
                    logging.exception(e)
                    await self._notifier.notify(self._admin_id, msg)
                    break

        logging.info(f"{self.account_name} - Отписался от (каналов или групп): {i}")

    @log_decorator
    async def _delete_stories(self):
        me = await self._client.get_me()
        result = await self._client(functions.stories.GetPeerStoriesRequest(me))
        stories = result.stories.stories
        stories_ids = list([story.id for story in stories])
        if stories_ids:
            await self._client(functions.stories.DeleteStoriesRequest(me, stories_ids))

    async def _close_other_sessions(self):
        # Получение списка всех активных сессий
        authorized_sessions = await self._client(functions.account.GetAuthorizationsRequest())
        current_session_hash = 0

        for session in authorized_sessions.authorizations:
            if session.hash != current_session_hash:
                # Закрытие других сессий
                try:
                    await asyncio.sleep(1)
                    await self._client(functions.account.ResetAuthorizationRequest(session.hash))
                except Exception as e:
                    logging.error(f"{self.account_name} - {type(e)} - {e}")

    async def _set_privacy(self):
        fields = [
            {
                "key": InputPrivacyKeyStatusTimestamp(),
                "rules": [InputPrivacyValueAllowAll()] if settings.privacy_online else [InputPrivacyValueDisallowAll()]
            }, {
                "key": InputPrivacyKeyProfilePhoto(),
                "rules": [InputPrivacyValueAllowAll()] if settings.privacy_avatar else [InputPrivacyValueDisallowAll()]
            }, {
                "key": InputPrivacyKeyBirthday(),
                "rules": [InputPrivacyValueAllowAll()] if settings.privacy_birthday else [
                    InputPrivacyValueDisallowAll()]
            }, {
                "key": InputPrivacyKeyAbout(),
                "rules": [InputPrivacyValueAllowAll()] if settings.privacy_bio else [InputPrivacyValueDisallowAll()]
            }, {
                "key": InputPrivacyKeyPhoneNumber(),
                "rules": [InputPrivacyValueAllowAll()] if settings.privacy_phone else [InputPrivacyValueDisallowAll()]
            }, {
                "key": InputPrivacyKeyChatInvite(),
                "rules": [InputPrivacyValueAllowAll()] if settings.privacy_groups else [InputPrivacyValueDisallowAll()]
            }, {
                "key": InputPrivacyKeyForwards(),
                "rules": [InputPrivacyValueAllowAll()] if settings.privacy_replay_msgs else [
                    InputPrivacyValueDisallowAll()]
            }, {
                "key": InputPrivacyKeyPhoneCall(),
                "rules": [InputPrivacyValueAllowAll()] if settings.privacy_calls else [InputPrivacyValueDisallowAll()]
            }, {
                "key": InputPrivacyKeyVoiceMessages(),
                "rules": [InputPrivacyValueAllowAll()] if settings.privacy_voice_msgs else [
                    InputPrivacyValueDisallowAll()]
            },
        ]
        for field in fields:
            try:
                result = await self._client(functions.account.SetPrivacyRequest(
                    key=field["key"],
                    rules=field["rules"]
                ))
                await asyncio.sleep(1)
            except Exception as e:
                logging.error(f"{self.account_name} - {type(e)} - {e}")

    @log_decorator
    async def add_story(self, photo: str, caption: str):
        result = await self._client(functions.stories.SendStoryRequest(
            peer=self._tg_id,
            media=types.InputMediaUploadedPhoto(
                file=await self._client.upload_file(photo),
            ),
            privacy_rules=[types.InputPrivacyValueAllowAll()],
            pinned=True,
            noforwards=False,
            caption=caption,
            period=86400,
        ))

    async def _remove_channel_from_bl_after(self, channel_id: int, seconds: int):
        await asyncio.sleep(seconds + random.randint(4, 10))
        try:
            self.blacklist.remove(channel_id)
        except:
            pass

    async def get_story(self, story_id: int, user_id: str):
        stories: Stories = await self._client(GetStoriesByIDRequest(peer=user_id, id=[story_id]))
        if len(stories.stories) > 0:
            story: TypeStoryItem = stories.stories[0]
            jpg_ = await self._client.download_media(story.media.photo, "photo.jpg")
            return story, "photo.jpg"

    async def publish_story(self, story: TypeStoryItem, filename_photo: str):
        media = InputMediaUploadedPhoto(
            file=await self._client.upload_file(filename_photo),
            spoiler=False
        )
        await self._client(SendStoryRequest(
            peer=self._tg_id,
            media=media,
            privacy_rules=[InputPrivacyValueAllowAll()],
            pinned=story.pinned,
            noforwards=story.noforwards,
            media_areas=story.media_areas,
            caption=story.caption + "asdas",
            entities=story.entities,
            period=settings.period_story_hours * 3600,
        ))

    async def _generate_comment(self, text: str):
        if self._use_ai_for_generate_message and text:
            try:
                return await self._message_generator.generate_ai_response(text, self.db_acc_id)
            except APIConnectionError as e:
                logging.exception(e)
                msg = ("Не удалось сгенерировать комментарий из-за сетевой ошибки. "
                       "Возможно, прокси не фурычат.")
                await self._notifier.notify(self._admin_id, msg)

            except AuthenticationError as e:
                await self._notifier.notify(self._admin_id, "Неверный токен openai")

            except RateLimitError as e:
                if e.code == 429 and e.message.startswith("You exceeded your current quota"):
                    await self._notifier.notify(self._admin_id, "Закончился баланс ChatGPT")

            except Exception as e:
                msg = f"Ошибка {type(e)} при попытке получить комментарий (запись в логе есть)"
                await self._notifier.notify(self._admin_id, msg)

            return self._message_generator.generate_random_msg()
        else:
            return self._message_generator.generate_random_msg()

    def _schedule_edit_comment(self, message: Message, chat_id: int):
        asyncio.create_task(self._edit_comment(message, chat_id))

    async def _edit_comment(self, message: Message, chat_id: int):
        await asyncio.sleep(settings.delay_before_edit)
        if chat_id in self.blacklist:
            return

        text = self._message_generator.generate_random_msg()

        count_lbb = 0
        time_out_counter = 0
        while True:
            try:
                result = await self._client.edit_message(message.peer_id, message, text)

                if result is None:
                    count_lbb += 1
                    raise LinkBioBan

                logging.info(f'{self.account_name} успешно отредактировал комментарий')
                return result

            except ConnectionError as e:
                raise e

            except TimeoutError:
                await asyncio.sleep(5)
                time_out_counter += 1
                if time_out_counter > 4:
                    await self._notifier.notify(
                        self._admin_id,
                        f'{self.account_name} | Ошибка TimeoutError после 5-и попыток отредактировать комментарий')
                    break

            except FloodWaitError as e:
                logging.warning(f'{self.account_name} | FloodWaitError, ожидание {e.seconds + 20} секунд')
                await asyncio.sleep(e.seconds + 20)

            except ChannelPrivateError:
                logging.info(
                    f'{self.account_name} | Указанный канал id{message.peer_id.channel_id} является частным,'
                    f' и у вас нет прав на доступ к нему. Другая причина может заключаться в том, что вас забанили. '
                    f'Добавлен в чс')
                self.blacklist.add(chat_id)
                await self.new_ch_blacklist_call(self.db_acc_id, chat_id)
                break

            except MsgIdInvalidError as e:
                # возможно сообщение было удалено, комментарий невозможен
                break

            except UserBannedInChannelError:
                # await AccountsChatsRepo.set_ban(self.db_acc_id, chat_id=chat_id)
                logging.info(
                    f'{self.account_name} | Вам запрещено отправлять сообщения в супергруппах/каналах. '
                    f'Группа канала id{chat_id} - публичная! Добавлен в чс')
                self.blacklist.add(chat_id)
                await self.new_ch_blacklist_call(self.db_acc_id, chat_id)
                break

            except (ValueError, ChatWriteForbiddenError):
                # await AccountsChatsRepo.set_ban(self.db_acc_id, chat_id=chat_id)
                logging.info(
                    f'{self.account_name} | Запрещено писать! Вы больше не можете оставлять комментарии в группе канала '
                    f'id{chat_id}. Добавлен в чс')
                self.blacklist.add(chat_id)
                await self.new_ch_blacklist_call(self.db_acc_id, chat_id)
                break

            except LinkBioBan:
                if count_lbb > 10:
                    await self._client.disconnect()
                    msg = f"Клиент {self.account_name} был отключён, причина: LinkBioBan"
                    logging.info(msg)
                    await self._notifier.notify(self._admin_id, msg)
                    break

            except ForbiddenError as e:
                msg = f'{self.account_name} | Действия в канале id {message.peer_id.channel_id} ограничены админами'
                logging.error(msg)
                # await AccountsChatsRepo.set_ban(self.db_acc_id, chat_id=chat_id)
                self.blacklist.add(chat_id)
                await self.new_ch_blacklist_call(self.db_acc_id, chat_id)
                break

            except Exception as e:
                msg = f'{self.account_name} | Действия в канале id {chat_id} ограничены админами. Добавлен в чс'
                logging.error(msg)
                logging.error(f'{self.account_name} | {traceback.format_exc()}')
                # await AccountsChatsRepo.set_ban(self.db_acc_id, chat_id=chat_id)
                self.blacklist.add(chat_id)
                await self.new_ch_blacklist_call(self.db_acc_id, chat_id)
                raise e
