import asyncio
import functools
import io
import logging
from pathlib import Path
from typing import Optional, Set, Union
from uuid import uuid4
from zipfile import ZipFile

import disnake
import httpx
from disnake.ext import commands

from mediamagic.bot import MediaMagic
from mediamagic.checks import is_premium_owner, is_premium_user
from mediamagic.constants import Client
from mediamagic.services.adownloader import Adownloader
from mediamagic.services.terabox import TeraExtractor
from mediamagic.services.upload import UploadService

logger = logging.getLogger(__name__)


class Upload(commands.Cog):
    def __init__(self, bot: MediaMagic) -> None:
        # FIFO Queue Data: (function, guild_id, interaction)
        self.queue = asyncio.Queue()
        self.bot = bot
        self.uploadservice = UploadService()
        self.active_producer = set()

    async def consumer(self, guild_id: int):
        logger.info(f"Consumer task created for {guild_id}")
        inter: disnake.GuildCommandInteraction | None = None
        while not self.queue.empty():
            logger.debug(f"Consumer of {guild_id} in while")
            func, id, inter = await self.queue.get()
            if id != guild_id:
                await self.queue.put((func, id, inter))
                logger.info(f"Putting back in queue {id}")
                continue
            try:
                await func()
            except Exception as e:
                logger.error(f"Consumer of {guild_id} got exception", exc_info=e)
            finally:
                self.queue.task_done()
        self.active_producer.remove(guild_id)
        if inter is not None:
            try:
                await inter.author.send(
                    f"Upload completed in {inter.channel.mention}",  # type: ignore
                    allowed_mentions=disnake.AllowedMentions(),
                )
            finally:
                await inter.channel.send(
                    f"{inter.author.mention} Upload completed!",
                    allowed_mentions=disnake.AllowedMentions(),
                    delete_after=5,
                )
        logger.info(f"Consumer task completed for {guild_id}")

    @commands.slash_command(name="nsfw_toggle")
    async def nsfw_toggle(
        self,
        inter: disnake.GuildCommandInteraction,
        channel_or_category: Union[disnake.TextChannel, disnake.CategoryChannel],
        value: bool,
    ) -> None:
        """
        Toggles the age-restriction of the provided channel or category

        Parameters
        ----------
        channel_or_category : The channel/category to toggle
        value : The value to set the age-restriction
        """
        await inter.response.defer()
        if isinstance(channel_or_category, disnake.CategoryChannel):
            for channel in channel_or_category.channels:
                await channel.edit(nsfw=value)
        else:
            await channel_or_category.edit(nsfw=value)
        await inter.send(
            f"{channel_or_category.mention} is now {'' if value else 'not'} age-restriced!",
        )

    @commands.slash_command(name="upload", dm_permission=False)
    @is_premium_owner()
    async def serve(
        self,
        inter: disnake.GuildCommandInteraction,
        attachment: Optional[disnake.Attachment] = None,
        direct_or_terabox_link: Optional[str] = None,
        channel: Optional[disnake.TextChannel] = None,
        sequential_upload: bool = True,
    ):
        """
        Uploads the provided links in attachment even if the media size is more than server upload limit

        Parameters
        ----------
        attachment : The text file containing the links to download
        direct_or_terabox_link : The direct/terabox link to download the media (use , for multiple links)
        channel : The channel to upload the files
        sequential_upload : Whether to upload the files sequentially or concurrently
        """
        if (direct_or_terabox_link is None and attachment is None) or (
            direct_or_terabox_link and attachment
        ):
            raise commands.CommandError(
                "Provide either attachment or direct_or_terabox_link option"
            )
        elif direct_or_terabox_link:
            final = direct_or_terabox_link
        elif attachment:
            final = attachment
        else:
            raise commands.CommandError("Should not be raised this error")
        await self.serv(inter, final, channel, sequential_upload)

    @commands.slash_command(name="terabox")
    @is_premium_user()
    async def terabox(self, inter: disnake.GuildCommandInteraction, link: str) -> None:
        """
        Resolve and upload terabox link in channel

        Parameters
        ----------
        link : The terabox link to resolve and upload (use , for multiple links)
        """
        if not link.startswith("http"):
            raise commands.CommandError("Invalid link")
        await inter.send(
            "Your upload is being queued, Upload will be completed soon!",
            ephemeral=True,
        )
        await self.serv(inter, link)

    async def serv(
        self,
        inter: disnake.GuildCommandInteraction,
        attachment: Union[disnake.Attachment, Path, str],
        channel: Optional[Union[disnake.TextChannel, disnake.ThreadWithMessage]] = None,
        sequential_upload: bool = True,
    ):
        """
        Serves the provided attachment

        Parameters
        ----------
        attachment : The text file/Path/str containing the links to download
        channel : The channel to upload the files
        sequential_upload : Whether to upload the files sequentially or concurrently
        """
        if isinstance(attachment, Path):
            url_buff = attachment.read_text()
        elif isinstance(attachment, str):
            url_buff = attachment.replace(",", "\n")
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
        # Batches urls into groups
        url_grp = [
            url_list[i : i + Client.url_group_limit]
            for i in range(0, len(url_list), Client.url_group_limit)
        ]
        for idx, url in enumerate(url_grp, 1):
            url = set(url)

            # for every url group _dwnld is called,
            # then a group is passed to Adownloader on by one
            async def _dwnld(urls: Set[str]):
                downloader = Adownloader(urls=urls)
                destination = await downloader.download()
                # After downloading a group we upload them via task or await

                async def _upload():
                    logger.info(f"Uploading from {destination}")
                    try:
                        await self.uploadservice.upload(
                            inter,
                            destination,
                            # For safe side we decrease discord file size limit by 1
                            # float((inter.guild.filesize_limit / 1024**2) - 1),
                            float((inter.guild.filesize_limit / 1024**2)),
                            channel=channel,
                        )
                    except Exception as e:
                        logger.error("Upload Failed", exc_info=e)

                if sequential_upload:
                    logger.info("Doing Sequential Upload")
                    await _upload()
                else:
                    logger.info("Doing Concurrent Upload")
                    asyncio.create_task(_upload())

            # Puts downloader with uploader function in queue
            func = functools.partial(_dwnld, url)
            logger.debug(f"Queued {len(url)} urls in _dwnld")
            await self.queue.put((func, inter.guild.id, inter))  # Producer
        # Create consumer task for this guild and put it in active producer set
        if not inter.guild.id in self.active_producer:
            self.active_producer.add(inter.guild.id)
            asyncio.create_task(self.consumer(inter.guild.id))

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
