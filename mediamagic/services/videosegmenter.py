import asyncio
import logging
from pathlib import Path
from typing import List, Tuple

from ffmpeg.asyncio import FFmpeg

from mediamagic.constants import BinPath

logger = logging.getLogger("videosegmenter")


class VidSegmenter:

    def __init__(self, max_size: int | float):
        print(self.max_size)
        self.max_size = max_size

    async def get_video_duration_size(self, video_path: Path) -> Tuple[float, float]:
        """Returns tuple of duration(seconds) & size(mb) of a video."""
        command = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ]

        process = await asyncio.create_subprocess_exec(
            *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode == 0:
            duration = float(stdout)
            return duration, video_path.stat().st_size / (1024**2)
        else:
            raise RuntimeError(
                f"Error getting video duration for {
                    video_path}: {stderr.decode()}"
            )

    async def trim_hls(
        self, media: Path, segment_duration: float, out_dir: Path
    ) -> List:
        # todo: figure out the way to trim rescursive and generate m3u8 file referencing following command
        #  ffmpeg -i input.mp4 -c copy -f hls -hls_time 100 -reset_timestamps 1 -hls_list_size 0 -hls_segment_filename output/hi%03d.mp4 output/inp%03d.m3u8

        raise NotImplementedError

    async def trim(
        self,
        media: Path,
        segment_duration: float,
        out_path: Path,
        file_name: str = "%03d.mp4",
    ) -> None:
        """Trims a video file into segments."""
        logger.debug(
            f"Trimming {media.name} to {
                segment_duration/60:.4f} mins"
        )
        ffmpeg = (
            FFmpeg()
            .option("y")
            .input(str(media))
            .output(
                str(out_path / file_name),
                codec="copy",
                map="0",
                f="segment",
                segment_time=segment_duration,
                reset_timestamps="1",
            )
        )

        try:
            await ffmpeg.execute()
        except Exception as e:
            logger.error(f"Error trimming {media.name}", exc_info=e)
            return
        logger.debug(f"Unlinking {media.name}")

    async def ensure_segments_size(self, outdir: Path, retry: int = 0) -> None:
        """Ensures that all segments are less than the max_size using recursive trimming."""
        should_check = False
        files = [file for file in outdir.iterdir() if file.is_file()]
        for file in files:
            segment_duration, size = await self.get_video_duration_size(file)
            # Both segment_duration returns same amount of file but just there
            # is imbalance in the size of the file in the first var

            # segment_duration = (segment_duration / size) * (self.max_size - 1)
            segment_duration = segment_duration / 2

            if size >= self.max_size:
                should_check = True
                await self.trim(
                    media=file,
                    segment_duration=segment_duration,
                    out_path=outdir,
                    file_name=f"{file.name}-%03d.mp4",
                )
                file.unlink()
        if should_check:
            logger.debug(f"Retrying {retry}")
            retry = retry + 1
            await self.ensure_segments_size(outdir, retry)

    async def sanitize_video(self, media: Path) -> None:
        """Fix video having missing timestamp"""
        ffmpeg = (
            FFmpeg()
            .option("y")
            .input(str(media))
            .output(
                str(str(media) + ".mp4"),
                codec="copy",
            )
        )
        try:
            await ffmpeg.execute()
        except Exception as e:
            logger.error(f"Error while sanitizing {media.name}", exc_info=e)
            return
        media.unlink()
        Path(str(media) + ".mp4").rename(str(media))

    async def segment(self, media: Path, save_dir: Path) -> Path:
        """Wrapper for segment method, where versions can be changed manually"""
        # res = await self.segment_v1(media, save_dir)
        res = await self.segment_v2(media, save_dir)
        return res

    async def segment_v1(self, media: Path, save_dir: Path) -> Path:
        """Segments a video file into smaller parts."""

        await self.sanitize_video(media)
        duration, size = await self.get_video_duration_size(media)
        segment_duration = (duration / size) * self.max_size

        if size <= self.max_size:
            raise ValueError(
                f"Video Size is Already less than {
                    self.max_size} Mb"
            )
        elif segment_duration <= 0:
            raise ValueError("Max Size Is Too Low")

        out_path = save_dir / media.stem
        out_path.mkdir(parents=True, exist_ok=True)
        logger.debug(
            f"Trimming: {media.name} {self.max_size=} Mb {duration=} Minutes {
                size=} Mb duration={segment_duration / 60} mins outpath={out_path.absolute()}"
        )

        await self.trim(media, segment_duration, out_path)
        logger.debug(f"Ensuring segments are less than {self.max_size} Mb")
        await self.ensure_segments_size(out_path)

        return out_path

    async def segment_v2(self, media: Path, save_dir: Path) -> Path:

        await self.sanitize_video(media)
        out_path = save_dir / media.stem

        out_path.mkdir(parents=True, exist_ok=True)
        process = await asyncio.create_subprocess_exec(
            BinPath.segmenter,
            media,
            out_path,
            str(self.max_size),
        )
        await process.communicate()
        return out_path


async def main():
    input_file = Path("o.mp4")
    output_dir = Path("output")
    segmenter = VidSegmenter(max_size=25)

    await segmenter.segment_v2(input_file, output_dir)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    asyncio.run(main())
