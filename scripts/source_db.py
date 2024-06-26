from collections import Counter

import requests
from peewee import SqliteDatabase, Model, CharField, BlobField, IntegerField, ForeignKeyField
from playhouse.sqlite_ext import JSONField
from requests.adapters import HTTPAdapter
from urllib3 import Retry

from .utility import HEADERS, tracing_response_hook

requests = requests.Session()
retries = Retry(total=5, backoff_factor=0.5, status_forcelist=[429])
requests.mount("https://", HTTPAdapter(max_retries=retries))
requests.hooks["response"].append(tracing_response_hook)
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


class DBWikiPage(BaseModel):
    title = CharField(primary_key=True)
    data = JSONField()


class DBComments(BaseModel):
    pool = ForeignKeyField(DBEntry, unique=True)
    comments = JSONField()


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
        criteria_q = questionable_count < 0.3 * len(entry.posts)
        if criteria_e and criteria_q:
            entries.append(entry)
    return entries


def pool_translation_ratio(entry: DBEntry) -> float:
    translation_count = 0
    for post in entry.posts:
        if "translated" in post["tag_string_meta"]:
            translation_count += 1
    return translation_count / len(entry.posts)


def pool_english_text_ratio(entry: DBEntry) -> float:
    english_count = 0
    for post in entry.posts:
        if "english_text" in post["tag_string_general"]:
            english_count += 1
    return english_count / len(entry.posts)


def db_entry_artists(entry: DBEntry) -> list[str]:
    artists = []
    for post in entry.posts:
        artists += post["tag_string_artist"].split()
    artists = [artist.replace("_", " ") for artist in artists]
    return list(set(artists))


def db_pixiv_id(entry: DBEntry) -> int | None:
    cover_post = entry.posts[0]
    if cover_post["pixiv_id"]:
        return cover_post["pixiv_id"]


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

        media_urls = {}
        for variant in posts[0]["media_asset"]["variants"]:
            media_urls[variant["type"]] = variant["url"]

        fallback_url = posts[0]["preview_file_url"]
        thumbnail_url = media_urls.get("360x360", fallback_url)
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


# FIXME: Handle request errors gracefully.
def gather_comments(post_ids: list[int], batch_size: int = 200):
    comments = []
    response_limit = 1000
    for start in range(0, len(post_ids), batch_size):
        print(f"[comments/chunk] {start} / {len(post_ids)}")
        ids = post_ids[start:start + batch_size]
        response = requests.get(
            f"https://danbooru.donmai.us/comments.json",
            headers=HEADERS,
            params={
                "search[post_id]": ",".join(map(str, ids)),
                "limit": response_limit,
            },
        ).json()

        # Retry with lower batch size if limit reached.
        if len(response) == response_limit:
            new_batch_size = batch_size // 2
            return gather_comments(post_ids, batch_size=new_batch_size)
        comments += response
    return comments


def scrape_comments():
    for entry in DBEntry.select():
        print(f"[comments/pool] {entry.pool_id}")
        ids = [post["id"] for post in entry.posts]
        comments = gather_comments(ids)

        (DBComments.delete()
         .where(DBComments.pool == entry)
         .execute())

        DBComments.create(
            pool=entry,
            comments=comments,
        )


def significant_characters() -> Counter[str]:
    characters = Counter()
    for entry in DBEntry.select(DBEntry.posts):
        names = []
        for post in entry.posts:
            names += post["tag_string_character"].split()
        for name in set(names):
            characters[name] += 1

    # Take only significant characters.
    return Counter({
        name: count
        for name, count in characters.items()
        if count >= 20
    })


def scrape_wiki_pages():
    for character in significant_characters().keys():
        if DBWikiPage.get_or_none(title=character):
            print(f"[wiki/skip] {character}")
            continue

        print(f"[wiki] {character}")
        results = requests.get(
            "https://danbooru.donmai.us/wiki_pages.json",
            params={"search[title_normalize]": character},
            headers=HEADERS,
        ).json()

        if results:
            DBWikiPage.create(
                title=character,
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
            f"https://dtext.nsk.sh/dtext-parse",
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
        DBComments,
        DBWikiPage,
        DBPoolDescription,
    ])

    scrape_pools()
    scrape_artists()
    scrape_comments()
    scrape_wiki_pages()
    render_pool_descriptions()


if __name__ == '__main__':
    main()
