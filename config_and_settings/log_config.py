import logging
import os

from colorama import init, Style, Fore


class ColorFormatter(logging.Formatter):
    # ANSI escape sequences for colors
    COLORS = {
        logging.DEBUG: Style.DIM + Fore.WHITE,
        logging.INFO: Style.BRIGHT + Fore.GREEN,
        logging.WARNING: Style.BRIGHT + Fore.YELLOW,
        logging.ERROR: Style.BRIGHT + Fore.RED,
        logging.CRITICAL: Style.BRIGHT + Fore.RED + Style.BRIGHT
    }

    def format(self, record):
        color = self.COLORS.get(record.levelno, Fore.WHITE)
        message = super().format(record)
        return color + message + Style.RESET_ALL


init(autoreset=True)

log_lvl = logging.INFO

os.makedirs("logs", exist_ok=True)

stream_handler = logging.StreamHandler()
info_file_handler = logging.FileHandler("logs/log.txt", encoding="utf-8")
error_file_handler = logging.FileHandler("logs/error.txt", encoding="utf-8")
handlers = [
    stream_handler,
    info_file_handler,
    error_file_handler
]

info_file_handler.setLevel(logging.INFO)
error_file_handler.setLevel(logging.ERROR)

formatter = ColorFormatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s")
stream_handler.setLevel(log_lvl)
stream_handler.setFormatter(formatter)

logging.getLogger('telethon.client.updates').setLevel(logging.ERROR)

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    level=logging.DEBUG,
    handlers=handlers
)
