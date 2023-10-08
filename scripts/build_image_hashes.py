import io
from typing import Optional

import PIL
import imagehash
from peewee import SqliteDatabase, Model, CharField
from playhouse.sqlite_ext import JSONField
from PIL import Image
from tqdm import tqdm

from scripts.source_ds import DSEntry
from .entry import entry_key, Entry, entry_thumbnails
from .source_db import DBEntry
from .source_eh import EHEntry
from .source_md import all_md_chapters

db = SqliteDatabase("data/phash.db")


# Hashes are ordered in match priority.
class ImageHash(Model):
    id = CharField(primary_key=True)
    h8s = JSONField()

    class Meta:
        database = db


def entry_h8s(entry: Entry) -> list[int]:
    for row in ImageHash.select().where(ImageHash.id == entry_key(entry)):
        return [int(h8, 16) for h8 in row.h8s]
    return []


# TODO: Handle rotation invariance.
def image_hash(image: Image, size: int) -> str:
    return str(imagehash.phash(image, hash_size=size))


def entry_candidate_images(entry: Entry) -> list[Image]:
    base_images = [
        Image.open(io.BytesIO(data))
        for data in entry_thumbnails(entry)
    ]

    images = base_images.copy()
    for image in base_images:
        width, height = image.size
        if width > height:
            # Image is landscape so append left half.
            images.append(image.crop((0, 0, width // 2, height)))
    return images


def main():
    db.connect()
    db.drop_tables([ImageHash])
    db.create_tables([ImageHash])

    sources = [
        EHEntry.select(),
        DBEntry.select(),
        DSEntry.select(),
        all_md_chapters(),
    ]

    for source in sources:
        for entry in tqdm(source):
            try:
                images = entry_candidate_images(entry)
                h8s = [image_hash(image, size=8) for image in images]
                ImageHash.create(id=entry_key(entry), h8s=h8s)
            except PIL.UnidentifiedImageError:
                continue


if __name__ == '__main__':
    main()
