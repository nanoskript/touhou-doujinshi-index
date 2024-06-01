import io
import os
from typing import TypeVar
from urllib.parse import urlencode

import requests
from PIL import Image, ImageFile

T = TypeVar("T")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TouhouIndexBot/0.1; +https://scarlet.nsk.sh)"
}


def deduplicate_by_identity(xs: list[T]) -> list[T]:
    objects = {}
    for o in xs:
        objects[id(o)] = o
    return list(objects.values())


def create_thumbnail(data: bytes) -> bytes:
    ImageFile.LOAD_TRUNCATED_IMAGES = True
    with io.BytesIO() as buffer:
        thumbnail = Image.open(io.BytesIO(data)).convert("RGB")
        thumbnail.thumbnail((256, 256))
        thumbnail.save(buffer, format="JPEG")
        return buffer.getvalue()


# Strain HTML for performance.
def strain_html(html: str, tag: str, pattern: str) -> str:
    start = html.find(pattern)
    position = start + 1
    depth = 1

    opening_tag = f"<{tag}"
    closing_tag = f"</{tag}"
    while depth > 0:
        opening = html.find(opening_tag, position)
        closing = html.find(closing_tag, position)

        if opening != -1 and opening < closing:
            depth += 1
            position = opening + 1
        else:
            depth -= 1
            position = closing + 1

    position += len(closing_tag)
    return html[start:position]


def get_with_proxy(url: str, retries: int, params: dict[str, str | int] = None):
    attempt = 0
    while attempt < retries:
        response = requests.get(
            "https://api.scrapingant.com/v2/general",
            params={
                "url": f"{url}?{urlencode(params or {})}",
                "x-api-key": os.environ["SCRAPINGANT_API_KEY"],
                "browser": "false",
            }
        )

        if response.status_code == 200:
            return response

        attempt += 1
        print(f"[retry] {url}")
    raise ValueError(f"Failed to fetch: {url}")
