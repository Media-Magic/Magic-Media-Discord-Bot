import logging
from functools import partial
from pathlib import Path
from typing import Iterable, List, Optional, Set, Union
from uuid import uuid4
from zipfile import BadZipfile, ZipFile

import aioshutil
import disnake
from disnake.ext import commands

from mediamagic.services.videosegmenter import VidSegmenter
from mediamagic.utils.helper import move_files_to_root

logger = logging.getLogger(__name__)


class UploadService:
    async def upload_file(
        self,
        inter: Union[disnake.Interaction, commands.Context],
        file: Path,
        max_file_size: float,
        channel: Optional[Union[disnake.TextChannel, disnake.ThreadWithMessage]] = None,
    ) -> None:
        try:
            segmenter = VidSegmenter(max_file_size)
            dir = await segmenter.segment(file, Path("."))
            await self.upload(inter, dir, max_file_size, channel)
        except ValueError:
            if isinstance(channel, disnake.TextChannel):
                await channel.send(file=disnake.File(file))
            else:
                await inter.channel.send(file=disnake.File(file))
        finally:
            file.unlink()

    async def upload_zip_v1(
        self,
        inter: Union[disnake.Interaction, commands.Context],
        zip_files: Iterable[Path],
        max_file_size: float,
        channel: Optional[Union[disnake.TextChannel, disnake.ThreadWithMessage]] = None,
    ) -> None:
        zip_path = Path(str(uuid4()))
        for file in zip_files:
            try:
                z = ZipFile(file)
                z.extractall(zip_path)
                z.close()
                file.unlink()
                move_files_to_root(zip_path)
                await self.upload(inter, zip_path, max_file_size, channel)
            except BadZipfile:
                logger.warning("Bad Zip File")
                file.unlink()
                await aioshutil.rmtree(zip_path)

    async def upload_zip(
        self,
        inter: Union[disnake.Interaction, commands.Context],
        zip_files: Iterable[Path],
        max_file_size: float,
        channel: Optional[Union[disnake.TextChannel, disnake.ThreadWithMessage]] = None,
    ) -> None:
        zip_path = Path(str(uuid4()))
        for file in zip_files:
            try:
                await aioshutil.unpack_archive(file, zip_path)
                file.unlink()
                move_files_to_root(zip_path)
                await self.upload(inter, zip_path, max_file_size, channel)
            except Exception as e:
                logger.error(f"Bad Zip File!", exc_info=e)
                file.unlink()
                await aioshutil.rmtree(zip_path)

    async def upload_segment(
        self,
        inter: Union[disnake.Interaction, commands.Context],
        to_segment: Union[List, Set],
        dir: Path,
        max_file_size: float,
        channel: Optional[Union[disnake.TextChannel, disnake.ThreadWithMessage]] = None,
    ) -> None:
        logger.info(f"{len(to_segment)} files found which are more than 25mb detected")
        for file in to_segment:
            try:
                segmenter = VidSegmenter(max_file_size)
                seg_dir = await segmenter.segment(file, dir)
            except Exception:
                continue
            file.unlink()
            await self.upload(inter, seg_dir, max_file_size, channel)

    async def upload(
        self,
        inter: Union[disnake.Interaction, commands.Context],
        dir: Path,
        max_file_size: float,
        channel: Optional[Union[disnake.TextChannel, disnake.ThreadWithMessage]] = None,
    ) -> None:
        """Generic Function for upload"""
        logger.debug(f"Upload started {dir=} {max_file_size=}")
        if dir.is_file():
            logger.debug(f"Uploading file {dir=} {max_file_size=}")
            await self.upload_file(inter, dir, max_file_size, channel)
        else:
            dir_iter = {x for x in map(lambda x: Path(x), dir.iterdir()) if x.is_file()}
            zip_files = {i for i in dir_iter if str(i).endswith(".zip")}
            to_segment = {
                file
                for file in dir_iter
                if file.stat().st_size / 1024**2 > max_file_size
            }
            dir_iter = dir_iter - zip_files
            dir_iter = sorted(dir_iter - to_segment)
            total_file = [file for file in map(lambda x: disnake.File(x), dir_iter)]
            file_grps = [
                total_file[i : i + 8] for i in range(0, len(total_file), 8)
            ]  # Legacy way to batch
            # file_grps = batched(total_file, 8)

            if zip_files:
                logger.debug(f"Uploading zip {zip_files=} {max_file_size=}")
                await self.upload_zip(inter, zip_files, max_file_size, channel)
            if to_segment:
                logger.debug(f"Uploading segment {to_segment=} {dir=} {max_file_size=}")
                await self.upload_segment(
                    inter, to_segment, dir, max_file_size, channel
                )

            logger.debug(f"Uploading to {channel=}")
            for file_grp in file_grps:
                len_file = [x.bytes_length / 1024**2 for x in file_grp]
                try:
                    logger.debug(f"Uploading {sum(len_file)}")
                    if isinstance(channel, disnake.ThreadWithMessage):
                        send = partial(channel.thread.send, files=file_grp)
                    elif isinstance(channel, disnake.TextChannel):
                        send = partial(channel.send, files=file_grp)
                    else:
                        send = partial(inter.channel.send, files=file_grp)
                    await send()
                except Exception as e:
                    logger.error(f"Upload Failed {e} {sum(len_file)} {len_file=}")

            await aioshutil.rmtree(dir)
