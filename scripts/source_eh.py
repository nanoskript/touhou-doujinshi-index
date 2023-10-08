import time

import requests
from peewee import SqliteDatabase, Model, IntegerField, BlobField
from playhouse.sqlite_ext import JSONField
from bs4 import BeautifulSoup

from .utility import HEADERS

db = SqliteDatabase("data/eh.db")


class BaseModel(Model):
    class Meta:
        database = db


class EHEntry(BaseModel):
    gid = IntegerField(unique=True)
    data = JSONField()
    thumbnail = BlobField()


def filter_eh_entries():
    for entry in EHEntry.select().order_by(EHEntry.gid):
        # Ignore image sets.
        if "other:non-h imageset" in entry.data["tags"]:
            continue
        if "[pixiv]" in entry.data["title"].lower():
            continue
        yield entry


def gallery_circles(entry: EHEntry) -> list[str]:
    circles = []
    for tag in entry.data["tags"]:
        if tag.startswith("group:"):
            circles.append(tag.removeprefix("group:"))
    return circles


def gallery_artists(entry: EHEntry) -> list[str]:
    artists = []
    for tag in entry.data["tags"]:
        if tag.startswith("artist:"):
            artists.append(tag.removeprefix("artist:"))
    return artists


def main():
    db.connect()
    db.create_tables([EHEntry])

    latest = list(EHEntry.select().order_by(EHEntry.gid.desc()).limit(1))
    start_gid = latest[0].gid if latest else 1
    search_url = f"https://e-hentai.org/?f_search=parody:%22touhou+project%24%22&f_cats=767&prev={start_gid}"
    while True:
        print(f"[request] {search_url}")
        html = BeautifulSoup(requests.get(search_url, headers=HEADERS).content, features="html.parser")

        galleries = []
        for link_element in html.find_all("a"):
            link = link_element.attrs["href"]
            if link.startswith("https://e-hentai.org/g/"):
                [gid, token, _end] = link.split("/")[-3:]
                galleries.append([int(gid), token])

        if not galleries:
            break

        metadata = requests.post(
            "https://api.e-hentai.org/api.php",
            headers=HEADERS,
            json={
                "method": "gdata",
                "gidlist": galleries,
                "namespace": 1
            }
        ).json()["gmetadata"]

        for gallery in metadata:
            gid = gallery["gid"]
            if EHEntry.select().where(EHEntry.gid == gid):
                print(f"[gallery/skip] {gid}")
                continue

            print(f"[gallery/new] {gid}")
            thumbnail_url = gallery["thumb"].replace("l.jpg", "300.jpg")
            thumbnail = requests.get(thumbnail_url, headers=HEADERS).content
            EHEntry.create(gid=gid, data=gallery, thumbnail=thumbnail)
            time.sleep(1)

        previous_url_element = html.find("a", attrs={"id": "uprev"})
        if previous_url_element is None:
            break

        # Delay for 10 seconds.
        search_url = previous_url_element.attrs.get("href", None)
        time.sleep(10)


if __name__ == '__main__':
    main()
