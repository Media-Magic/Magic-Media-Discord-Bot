import asyncio
import io
import logging
from pathlib import Path
from typing import Optional, Set, Union
from uuid import uuid4
from zipfile import ZipFile

import disnake
import httpx
from disnake.ext import commands, tasks

from mediamagic.bot import MediaMagic
from mediamagic.checks import is_premium_owner
from mediamagic.services.adownloader import Adownloader
from mediamagic.services.terabox import TeraExtractor
from mediamagic.services.upload import UploadService

logger = logging.getLogger(__name__)


class Upload(commands.Cog):
    def __init__(self, bot: MediaMagic) -> None:
        self.queue = asyncio.Queue()
        self.bot = bot
        self.uploadservice = UploadService()

    @commands.slash_command(name="nsfw_toggle")
    async def nsfw_toggle(
        self,
        inter: disnake.GuildCommandInteraction,
        channel_or_category: Union[disnake.TextChannel, disnake.CategoryChannel],
        value: bool,
    ) -> None:
        await inter.response.defer()
        if isinstance(channel_or_category, disnake.CategoryChannel):
            for channel in channel_or_category.channels:
                await channel.edit(nsfw=value)
        else:
            await channel_or_category.edit(nsfw=value)
        await inter.send(
            f"{channel_or_category.mention} is now {'' if value else 'not'} age-restriced!",
        )

    async def serv(
        self,
        inter: disnake.GuildCommandInteraction,
        attachment: Union[disnake.Attachment, Path],
        channel: Optional[Union[disnake.TextChannel, disnake.ThreadWithMessage]] = None,
        sequential_upload: bool = True,
    ):
        """
        Serves the provided attachment

        Parameters
        ----------
        attachment : The text file containing the links to download
        channel : The channel to upload the files
        sequential_upload : Whether to upload the files sequentially or concurrently
        """
        logger.debug(f"Serv started {attachment=} {channel=}")
        if isinstance(attachment, Path):
            url_buff = attachment.read_text()
        else:
            await inter.send(
                "Your upload is being queued, Upload will be completed soon!",
                ephemeral=True,
            )
            url_buff = (await attachment.read()).decode("utf-8")
        url_list = url_buff.split("\n")
        url_set = {x for x in url_list if x}
        tera_set = {x for x in url_set if x.startswith("https://terabox")}
        url_set = url_set - tera_set

        logger.debug(f"TeraBox Links {len(tera_set)=}")
        if tera_set:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(None, read=None),
                follow_redirects=True,
                limits=httpx.Limits(max_connections=10),
            ) as client:
                extractor = TeraExtractor(
                    tera_set,
                    "Magic Browser",
                    client,
                )
                data = await extractor()
                logger.info(f"Resolved TeraBox Links {len(data)=}")
                url_set.update({url.fast_link for url in data if url is not None})

        url_list = list(url_set)
        url_grp = [url_list[i : i + 100] for i in range(0, len(url_list), 100)]
        logger.info(f"Url Group {len(url_grp)=}")
        for idx, url in enumerate(url_grp, 1):
            url = set(url)

            async def _dwnld(urls: Set, final: bool = False):
                downloader = Adownloader(urls=urls)
                destination = await downloader.download()

                async def _upload():
                    logger.info(f"Uploading from {destination}")
                    try:
                        await self.uploadservice.upload(
                            inter,
                            destination,
                            float((inter.guild.filesize_limit / 1024**2) - 1),
                            channel=channel,
                        )
                    except Exception:
                        logger.error("Upload Failed")
                        return
                    logger.info(f"Upload Sequence {idx}/{len(url_grp)} Completed")
                    (
                        logger.info(
                            f"Upload Completed {inter.guild_id} -> {inter.guild.name}"
                        )
                        if final
                        else None
                    )
                    if not isinstance(attachment, Path):
                        if final:
                            try:
                                await inter.author.send(
                                    f"{len(set(url_list))} Upload completed in {inter.channel.mention}",  # type: ignore
                                    allowed_mentions=disnake.AllowedMentions(),
                                )
                            finally:
                                await inter.channel.send(
                                    f"{inter.author.mention} {len(set(url_list))} Upload completed",
                                    allowed_mentions=disnake.AllowedMentions(),
                                    delete_after=5,
                                )

                if sequential_upload:
                    logger.info("Doing Sequential Upload")
                    await _upload()
                else:
                    logger.info("Doing Concurrent Upload")
                    asyncio.create_task(_upload())

            if idx == len(url_grp):
                await self.queue.put((_dwnld, url, True))
            else:
                await self.queue.put((_dwnld, url, False))

    @commands.slash_command(name="serve", dm_permission=False)
    @is_premium_owner()
    async def serve(
        self,
        inter: disnake.GuildCommandInteraction,
        attachment: disnake.Attachment,
        channel: Optional[disnake.TextChannel] = None,
        sequential_upload: bool = True,
    ):
        """
        Download and Upload the provided links and segment the video if it is more than server upload limit

        Parameters
        ----------
        attachment : The text file containing the links to download
        """
        await self.serv(inter, attachment, channel, sequential_upload=sequential_upload)

    @tasks.loop()
    async def run(self):
        if self.queue.empty():
            return
        _f, parm, final = await self.queue.get()
        await _f(parm, final)
        self.queue.task_done()

    @commands.slash_command(name="clone")
    @is_premium_owner()
    async def clone(_):
        """Clone Commands"""

    @clone.sub_command(name="to_channel")
    async def clone_to_channel(
        self, inter: disnake.GuildCommandInteraction, zip_file: disnake.Attachment
    ):
        """
        Clone the provided zip file into a Text channels

        Parameters
        ----------
        zip_file : The zip file to clone
        """
        await inter.send("Cloning Started", ephemeral=True)
        zip_bytes = await zip_file.read()
        zip = ZipFile(io.BytesIO(zip_bytes))
        zip_path = Path(str(uuid4()))
        zip.extractall(zip_path)

        async def _serv(file):
            logger.info(f"Creating thread for {file.stem}")
            channel = await inter.guild.create_text_channel(name=file.stem)
            await self.serv(inter, file, channel=channel)

        tasks = (_serv(file) for file in zip_path.iterdir())
        await asyncio.gather(*tasks)
        await inter.send("Cloning Completed", ephemeral=True)

    @clone.sub_command(name="to_forum")
    async def clone_to_forum(
        self,
        inter: disnake.GuildCommandInteraction,
        zip_file: disnake.Attachment,
        channel: disnake.ForumChannel,
    ):
        """
        Clone the provided zip file into a forum channel

        Parameters
        ----------
        zip_file : The zip file to clone
        channel : The forum channel to clone into
        """
        await inter.send("Cloning Started", ephemeral=True)
        zip_bytes = await zip_file.read()
        zip = ZipFile(io.BytesIO(zip_bytes))
        zip_path = Path(str(uuid4()))
        zip.extractall(zip_path)

        async def _serv(file):
            logger.info(f"Creating thread for {file.stem}")
            thread = await channel.create_thread(name=file.stem, content="_ _")
            await self.serv(inter, file, channel=thread)

        tasks = (_serv(file) for file in zip_path.iterdir())
        await asyncio.gather(*tasks)
        await inter.send("Cloning Completed", ephemeral=True)


def setup(client: MediaMagic) -> None:
    client.add_cog(Upload(client))
