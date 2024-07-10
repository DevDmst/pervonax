from dataclasses import dataclass


@dataclass
class Config:
    api_id: str
    api_hash: str
    bot_token: str
    admin_id: int
