import time

import requests
from bs4 import BeautifulSoup
from peewee import Model, SqliteDatabase, IntegerField, CharField, BlobField
from requests.adapters import HTTPAdapter
from urllib3.util import create_urllib3_context
import urllib.parse

# Outdated cipher is being used.
CIPHER = "ALL:@SECLEVEL=1"
CONNECTION_FAILURE_DELAY_SECONDS = 1
CONNECTION_FAILURE_LIMIT = 10
db = SqliteDatabase("data/mb.db")


class CustomCipherAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        context = create_urllib3_context(ciphers=CIPHER)
        kwargs['ssl_context'] = context
        return super(CustomCipherAdapter, self).init_poolmanager(*args, **kwargs)


class BaseModel(Model):
    class Meta:
        database = db


class MBEntry(BaseModel):
    id = IntegerField(primary_key=True)
    data = CharField()
    thumbnail = BlobField(null=True)


session = requests.Session()
session.mount("https://", CustomCipherAdapter())


def get(url, **kwargs):
    failures = 0
    while True:
        try:
            return session.get(url, **kwargs)
        except requests.exceptions.ConnectionError as e:
            print(f"[url/retry] {url}")
            time.sleep(CONNECTION_FAILURE_DELAY_SECONDS)

            failures += 1
            if failures >= CONNECTION_FAILURE_LIMIT:
                raise e


def source_mb():
    page_number = 1
    while True:
        print(f"[page] {page_number}")
        response = get(
            "https://www.melonbooks.co.jp/tags/index.php",
            params={
                "genre": "東方Project",
                "fromagee_flg": 0,
                "disp_number": 100,
                "text_type": "all",
                "category_ids": 1,
                "child_category_ids": 9,
                "product_type": "all",
                "is_end_of_sale[]": 1,
                "is_end_of_sale2": 1,
                "pageno": page_number,
            }
        )

        content = response.content.decode("utf-8", "ignore")
        html = BeautifulSoup(content, features="html.parser")
        items = html.find("div", attrs={"class": "item-list"}).find_all("li")

        for item in items:
            link = item.find("a")
            product_id = int(link.attrs["href"].split("=")[-1])
            thumbnail_url = f"https:{link.find('img').attrs['data-src']}"
            print(f"[product] {product_id}")

            # TODO: Do not skip entries with empty thumbnails.
            if MBEntry.get_or_none(MBEntry.id == product_id):
                print(f"[product/skip] {product_id}")
                continue

            thumbnail = None
            thumbnail_parsed = urllib.parse.urlparse(thumbnail_url)
            thumbnail_query = urllib.parse.parse_qs(thumbnail_parsed.query)
            if "image" in thumbnail_query:
                thumbnail = get(thumbnail_url).content

            detail_url = "https://www.melonbooks.co.jp/detail/detail.php"
            data = get(detail_url, params={"product_id": product_id}).content
            MBEntry.create(
                id=product_id,
                data=data,
                thumbnail=thumbnail,
            )

        if not items:
            break
        page_number += 1


def main():
    db.connect()
    db.create_tables([MBEntry])
    source_mb()


if __name__ == '__main__':
    main()
