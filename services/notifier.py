import aiohttp


class Notifier:
    def __init__(self, bot_token: str):
        self._request_template = f"https://api.telegram.org/bot{bot_token}/sendMessage?"

    async def notify(self, chat_id: int, text: str):
        async with aiohttp.ClientSession() as session:
            async with session.get(self._request_template, params={"chat_id": chat_id, "text": text}) as resp:
                return await resp.json()
