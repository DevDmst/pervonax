import json
import logging
import random
from datetime import datetime

import tiktoken
from httpx import AsyncClient
from httpx_socks import AsyncProxyTransport
from openai import AsyncOpenAI, APIConnectionError
from python_socks import ProxyType

from db.repositories.openai_requests import OpenAIRequestsRepo


class AIMsgGenerator:
    def __init__(self,
                 openai_api_key: str,
                 promts: list[str],
                 proxy_socks5: dict = None,):
        if proxy_socks5:
            proxy_host = proxy_socks5["addr"]
            proxy_port = proxy_socks5["port"]
            proxy_username = proxy_socks5["username"]
            proxy_password = proxy_socks5["password"]
            transport = AsyncProxyTransport(
                proxy_type=ProxyType.SOCKS5,
                proxy_host=proxy_host,
                proxy_port=proxy_port,
                username=proxy_username,
                password=proxy_password,
                rdns=proxy_socks5["rdns"]
            )
            httpx_client = AsyncClient(transport=transport)
        else:
            httpx_client = None

        self._openai_client = AsyncOpenAI(api_key=openai_api_key, http_client=httpx_client)
        self.model = "gpt-4o-mini"
        self._promts = promts
        self._attempts = 2


    async def generate_msg(self, text: str, acc_db_id: int) -> str:
        attempts = self._attempts
        response = ""
        while attempts > 0:
            try:
                choice = random.choice(self._promts).replace("{`post`}", text)
                completion = await self._openai_client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "user", "content": choice}
                    ],
                    temperature=0.5
                )
                message = completion.choices[0].message
                data = {
                    "prompt_tokens": completion.usage.prompt_tokens,
                    "completion_tokens": completion.usage.completion_tokens,
                    "user_bot_id": acc_db_id,
                    "created_dt": datetime.utcnow()
                }
                await OpenAIRequestsRepo.add_request(data)
                response = message.content
                break
            except APIConnectionError as e:
                raise e
            except Exception as e:
                logging.info(f"Не удалось сгенерировать AI коммент")
                logging.exception(e)
                attempts -= 1
                data = {
                    "prompt_tokens": self.count_tokens(text),
                    "user_bot_id": acc_db_id,
                    "created_dt": datetime.utcnow()
                }
                await OpenAIRequestsRepo.add_request(data)
        return response

    def count_tokens(self, text: str, role: str = "user"):
        model = self.model
        try:
            encoding = tiktoken.encoding_for_model(model)
        except KeyError:
            encoding = tiktoken.get_encoding("gpt-3.5-turbo")
        messages = [{
            "role": role,
            "content": text,
        }]
        tokens_per_message = 4
        num_tokens = 0
        for message in messages:
            num_tokens += tokens_per_message
            for key, value in message.items():
                if key == 'content':
                    num_tokens += len(encoding.encode(value))
                else:
                    num_tokens += len(encoding.encode(value))
        num_tokens += 3
        return num_tokens
