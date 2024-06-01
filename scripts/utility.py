import io
import os
from typing import TypeVar
from urllib.parse import urlencode
from pprint import pprint

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


def get_with_proxy(url: str, retries: int, params: dict[str, str | int] = None, with_browser: bool = False):
    attempt = 0
    while attempt < retries:
        params = {
            "url": f"{url}?{urlencode(params or {})}",
            "x-api-key": os.environ["SCRAPINGANT_API_KEY"],
        }

        if with_browser:
            params["return_page_source"] = "true"
        else:
            params["browser"] = "false"

        response = requests.get(
            "https://api.scrapingant.com/v2/general",
            params=params
        )

        if response.status_code == 200:
            return response

        attempt += 1
        print(f"[retry/{response.status_code}] {params['url']}")
    raise ValueError(f"Failed to fetch: {params['url']}")


def tracing_response_hook(response: requests.Response, *_args, **_kwargs):
    if not response.ok:
        print(f"[response/{response.status_code}] {response.url}")
        pprint(dict(response.headers))
