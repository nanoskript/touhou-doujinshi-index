import io

import PIL
import requests
from peewee import SqliteDatabase, Model, BlobField, CharField
from playhouse.sqlite_ext import JSONField
from requests.adapters import Retry

from .utility import HEADERS, create_thumbnail

s = requests.Session()
retries = Retry(total=5, backoff_factor=0.1, status_forcelist=[500, 502, 503, 504])
db = SqliteDatabase("data/ds.db")


class BaseModel(Model):
    class Meta:
        database = db


class DSEntry(BaseModel):
    slug = CharField(primary_key=True)
    data = JSONField()
    thumbnail = BlobField()


def filter_ds_entries():
    entries = []
    for entry in DSEntry.select():
        def is_nsfw():
            for tag in entry.data["tags"]:
                if tag["type"] == "General" and tag["name"] == "NSFW":
                    return True

        if not is_nsfw():
            entries.append(entry)
    return entries


def ds_entry_characters(entry: DSEntry) -> list[str]:
    characters = []
    for tag in entry.data["tags"]:
        if tag["type"] == "Pairing":
            characters += tag["name"].split(" x ")
    return list(set(characters))


def main():
    db.connect()
    db.create_tables([DSEntry])

    url = "https://dynasty-scans.com/doujins/touhou_project.json"
    page_count = int(s.get(url, headers=HEADERS).json()["total_pages"])
    for page in range(1, page_count + 1):
        chapter_index = s.get(url, params={"page": page}, headers=HEADERS).json()
        for chapter in chapter_index["taggings"]:
            slug = chapter["permalink"]
            entry = DSEntry.get_or_none(slug=slug)

            if entry:
                if entry.data["tags"] == chapter["tags"]:
                    print(f"[chapter/skip] {slug}")
                    continue
                print(f"[chapter/update] {slug}")
                entry.delete_instance()
            else:
                print(f"[chapter/new] {slug}")

            chapter_url = f"https://dynasty-scans.com/chapters/{slug}.json"
            chapter_data = s.get(chapter_url, headers=HEADERS).json()
            cover = s.get("https://dynasty-scans.com" + chapter_data["pages"][0]["url"]).content

            try:
                thumbnail_data = create_thumbnail(cover)
            except PIL.UnidentifiedImageError:
                continue

            DSEntry.create(
                slug=slug,
                data=chapter_data,
                thumbnail=thumbnail_data,
            )


if __name__ == '__main__':
    main()
