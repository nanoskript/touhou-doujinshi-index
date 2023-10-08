from collections import defaultdict, Counter

import requests
from peewee import SqliteDatabase, Model, CharField, BlobField
from playhouse.sqlite_ext import JSONField

from .utility import HEADERS

db = SqliteDatabase("data/db.db")


class BaseModel(Model):
    class Meta:
        database = db


class DBEntry(BaseModel):
    pool_id = CharField(unique=True)
    data = JSONField()
    posts = JSONField()
    thumbnail = BlobField()


class DBArtist(BaseModel):
    string = CharField(unique=True)
    data = JSONField()


class DBCharacter(BaseModel):
    string = CharField(unique=True)
    data = JSONField()


def filter_db_entries():
    entries = []
    for entry in DBEntry.select().order_by(DBEntry.pool_id):
        explicit_count = 0
        for post in entry.posts:
            if post["rating"] == "e":
                explicit_count += 1

        # Ignore explicit pools.
        if explicit_count < 0.1 * len(entry.posts):
            entries.append(entry)
    return entries


def pool_translation_ratio(entry: DBEntry) -> float:
    translation_count = 0
    for post in entry.posts:
        if "translated" in post["tag_string_meta"]:
            translation_count += 1
    return translation_count / len(entry.posts)


# TODO: Include 東方 as query.
def all_pools():
    page = 1
    while True:
        result = requests.get(
            "https://danbooru.donmai.us/pools.json",
            headers=HEADERS,
            params={
                "page": page,
                "search[category]": "series",
                "search[is_deleted]": "false",
                "search[name_contains]": "Touhou",
            }
        ).json()

        if not result:
            return

        yield from result
        page += 1


def scrape_pools():
    for data in all_pools():
        pool_id = data["id"]
        if not data["post_ids"]:
            continue

        if DBEntry.select().where(DBEntry.pool_id == pool_id):
            print(f"[pool/skip] {pool_id}")
            continue
        print(f"[pool/new] {pool_id}")

        posts = []
        for index, post_id in enumerate(data["post_ids"]):
            print(f"[post] {index} / {len(data['post_ids'])} ({post_id})")
            post = requests.get(f"https://danbooru.donmai.us/posts/{post_id}.json", headers=HEADERS).json()
            posts.append(post)

        # Posts in pools can be walled.
        if "preview_file_url" not in posts[0]:
            print(f"[pool/walled] {pool_id}")
            continue

        thumbnail_url = posts[0]["preview_file_url"]
        thumbnail = requests.get(thumbnail_url, headers=HEADERS).content

        DBEntry.create(
            pool_id=pool_id,
            data=data,
            posts=posts,
            thumbnail=thumbnail,
        )


def pool_artists(entry: DBEntry) -> set[str]:
    artists = []
    for post in entry.posts:
        artists += post["tag_string_artist"].split()
    return set(artists)


def all_artists() -> set[str]:
    artists = set()
    for entry in DBEntry.select():
        for artist in pool_artists(entry):
            artists.add(artist)
    return artists


def scrape_artists():
    for artist in all_artists():
        if DBArtist.select().where(DBArtist.string == artist):
            print(f"[artist/skip] {artist}")
            continue

        print(f"[artist/new] {artist}")
        results = requests.get(
            f"https://danbooru.donmai.us/artists.json",
            headers=HEADERS,
            params={
                "search[name]": artist,
            }
        ).json()

        if results:
            DBArtist.create(
                string=artist,
                data=results[0],
            )


def main():
    db.connect()
    db.create_tables([
        DBEntry,
        DBArtist,
    ])

    scrape_pools()
    scrape_artists()


if __name__ == '__main__':
    main()
