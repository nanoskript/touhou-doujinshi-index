import io
from typing import TypeVar
from PIL import Image, ImageFile

T = TypeVar("T")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TouhouIndexBot/0.1; +https://scarlet.nanoskript.dev)"
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
