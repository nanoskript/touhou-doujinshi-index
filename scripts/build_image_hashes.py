import io

import PIL
import imagehash
from peewee import SqliteDatabase, Model, CharField
from PIL import Image
from tqdm.contrib.concurrent import thread_map

from scripts.data_comic_thproject_net import CTHEntry
from scripts.data_doujinshi_org import OrgEntry
from scripts.source_ds import DSEntry
from .entry import entry_key, Entry, entry_thumbnails
from .source_db import DBEntry
from .source_eh import EHEntry
from .source_md import all_md_chapters

db = SqliteDatabase("data/phash.db")


# Hashes are space-separated and ordered in match priority.
class ImageHash(Model):
    id = CharField(primary_key=True)
    h8s = CharField()

    class Meta:
        database = db


# Optimized for repeated calls.
def entry_h8s(entry: Entry) -> list[int]:
    query = "SELECT h8s FROM imagehash WHERE id = ?"
    for [h8s] in db.execute_sql(query, [entry_key(entry)]):
        return [int(h8, 16) for h8 in h8s.split()]
    return []


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

            # Try rotating clockwise and anti-clockwise.
            images.append(image.rotate(angle=270, expand=True))
            images.append(image.rotate(angle=90, expand=True))
    return images


def process_entry(entry: Entry):
    try:
        images = entry_candidate_images(entry)
        h8s = [image_hash(image, size=8) for image in images]
        return ImageHash(id=entry_key(entry), h8s=" ".join(h8s))
    except PIL.UnidentifiedImageError:
        pass


def main():
    db.connect()
    db.drop_tables([ImageHash])
    db.create_tables([ImageHash])

    sources = [
        EHEntry.select(),
        DBEntry.select(),
        DSEntry.select(),
        all_md_chapters(),
        OrgEntry.select(),
        CTHEntry.select(),
    ]

    for source in sources:
        hashes = thread_map(process_entry, source)
        ImageHash.bulk_create(filter(None, hashes))


if __name__ == '__main__':
    main()
