import yaml

from config_and_settings import log_config  # noqa
from config_and_settings._config import Config
from config_and_settings._settings import Settings

with open("config_and_settings/config.yaml", "r", encoding="utf-8") as f:
    _config_data = yaml.safe_load(f)
with open("config_and_settings/settings.yaml", "r", encoding="utf-8") as f:
    _settings_data = yaml.safe_load(f)

config: Config = Config(**_config_data)
settings: Settings = Settings(**_settings_data)
