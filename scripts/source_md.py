import dataclasses
import re
import time

import PIL
import mistletoe
import requests
from peewee import SqliteDatabase, Model, BlobField, CharField, ForeignKeyField
from playhouse.sqlite_ext import JSONField

from .utility import HEADERS, create_thumbnail, tracing_response_hook

BASE_URL = "https://api.mangadex.org"
requests = requests.Session()
requests.hooks["response"].append(tracing_response_hook)
db = SqliteDatabase("data/md.db")


class BaseModel(Model):
    class Meta:
        database = db


class MDManga(BaseModel):
    slug = CharField(primary_key=True)
    data = JSONField()
    covers = JSONField()
    chapters = JSONField()
    thumbnail = BlobField()


class MDChapter(BaseModel):
    slug = CharField(primary_key=True)
    thumbnail = BlobField()


class MDStatistics(BaseModel):
    manga = ForeignKeyField(MDManga, unique=True)
    title = JSONField()
    chapters = JSONField()


@dataclasses.dataclass()
class MDEntry:
    manga: MDManga
    slug: str
    language: str
    title: str
    date: str
    pages: int
    comments: int
    thumbnail: bytes


MD_LANGUAGE_MAP = {
    "en": "English",
    "ja": "Japanese",
    "id": "Indonesian",
    "ru": "Russian",
    "pt": "Portuguese",
    "pt-br": "Portuguese",
    "vi": "Vietnamese",
    "de": "German",
    "fr": "French",
    "it": "Italian",
    "uk": "Ukrainian",
    "es": "Spanish",
    "es-la": "Spanish",
    "pl": "Polish",
    "hu": "Hungarian",
    "th": "Thai",
    "tr": "Turkish",
    "ar": "Arabic",
}


def md_language(code: str) -> str:
    if code not in MD_LANGUAGE_MAP:
        print(f"[warning] missing language code: {code}")
        return code
    return MD_LANGUAGE_MAP[code]


def md_manga_titles(manga: MDManga) -> list[str]:
    manga_titles = list(manga.data["attributes"]["title"].values())
    for title in manga.data["attributes"]["altTitles"]:
        manga_titles += list(title.values())
    return manga_titles


def md_manga_authors_and_artists(manga: MDManga) -> list[str]:
    names = []
    for relationship in manga.data["relationships"]:
        if relationship["type"] in ["author", "artist"]:
            names.append(relationship["attributes"]["name"])
    return list(set(names))


def md_manga_tags(manga: MDManga) -> list[str]:
    tags = []
    for tag in manga.data["attributes"]["tags"]:
        name = tag["attributes"]["name"]["en"]
        if name not in ["Doujinshi", "Oneshot"]:
            tags.append(name)
    return tags


def md_manga_descriptions(manga: MDManga) -> dict[str, str]:
    descriptions = {}
    for code, details in manga.data["attributes"]["description"].items():
        if details.strip():
            name = f"MangaDex description ({md_language(code)})"
            details = re.sub(r"(?<=\S)\n", "  \n", details)
            descriptions[name] = mistletoe.markdown(details)
    return descriptions


def md_manga_comments(manga: MDManga) -> int:
    statistics = MDStatistics.get(manga=manga)
    title_comments = statistics.title["comments"]
    return (title_comments and title_comments["repliesCount"]) or 0


def all_md_chapters() -> list[MDEntry]:
    chapters = []
    for manga in MDManga.select():
        statistics = MDStatistics.get(manga=manga)
        for chapter in manga.chapters:
            def chapter_title():
                tokens = []
                if chapter['attributes']['chapter']:
                    tokens.append(f"Chapter {chapter['attributes']['chapter']}")
                if chapter['attributes']['title']:
                    tokens.append(chapter['attributes']['title'])
                if tokens:
                    return " - ".join(tokens)
                return md_manga_titles(manga)[0]

            def chapter_language():
                code = chapter["attributes"]["translatedLanguage"]
                return md_language(code)

            def chapter_thumbnail():
                data = MDChapter.get_or_none(MDChapter.slug == chapter["id"])
                return data.thumbnail if data else manga.thumbnail

            def chapter_comments():
                comments = statistics.chapters[chapter["id"]]["comments"]
                return comments and comments["repliesCount"]

            assert chapter["type"] == "chapter"
            chapters.append(MDEntry(
                manga=manga,
                slug=chapter["id"],
                language=chapter_language(),
                title=chapter_title(),
                date=chapter["attributes"]["publishAt"],
                pages=int(chapter["attributes"]["pages"]),
                comments=chapter_comments(),
                thumbnail=chapter_thumbnail(),
            ))
    return chapters


def manga_request(params):
    return requests.get(
        f"{BASE_URL}/manga",
        headers=HEADERS,
        params=params + [
            ("title", "Touhou"),
            ("includes[]", "author"),
            ("includes[]", "artist"),
        ],
    ).json()


def scrape_manga():
    offset = 0
    limit = 100
    all_slugs = set()

    # Retrieve all titles.
    while True:
        entries = manga_request([("limit", limit), ("offset", offset)])["data"]
        if not entries:
            break

        for entry in entries:
            slug = entry["id"]
            manga = MDManga.get_or_none(MDManga.slug == slug)
            all_slugs.add(slug)

            if manga:
                if manga.data == entry:
                    print(f"[manga/skip] {slug}")
                    continue
                print(f"[manga/update] {slug}")
                manga.delete_instance()
            else:
                print(f"[manga/new] {slug}")

            covers = requests.get(
                f"{BASE_URL}/cover",
                headers=HEADERS,
                params={
                    "limit": limit,
                    "manga[]": slug,
                }
            ).json()["data"]

            if not covers:
                print(f"[manga/uncovered] {slug}")
                continue

            def cover_sort_key(c):
                volume = c["attributes"]["volume"]
                date = c["attributes"]["createdAt"]
                return volume or date

            first_cover = sorted(covers, key=cover_sort_key)[0]
            cover_file = first_cover["attributes"]["fileName"]
            thumbnail = requests.get(
                url=f"https://uploads.mangadex.org/covers/{slug}/{cover_file}.256.jpg",
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
                covers=covers,
                chapters=chapters,
                thumbnail=thumbnail
            )

        # Slide offset.
        offset += limit

    # Remove orphan titles.
    for manga in MDManga.select():
        if manga.slug not in all_slugs:
            print(f"[manga/orphan] {manga.slug}")
            manga.delete_instance()


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


def scrape_statistics():
    batch_limit = 100
    for manga in MDManga.select():
        print(f"[statistics/manga] {manga.slug}")
        manga_url = f"{BASE_URL}/statistics/manga/{manga.slug}"
        title = request_with_retry(manga_url).json()["statistics"][manga.slug]

        chapter_uuids = []
        for chapter in manga.chapters:
            chapter_uuids.append(chapter["id"])

        chapters = {}
        for start in range(0, len(chapter_uuids), batch_limit):
            batch = chapter_uuids[start:start + batch_limit]
            chapters.update(requests.get(
                f"{BASE_URL}/statistics/chapter",
                headers=HEADERS,
                params={"chapter[]": batch}
            ).json()["statistics"])

        (MDStatistics.delete()
         .where(MDStatistics.manga == manga)
         .execute())

        MDStatistics.create(
            manga=manga,
            title=title,
            chapters=chapters,
        )


def main():
    db.connect()
    db.create_tables([
        MDManga,
        MDChapter,
        MDStatistics,
    ])

    scrape_manga()
    scrape_chapters()
    scrape_statistics()


if __name__ == '__main__':
    main()
