from typing import Optional

import PIL
import requests
from bs4 import BeautifulSoup
from peewee import SqliteDatabase, Model, BlobField, CharField, IntegerField
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


def ds_entry_tags(entry: DSEntry) -> list[str]:
    tags = []
    for tag in entry.data["tags"]:
        if tag["type"] in ["General", "Pairing"]:
            tags.append(tag["name"])
    return tags


def ds_entry_series(entry: DSEntry) -> Optional[dict]:
    for tag in entry.data["tags"]:
        if tag["type"] == "Series":
            return tag


def topic_comments_by_name(name: str) -> Optional[int]:
    topics = list(DSTopic.select()
                  .where(DSTopic.subject == f"{name} discussion")
                  .order_by(DSTopic.comments))

    if topics:
        # FIXME: If there are multiple topics,
        # we currently take the most conservative non-empty one.
        return topics[0].comments


def ds_entry_comments(entry: DSEntry) -> Optional[int]:
    # Comments on a series are combined.
    series_tag = ds_entry_series(entry)
    if series_tag:
        return None

    # Retrieve topic.
    title = entry.data["title"]
    return topic_comments_by_name(title)


def ds_series_comments(name: str) -> int:
    return topic_comments_by_name(name) or 0


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


def main():
    db.connect()
    db.create_tables([DSEntry, DSTopic])

    scrape_entries()
    scrape_topics()


if __name__ == '__main__':
    main()
