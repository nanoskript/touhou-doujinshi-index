import time

import requests
from peewee import SqliteDatabase, Model, IntegerField, BlobField
from playhouse.sqlite_ext import JSONField
from bs4 import BeautifulSoup

from .date_time_utc_field import DateTimeUTCField
from .utility import HEADERS, tracing_response_hook, utcnow

REFRESH_COUNT = 100
requests = requests.Session()
requests.hooks["response"].append(tracing_response_hook)
db = SqliteDatabase("data/eh.db")


class BaseModel(Model):
    class Meta:
        database = db


class EHEntry(BaseModel):
    gid = IntegerField(primary_key=True)
    data = JSONField()
    thumbnail = BlobField()
    last_fetched = DateTimeUTCField(null=True)


def filter_eh_entries():
    for entry in EHEntry.select().order_by(EHEntry.gid):
        # Ignore image sets.
        if "other:non-h imageset" in entry.data["tags"]:
            continue
        if "[pixiv]" in entry.data["title"].lower():
            continue
        if "●pixiv●" in entry.data["title"].lower():
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


def gallery_metadata(gidlist: list) -> list[dict]:
    # The gdata API accepts at most 25 gids per request.
    metadata = []
    for start in range(0, len(gidlist), 25):
        if start:
            time.sleep(1)
        metadata += requests.post(
            "https://api.e-hentai.org/api.php",
            headers=HEADERS,
            json={
                "method": "gdata",
                "gidlist": gidlist[start:start + 25],
                "namespace": 1
            }
        ).json()["gmetadata"]
    return metadata


def scrape_galleries():
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

        for gallery in gallery_metadata(galleries):
            gid = gallery["gid"]
            if EHEntry.select().where(EHEntry.gid == gid):
                print(f"[gallery/skip] {gid}")
                continue

            print(f"[gallery/new] {gid}")
            thumbnail_url = gallery["thumb"].replace("l.jpg", "300.jpg")
            thumbnail = requests.get(thumbnail_url, headers=HEADERS).content
            EHEntry.create(gid=gid, data=gallery, thumbnail=thumbnail, last_fetched=utcnow())
            time.sleep(1)

        previous_url_element = html.find("a", attrs={"id": "uprev"})
        if previous_url_element is None:
            break

        # Delay for 10 seconds.
        search_url = previous_url_element.attrs.get("href", None)
        time.sleep(10)


def refresh_entries():
    gidlist = []
    indexed = {}
    for entry in EHEntry.select().order_by(EHEntry.last_fetched.asc()).limit(REFRESH_COUNT):
        token = entry.data.get("token")
        if token is None:
            entry.last_fetched = utcnow()
            entry.save()
            print(f"[refresh/skip] {entry.gid}")
            continue
        gidlist.append([entry.gid, token])
        indexed[entry.gid] = entry

    try:
        metadata = gallery_metadata(gidlist)
    except Exception as error:
        # Leave rows untouched so they retry next run.
        print(f"[refresh/fail] {error}")
        return

    for gallery in metadata:
        entry = indexed[gallery["gid"]]
        if "error" in gallery:
            # The gallery is gone: keep the stored data, only rotate it out.
            print(f"[refresh/gone] {entry.gid}")
        else:
            entry.data = gallery
            print(f"[refresh/update] {entry.gid}")
        entry.last_fetched = utcnow()
        entry.save()


def main():
    db.connect()
    db.create_tables([EHEntry])
    scrape_galleries()
    refresh_entries()


if __name__ == '__main__':
    main()
