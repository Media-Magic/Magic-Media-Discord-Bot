import asyncio
import logging
from pathlib import Path
from typing import Any, Dict
from uuid import uuid4

import httpx
import m3u8
from streamlink.session.session import Streamlink

from mediamagic.exceptions import ModelOffline

logger = logging.getLogger("striplivecam")


class NsfwLiveCam:
    def __init__(
        self, model_name: str, out_dir: Path, client: httpx.AsyncClient
    ) -> None:
        self.model = model_name.replace("-", ";")
        self.out_path = out_dir.joinpath(f"{self.model}_{str(uuid4())}.mp4")
        self.host = "xham.live"
        self.client = client
        self.stop = False
        self.filename = f"{self.model}_{str(uuid4())}.mp4"

    async def get_suggestions(self, model: str):
        """Returns a set of model names based on the query"""
        if not model:
            return {}
        elif len(model) >= 3:
            url = f"https://{self.host}/api/front/v4/models/search/suggestion?query={model}&limit=20&primaryTag=girls"
            resp = await self.client.get(url)
            json = resp.json()
            try:
                return {x.get("username") for x in json.get("models")}
            except TypeError or httpx.ConnectError:
                return {}
        return {}

    async def _get_model_id(self) -> Dict:
        """Returns the model id, timestamp and master m3u8 link"""
        url = f"https://{self.host}/api/front/v2/models/username/{self.model.replace(';', '-')}/cam"
        resp = await self.client.get(url)
        json = resp.json()
        if (
            json["cam"]["isCamAvailable"] == "false"
            or len(json["cam"]["streamName"]) == 0
        ):
            raise ModelOffline()
        return {
            "id": json["user"]["user"]["id"],
            "timestamp": json["user"]["user"]["snapshotTimestamp"],
            "master_url": f'https://edge-hls.doppiocdn.com/hls/{json["cam"]["streamName"]}/master/{json["cam"]["streamName"]}_auto.m3u8',
            # "hls_url": f'https://b-{json["cam"]["viewServers"]["flashphoner-hls"]}.doppiocdn.com/hls/{json["cam"]["streamName"]}/{json["cam"]["streamName"]}.m3u8',
            "hls_url": f'https://b-hls-13.doppiocdn.live/hls/{json["cam"]["streamName"]}/{json["cam"]["streamName"]}.m3u8',
        }

    async def quality(self, master_url: str) -> Dict[int, str]:
        """Returns the dict of available qualities"""
        resp = await self.client.get(master_url)
        master_playlist = m3u8.loads(resp.text)
        resolution_dict = {}
        for playlist in master_playlist.playlists:
            resolution = playlist.stream_info.resolution
            uri = playlist.uri
            resolution_dict[resolution[1]] = uri
        return resolution_dict

    async def get_thumbnail(self) -> str:
        """Returns the thumbnail of the model"""
        metadata = await self._get_model_id()
        return f"https://img.strpst.com/thumbs/{metadata.get('timestamp')}/{metadata.get('id')}_webp"

    async def record_stream(self) -> Any:
        """Records the stream"""
        while not self.stop:
            metadata = await self._get_model_id()
            session = Streamlink()
            session.set_option("ffmpeg-start-at-zero", True)
            session.set_option("stream-segment-threads", 20)
            qualities = await self.quality(metadata["master_url"])
            if qualities.get(960):
                highest_quality = qualities[960]
            elif qualities.get(720):
                highest_quality = qualities[720]
            else:
                highest_quality = list(qualities.items())[0][1]
            stream = session.streams(f"hlsvariant://{highest_quality}")["best"]
            logger.info(f"Recording {self.model} using {highest_quality}")
            loop = asyncio.get_running_loop()
            try:
                await loop.run_in_executor(None, self.write_stream, stream)
            except Exception as e:
                logger.error(f"{self.__qualname__} failed to record stream", exc_info=e)
            finally:
                logger.debug(f"Reloading stream of {self.model}")

    def write_stream(self, stream: Any) -> None:
        """Writes the stream to a file"""
        stream = stream.open()
        with open(self.filename, mode="ab") as file:
            while stream and not self.stop:
                try:
                    if buff := stream.read(1024):
                        file.write(buff)
                    else:
                        break
                except Exception as e:
                    logger.error("Failed to write buffer", exc_info=e)
                    break
        stream.close()

    async def stop_recording(self) -> None:
        """Stops the recording"""
        logger.info("Recording stopped")
        self.stop = True
        await asyncio.sleep(5)
