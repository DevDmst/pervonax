import functools
import logging
import os
import random
import re
import string
from pathlib import Path

_telegram_link_pattern = r'https://t.me/.+'

def get_sessions(path_to_folder: str) -> dict:
    """
    Собирает информацию о сессиях и JSON файлах в указанной папке.
    :param path_to_folder: Путь к папке, в которой находятся файлы.
    :return: Словарь, где ключами являются имена файлов, а значениями - словари с путями к файлам сессий и JSON.
    """
    sessions = {}
    for file in os.listdir(path_to_folder):
        name = Path(file).stem
        if not sessions.get(name):
            sessions[name] = {"session": None, "json": None}
        if file.endswith('.session'):
            sessions[name]["session"] = os.path.join(path_to_folder, file)
        elif file.endswith('.json'):
            sessions[name]["json"] = os.path.join(path_to_folder, file)
    return sessions


def get_proxies(path_to_file: str, proxy_type: str) -> list:
    with open(path_to_file, 'r', encoding="utf-8") as f:
        lines = f.readlines()
        proxies = []
        for line in lines:
            if line := line.strip():
                proxy = line.split(':')
                proxy = {
                    'proxy_type': proxy_type,
                    'addr': proxy[0],
                    'port': int(proxy[1]),
                    'username': proxy[2],
                    'password': proxy[3],
                    'rdns': True
                }
                proxies.append(proxy)
        return proxies


def get_path_from_root(path: str) -> str:
    getcwd = os.getcwd()
    current_file_path = os.path.abspath(__file__)
    root = os.path.dirname(current_file_path)

    return os.path.join(root, path)


def get_next(items: list, counter: list):
    """Возвращает n-ый элемент, где n = counter[0] и увеличивает counter[0] на 1"""
    if counter[0] < len(items):
        item = items[counter[0]]
        counter[0] += 1
        return item
    else:
        counter[0] = 0
        return items[0]


def is_dict_exist(dict_item: dict, list_of_dicts: list[dict]):
    for it in list_of_dicts:
        result = all((dict_item.get(k) == v for k, v in it.items()))
        if result:
            return True
    return False


def random_string():
    letters_and_digits = string.ascii_letters + string.digits
    rand_string = ''.join(random.sample(letters_and_digits, 15))
    return rand_string


def is_tg_link(channel: str):
    if re.match(_telegram_link_pattern, channel):
        return True
    else:
        return False


def get_channels(path: str):
    with open(path, "r", encoding="utf-8") as f:
        channels = f.readlines()
        channels = [channel.strip() for channel in channels if is_tg_link(channel)]
        return channels

def cyclic_iterator(items):
    if not items:
        raise ValueError("The list is empty")
    index = 0
    while True:
        yield items[index]
        index = (index + 1) % len(items)