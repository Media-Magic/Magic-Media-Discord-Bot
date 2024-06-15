import logging

from disnake.ext import commands

from mediamagic.constants import Client
from mediamagic.utils.extensions import walk_extensions

logger = logging.getLogger(__name__)


class MediaMagic(commands.Bot):
    def __init__(self, **kwargs) -> None:
        kwargs["command_prefix"] = Client.command_prefix
        super().__init__(**kwargs)

    def load_bot_extensions(self) -> None:
        """Loads extensions released by walk_extensions()"""
        for ext in walk_extensions():
            logger.info(f"{ext} extension loaded!")
            self.load_extension(ext)
