from dataclasses import dataclass


@dataclass
class Settings:
    use_proxy: bool
    type_proxy: str
    need_edit_comment: bool
    delay_before_edit: int
    delay_between_subscriptions: list[int]
    delay_before_comment: list[int]
    delay_between_comments: list[int]
    max_chat_on_acc: int

    edit_privacy: bool

    privacy_groups: bool
    privacy_online: bool
    privacy_phone: bool
    privacy_avatar: bool
    privacy_bio: bool
    privacy_birthday: bool
    privacy_replay_msgs: bool
    privacy_calls: bool
    privacy_voice_msgs: bool

    update_fio: bool
    update_avatar: bool
    delete_avatar_before_set_new: bool
    update_bio: bool
    delete_username: bool
    set_random_username: bool
    delete_stories: bool

    close_other_sessions: bool

    timer_pervonax: bool

    period_story_hours: int
    promts: list[str]

    use_ai_for_generate_message: bool

    promt_token_price_1k: int
    completion_token_price_1k: int
