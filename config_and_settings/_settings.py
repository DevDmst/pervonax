from dataclasses import dataclass


@dataclass
class Settings:
    use_proxy: bool
    type_proxy: str
    set_new_username: bool
    gpt_model: str
    use_gpt: bool
    need_edit_comment: bool
    delay_before_edit: list[int]
    delay_between_subscriptions: list[int]
    delay_before_comment: list[int]
    delay_between_comments: list[int]
    max_chat_on_acc: int
