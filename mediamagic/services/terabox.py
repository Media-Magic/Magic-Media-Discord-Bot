import asyncio
import dataclasses
import logging
import sys
from typing import Optional, Set

import httpx

logger = logging.getLogger("terabox")


class TeraExtractor:
    @dataclasses.dataclass(frozen=True)
    class TeraLink:
        thumbnail: str
        title: str
        fast_link: str
        slow_link: str

    def __init__(self, urls: Set, user_agent: str, client: httpx.AsyncClient) -> None:
        self.urls = urls
        self.client = client
        self.user_agent = user_agent

    async def fetch_link(self, link: str) -> TeraLink | None:
        """Fetches the fast and slow(HD) download links for a given terabox link."""
        resp = await self.client.post(
            "https://ytshorts.savetube.me/api/v1/terabox-downloader", data={"url": link}
        )
        if not (json := resp.json().get("response", None)):
            logger.error(f"Unable to resolve {link}")
            return None
        json = json[0]
        resolution = json.get("resolutions")
        fast_link = resolution.get("Fast Download")
        slow_link = resolution.get("HD Video")
        thumbnail = json.get("thumbnail")
        title = json.get("title")
        return self.TeraLink(thumbnail, title, fast_link, slow_link)

    async def __call__(self, urls: Optional[Set] = None) -> Set[TeraLink | None]:
        if not urls:
            urls = self.urls
        tasks = (self.fetch_link(url) for url in urls if url)
        tera_links = set(await asyncio.gather(*tasks))
        logger.info(f"Resolved {len(tera_links)} TeraLinks")
        return tera_links

    @staticmethod
    def extract_links(tera_links: Set[TeraLink | None]) -> Set[str]:
        return {tera_link.fast_link for tera_link in tera_links if tera_link}


if __name__ == "__main__":

    async def main():
        _usage = f"Usage: {sys.argv[0]} <url1> <url2> ..."
        if len(sys.argv) > 1:
            urls = set(sys.argv[1:])
        else:
            print(_usage)
            sys.exit(1)

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(None),
            follow_redirects=True,
            limits=httpx.Limits(max_connections=10),
        ) as client:
            extractor = TeraExtractor(urls, "Magic Browser", client)
            raw_links = await extractor()
            links = extractor.extract_links(raw_links)
            for link in links:
                print(link)

    asyncio.run(main())
