import dataclasses
import time

import PIL
import requests
from peewee import SqliteDatabase, Model, BlobField, CharField
from playhouse.sqlite_ext import JSONField

from .utility import HEADERS, create_thumbnail

BASE_URL = "https://api.mangadex.org"
db = SqliteDatabase("data/md.db")


class BaseModel(Model):
    class Meta:
        database = db


class MDManga(BaseModel):
    slug = CharField(primary_key=True)
    data = JSONField()
    chapters = JSONField()
    thumbnail = BlobField()


class MDChapter(BaseModel):
    slug = CharField(primary_key=True)
    thumbnail = BlobField()


@dataclasses.dataclass()
class MDEntry:
    manga: MDManga
    slug: str
    language: str
    title: str
    date: str
    pages: int
    thumbnail: bytes


MD_LANGUAGE_MAP = {
    "en": "English",
    "id": "Indonesian",
    "es-la": "Spanish (LATAM)",
    "ru": "Russian",
    "pt-br": "Portuguese (Br)",
    "vi": "Vietnamese",
    "de": "German",
    "fr": "French",
    "it": "Italian",
    "uk": "Ukrainian",
    "es": "Spanish (Es)",
    "pl": "Polish",
    "hu": "Hungarian",
    "th": "Thai",
    "tr": "Turkish",
}


def all_md_chapters() -> list[MDEntry]:
    chapters = []
    for manga in MDManga.select():
        for chapter in manga.chapters:
            def chapter_title():
                tokens = []
                if chapter['attributes']['chapter']:
                    tokens.append(f"Chapter {chapter['attributes']['chapter']}")
                if chapter['attributes']['title']:
                    tokens.append(chapter['attributes']['title'])
                if tokens:
                    return " - ".join(tokens)

                manga_titles = manga.data["attributes"]["title"]
                return list(manga_titles.values())[0]

            def chapter_language():
                code = chapter["attributes"]["translatedLanguage"]
                if code not in MD_LANGUAGE_MAP:
                    print(f"[warning] missing language code: {code}")
                    return code
                return MD_LANGUAGE_MAP[code]

            def chapter_thumbnail():
                data = MDChapter.get_or_none(MDChapter.slug == chapter["id"])
                return data.thumbnail if data else manga.thumbnail

            assert chapter["type"] == "chapter"
            chapters.append(MDEntry(
                manga=manga,
                slug=chapter["id"],
                language=chapter_language(),
                title=chapter_title(),
                date=chapter["attributes"]["publishAt"],
                pages=int(chapter["attributes"]["pages"]),
                thumbnail=chapter_thumbnail(),
            ))
    return chapters


def manga_request(params):
    return requests.get(
        f"{BASE_URL}/manga",
        headers=HEADERS,
        params=params + [
            ("title", "Touhou"),
            ("includes[]", "cover_art"),
            ("includes[]", "author"),
            ("includes[]", "artist"),
        ],
    ).json()


def scrape_manga():
    offset = 0
    limit = 100
    while True:
        entries = manga_request([("limit", limit), ("offset", offset)])["data"]
        if not entries:
            break

        for entry in entries:
            slug = entry["id"]
            if MDManga.get_or_none(MDManga.slug == slug):
                print(f"[manga/skip] {slug}")
                continue
            print(f"[manga/new] {slug}")

            covers = []
            for relationship in entry["relationships"]:
                if relationship["type"] == "cover_art":
                    covers.append(relationship["attributes"]["fileName"])

            if not covers:
                print(f"[manga/uncovered] {slug}")
                continue

            thumbnail = requests.get(
                url=f"https://uploads.mangadex.org/covers/{slug}/{covers[0]}.256.jpg",
                headers=HEADERS,
            ).content

            chapters = requests.get(
                url=f"{BASE_URL}/manga/{slug}/feed",
                headers=HEADERS,
                params={"limit": 500},
            ).json()["data"]

            MDManga.create(
                slug=slug,
                data=entry,
                chapters=chapters,
                thumbnail=thumbnail
            )

        # Slide offset.
        offset += limit


def request_with_retry(url):
    while True:
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 429:
            print(f"[event/rate-limit] {url}")
            until = int(response.headers["X-RateLimit-Retry-After"])
            time.sleep(max(0.0, until - time.time()))
            continue
        return response


def scrape_chapters():
    for manga in MDManga.select():
        # Skip fetching chapter cover images when only one chapter exists.
        if len(manga.chapters) <= 1:
            continue

        for chapter in manga.chapters:
            slug = chapter["id"]
            if MDChapter.get_or_none(MDChapter.slug == slug):
                print(f"[chapter/skip] {slug}")
                continue
            print(f"[chapter/new] {slug}")

            page_data = request_with_retry(
                url=f"{BASE_URL}/at-home/server/{slug}",
            ).json()

            cover_url = "/".join([
                page_data["baseUrl"],
                "data-saver",
                page_data["chapter"]["hash"],
                page_data["chapter"]["dataSaver"][0],
            ])

            cover = requests.get(
                url=cover_url,
                headers=HEADERS,
            ).content

            try:
                thumbnail = create_thumbnail(cover)
            except PIL.UnidentifiedImageError:
                print(f"[page/failure] {cover_url}")
                continue

            MDChapter.create(
                slug=slug,
                thumbnail=thumbnail,
            )


def main():
    db.connect()
    db.create_tables([
        MDManga,
        MDChapter,
    ])

    scrape_manga()
    scrape_chapters()


if __name__ == '__main__':
    main()
