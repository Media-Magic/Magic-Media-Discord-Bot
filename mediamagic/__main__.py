import asyncio
import logging.config
import logging.handlers
import os
import signal
import sys

import disnake
from disnake.ext import commands

from mediamagic.bot import MediaMagic
from mediamagic.constants import Client

bot = commands.Bot(command_prefix="!", intents=disnake.Intents.all())


def setup_logging() -> None:
    os.makedirs("logs", exist_ok=True)
    # file_handler = logging.FileHandler(Client.log_file_name, mode="w")
    file_handler = logging.handlers.RotatingFileHandler(
        Client.log_file_name, mode="a", maxBytes=(1000000 * 20), backupCount=5
    )
    console_handler = logging.StreamHandler()

    file_handler.setLevel(logging.DEBUG)
    console_handler.setLevel(logging.INFO)
    logging.basicConfig(
        level=logging.DEBUG,
        format="[%(levelname)s|%(module)s|%(funcName)s|L%(lineno)d] %(asctime)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
        handlers=[console_handler, file_handler],
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("disnake").setLevel(logging.INFO)
    logging.getLogger("aiosqlite").setLevel(logging.INFO)
    logging.getLogger("streamlink").disabled = True


# def setup_logging() -> None:
#     with open(Client.log_config, "r") as file:
#         config = json.load(file)
#     try:
#         os.mkdir("logs")
#     except FileExistsError:
#         ...
#     logging.config.dictConfig(config)
#     queue_handler = logging.getHandlerByName("queue_handler")
#     if queue_handler is not None:
#         queue_handler.listener.start()  # type: ignore[reportAttributeAccessIssue]
#         atexit.register(queue_handler.listener.stop)  # type: ignore[reportAttributeAccessIssue]


async def main() -> None:
    setup_logging()
    logger = logging.getLogger(Client.name)
    logger.info("Logger Initialized!")
    client = MediaMagic(intents=disnake.Intents.all())
    try:
        client.load_bot_extensions()
    except Exception:
        await client.close()
        raise

    loop = asyncio.get_running_loop()

    future: asyncio.Future = asyncio.ensure_future(
        client.start(Client.token or ""), loop=loop
    )
    loop.add_signal_handler(signal.SIGINT, lambda: future.cancel())
    loop.add_signal_handler(signal.SIGTERM, lambda: future.cancel())

    try:
        await future
    except asyncio.CancelledError:
        logger.info("Received signal to terminate bot and event loop")
    finally:
        if not client.is_closed():
            await client.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
