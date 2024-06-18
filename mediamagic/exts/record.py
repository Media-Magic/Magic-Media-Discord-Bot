import logging
import time
from pathlib import Path
from typing import Dict, Set, Union

import disnake
import httpx
from disnake.ext import commands

from mediamagic.bot import MediaMagic
from mediamagic.checks import is_premium_user
from mediamagic.exceptions import ModelOffline
from mediamagic.services.striplivecam import NsfwLiveCam
from mediamagic.services.upload import UploadService

logger = logging.getLogger(__name__)


class RecorderView(disnake.ui.View):
    def __init__(self, recorder: NsfwLiveCam, author_id: int) -> None:
        super().__init__(timeout=None)
        self.recorder = recorder
        self.author_id = author_id

    @disnake.ui.button(label="Update Thumbnail", style=disnake.ButtonStyle.green)
    async def green(self, _, inter: disnake.MessageInteraction):
        await inter.response.defer()
        await inter.edit_original_response(await self.recorder.get_thumbnail())

    @disnake.ui.button(label="Stop Recording", style=disnake.ButtonStyle.red)
    async def red(self, _, inter: disnake.MessageInteraction):
        if inter.author.id != self.author_id:
            await inter.send("Recording wasn't started by you!", ephemeral=True)
            return
        await inter.send("Stopping Recording", ephemeral=True, delete_after=5)
        await self.recorder.stop_recording()


class Recorder(commands.Cog):
    def __init__(self, bot: MediaMagic) -> None:
        self.bot = bot
        self.uploadservice = UploadService()

    async def record(
        self,
        inter: Union[disnake.GuildCommandInteraction, commands.GuildContext],
        model: str,
    ):
        recorder = NsfwLiveCam(
            model_name=model, out_dir=Path("."), client=httpx.AsyncClient()
        )
        start = time.perf_counter()
        if isinstance(inter, disnake.ApplicationCommandInteraction):
            await inter.send(
                await recorder.get_thumbnail(),
                view=RecorderView(recorder, inter.author.id),
            )
            msg = await inter.original_response()
        else:
            msg = await inter.send(
                await recorder.get_thumbnail(),
                view=RecorderView(recorder, inter.author.id),
            )
        logger.info(f"Recording {model}")
        try:
            await recorder.record_stream()
        except Exception as e:
            logger.warning("Error occured in record stream")
            await recorder.stop_recording()
        await inter.channel.send(
            f"Stream Duration: {(time.perf_counter() - start)/60:.2f}", delete_after=5
        )

        try:
            await self.uploadservice.upload(
                inter,
                Path(recorder.filename),
                float((inter.guild.filesize_limit / 1024**2) - 1),
            )
        except ModelOffline:
            if isinstance(inter, disnake.ApplicationCommandInteraction):
                await inter.edit_original_response(
                    "Model Is Currenlty Offline or in Private Show"
                )
            else:
                await msg.edit("Model Is Currenlty Offline or in Private Show")
        except Exception as e:
            logger.error("Unable to upload", exc_info=e)
        else:
            logger.debug("Upload Completed")
            await inter.channel.send(
                f"{inter.author.mention} upload completed",
                delete_after=5,
                allowed_mentions=disnake.AllowedMentions(),
            )
        finally:
            await msg.delete()

    @commands.slash_command(name="record")
    @is_premium_user()
    async def slash_record(self, inter: disnake.GuildCommandInteraction, model: str):
        """
        Record the stream of the provided model

        Parameters
        ----------
        model : The model name to record
        """
        await inter.response.defer()
        try:
            await self.record(inter, model)
        except ModelOffline:
            await inter.edit_original_response(
                "Model Is Currenlty Offline or in Private Show"
            )

    @slash_record.autocomplete("model")
    async def models_suggestions(self, _, name: str) -> Set | Dict:
        return await NsfwLiveCam(
            model_name="", out_dir=Path("."), client=httpx.AsyncClient()
        ).get_suggestions(name)

    @commands.command(name="record", aliases=["r"])
    @is_premium_user()
    async def pre_record(self, ctx: commands.GuildContext, model: str):
        """
        Record the stream of the provided model

        Parameters
        ----------
        model : The model name to record
        """
        if model[0] == "'" and model[-1] == "'":
            model = model[1:-1]
        await self.record(ctx, model)


def setup(client: MediaMagic) -> None:
    client.add_cog(Recorder(client))
