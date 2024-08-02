import json
import logging
import random
import re
from urllib.parse import quote

from httpx import AsyncClient, Proxy
from httpx_socks import AsyncProxyTransport
from openai import OpenAI, AsyncOpenAI, APIConnectionError
from python_socks import ProxyType

from services.ai_msg_generator import AIMsgGenerator


class MessageGenerator:
    def __init__(self,
                 templates_file_path: str,
                 openai_api_key: str,
                 promts: list[str],
                 proxy_socks5: dict = None, ):
        self._templates_file_path = templates_file_path
        with open(templates_file_path, "r", encoding="utf-8") as f:
            templates = f.readlines()
            self._templates = [template.strip() for template in templates if
                               template.strip() and not template.startswith("#")]
        self._pattern = re.compile(r'\{([^}]+)\}')
        self._ai_generator = AIMsgGenerator(openai_api_key, promts, proxy_socks5)

    def generate_random_msg(self):
        choice = random.choice(self._templates)
        last_end = 0
        phrase = []
        for match in self._pattern.finditer(choice):
            phrase.append(choice[last_end:match.start()])

            options = match.group(1).split('|')
            phrase.append(random.choice(options))

            last_end = match.end()
        phrase.append(choice[last_end:])
        return "".join(phrase)

    async def generate_ai_response(self, text: str, acc_db_id: int):
        response = await self._ai_generator.generate_msg(text, acc_db_id)
        if not response:
            return self.generate_random_msg()
        return response
