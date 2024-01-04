from typing import Optional

import PIL
import requests
from bs4 import BeautifulSoup
from peewee import SqliteDatabase, Model, BlobField, CharField, IntegerField, ForeignKeyField
from playhouse.sqlite_ext import JSONField
from requests.adapters import Retry, HTTPAdapter

from .utility import HEADERS, create_thumbnail

s = requests.Session()
retries = Retry(total=5, backoff_factor=0.1, status_forcelist=[500, 502, 503, 504])
s.mount("https://", HTTPAdapter(max_retries=retries))
db = SqliteDatabase("data/ds.db")


class BaseModel(Model):
    class Meta:
        database = db


class DSEntry(BaseModel):
    slug = CharField(primary_key=True)
    data = JSONField()
    thumbnail = BlobField()


class DSTopic(BaseModel):
    slug = CharField(primary_key=True)
    subject = CharField()
    views = IntegerField()
    comments = IntegerField()


class DSEntryTopicSlug(BaseModel):
    entry = ForeignKeyField(DSEntry, unique=True)
    topic_slug = CharField()


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


def ds_entry_pairings(entry: DSEntry) -> list[frozenset[str]]:
    pairings = []
    for tag in entry.data["tags"]:
        if tag["type"] == "Pairing":
            pairings.append(frozenset(tag["name"].split(" x ")))
    return list(set(pairings))


def ds_all_pairings() -> set[frozenset[str]]:
    pairings = []
    for entry in DSEntry.select():
        pairings += ds_entry_pairings(entry)
    return set(pairings)


def ds_entry_tags(entry: DSEntry) -> list[str]:
    tags = []
    for tag in entry.data["tags"]:
        if tag["type"] in ["General"]:
            tags.append(tag["name"])
    return tags


def ds_entry_authors(entry: DSEntry) -> list[str]:
    artists = []
    for tag in entry.data["tags"]:
        if tag["type"] in ["Author"]:
            artists.append(tag["name"])
    return artists


def ds_entry_series(entry: DSEntry) -> Optional[dict]:
    for tag in entry.data["tags"]:
        if tag["type"] == "Series":
            return tag


# FIXME: Include anthology comments.
# If this entry is part of a series,
# then this returns all the comments for that series.
def ds_entry_comments(entry: DSEntry) -> Optional[int]:
    link = DSEntryTopicSlug.get_or_none(entry=entry)
    if link:
        topic = DSTopic.get(slug=link.topic_slug)
        return topic.comments


def scrape_entries():
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


def scrape_topics():
    page = 1
    url = "https://dynasty-scans.com/forum?page=2"
    while True:
        print(f"[topics/page] {page}")
        response = s.get(url, headers=HEADERS, params={"page": page})
        html = BeautifulSoup(response.content, features="html.parser")
        topics = html.find_all(attrs={"class": "forum_topic"})

        for topic in topics:
            link = topic.find("a", attrs={"class": "subject"})
            slug = link.attrs["href"].split("/")[-1]

            views = int(topic
                        .find(attrs={"class": "views_count"})
                        .find("b").text.replace(",", ""))

            comments = int(topic
                           .find(attrs={"class": "posts_count"})
                           .find("b").text.replace(",", ""))

            (DSTopic.delete()
             .where(DSTopic.slug == slug)
             .execute())

            DSTopic.create(
                slug=slug,
                subject=link.text,
                views=views,
                comments=comments,
            )

        if not topics:
            break
        page += 1


def scrape_entry_topic_slugs():
    for entry in DSEntry.select():
        if DSEntryTopicSlug.get_or_none(entry=entry):
            print(f"[topic/slug/skip] {entry.slug}")
            continue

        print(f"[topic/slug] {entry.slug}")
        url = f"https://dynasty-scans.com/chapters/{entry.slug}"
        response = s.get(url, headers=HEADERS).content

        html = BeautifulSoup(response, features="html.parser")
        icon = html.find("i", attrs={"class": "icon-comment"})
        if icon.nextSibling is not None:
            link = icon.parent.attrs["href"]
            topic_slug = link.split("/")[-1].strip()

            (DSEntryTopicSlug.delete()
             .where(DSEntryTopicSlug.entry == entry)
             .execute())

            DSEntryTopicSlug.create(
                entry=entry,
                topic_slug=topic_slug,
            )


def main():
    db.connect()
    db.create_tables([
        DSEntry,
        DSTopic,
        DSEntryTopicSlug,
    ])

    scrape_entries()
    scrape_topics()
    scrape_entry_topic_slugs()


if __name__ == '__main__':
    main()
