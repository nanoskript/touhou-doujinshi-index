import requests
from peewee import SqliteDatabase, Model, CharField, BlobField, IntegerField, ForeignKeyField
from playhouse.sqlite_ext import JSONField

from .utility import HEADERS

db = SqliteDatabase("data/db.db")


class BaseModel(Model):
    class Meta:
        database = db


class DBEntry(BaseModel):
    pool_id = IntegerField(primary_key=True)
    data = JSONField()
    posts = JSONField()
    thumbnail = BlobField()


class DBArtist(BaseModel):
    string = CharField(unique=True)
    data = JSONField()


class DBCharacter(BaseModel):
    string = CharField(unique=True)
    data = JSONField()


class DBPoolDescription(BaseModel):
    pool = ForeignKeyField(DBEntry, unique=True)
    html = CharField()


def filter_db_entries():
    entries = []
    for entry in DBEntry.select().order_by(DBEntry.pool_id):
        explicit_count = 0
        questionable_count = 0
        for post in entry.posts:
            if post["rating"] == "e":
                explicit_count += 1
            if post["rating"] == "q":
                questionable_count += 1

        # Ignore explicit pools.
        criteria_e = explicit_count < 0.1 * len(entry.posts)
        criteria_q = questionable_count < 0.5 * len(entry.posts)
        if criteria_e and criteria_q:
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


def gather_posts(post_ids: list[int]):
    posts = []
    limit = 200
    for start in range(0, len(post_ids), limit):
        print(f"[post/chunk] {start} / {len(post_ids)}")
        ids = post_ids[start:start + limit]
        posts += requests.get(
            f"https://danbooru.donmai.us/posts.json",
            headers=HEADERS,
            params={
                "tags": f"id:{','.join(map(str, ids))}",
                "limit": limit,
            },
        ).json()

    posts.sort(key=lambda p: post_ids.index(p["id"]))
    return posts


def scrape_pools():
    for data in all_pools():
        pool_id = data["id"]
        if not data["post_ids"]:
            continue

        posts = gather_posts(data["post_ids"])
        existing = DBEntry.get_or_none(pool_id=pool_id)
        if existing:
            if existing.data == data and existing.posts == posts:
                print(f"[pool/skip] {pool_id}")
                continue

            print(f"[pool/update] {pool_id}")
            existing.delete_instance()
        else:
            print(f"[pool/new] {pool_id}")

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


def render_pool_descriptions():
    batch_size = 1000
    entries = list(DBEntry.select())
    for start in range(0, len(entries), batch_size):
        print(f"[descriptions] {start}")
        batch = entries[start:start + batch_size]
        strings = [entry.data["description"] for entry in batch]

        results = requests.post(
            f"https://dtext.nanoskript.dev/dtext-parse",
            headers=HEADERS,
            json=strings,
        ).json()

        for entry, html in zip(batch, results):
            (DBPoolDescription.delete()
             .where(DBPoolDescription.pool == entry)
             .execute())

            DBPoolDescription.create(
                pool=entry,
                html=html,
            )


def main():
    db.connect()
    db.create_tables([
        DBEntry,
        DBArtist,
        DBPoolDescription,
    ])

    scrape_pools()
    scrape_artists()
    render_pool_descriptions()


if __name__ == '__main__':
    main()
