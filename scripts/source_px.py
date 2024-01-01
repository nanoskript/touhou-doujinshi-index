import json
import re
import time

import requests
from peewee import SqliteDatabase, Model, IntegerField
from playhouse.sqlite_ext import JSONField

from scripts.source_db import DBEntry, db_pixiv_id
from scripts.utility import HEADERS

db = SqliteDatabase("data/px.db")
REQUEST_DELAY_SECONDS = 2.5


class BaseModel(Model):
    class Meta:
        database = db


class PXEntry(BaseModel):
    id = IntegerField(primary_key=True)
    data = JSONField()


# Script must run after Danbooru sourcing.
def gather_pixiv_ids() -> list[int]:
    ids = []
    for entry in DBEntry.select():
        ids.append(db_pixiv_id(entry))
    return list(set(filter(None, ids)))


def get_pixiv_entry(pixiv_id: int) -> PXEntry | None:
    entry = PXEntry.get_or_none(id=pixiv_id)
    if entry and not entry.data["error"]:
        return entry


def request_pixiv_metadata(pixiv_id: int):
    time.sleep(REQUEST_DELAY_SECONDS)
    response = requests.get(
        "https://rdtls.nl/pixiv.php",
        params={"site": "pixiv", "id": pixiv_id},
        headers=HEADERS,
    )

    if not response.ok:
        print(f"[pixiv/failure] {pixiv_id}")
        return

    data = response.content.decode("utf-8", errors="replace")
    pattern = r"syntaxHighlight\(\s*JSON\.stringify\((.+), null, 2\)"
    match = re.search(pattern, data, re.S)
    return json.loads(match.group(1))


def main():
    db.connect()
    db.create_tables([PXEntry])
    ids = gather_pixiv_ids()

    for pixiv_id in ids:
        if PXEntry.get_or_none(id=pixiv_id):
            print(f"[pixiv/skip] {pixiv_id}")
            continue

        print(f"[pixiv/new] {pixiv_id}")
        data = request_pixiv_metadata(pixiv_id)
        PXEntry.create(id=pixiv_id, data=data)


if __name__ == '__main__':
    main()
