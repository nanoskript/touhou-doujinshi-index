import dataclasses
import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from lxml.cssselect import CSSSelector
from peewee import Model, SqliteDatabase, IntegerField, CharField, BlobField
from requests.adapters import HTTPAdapter
from urllib3.util import create_urllib3_context
import urllib.parse
from lxml import etree

from .utility import strain_html, get_with_proxy

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


@dataclasses.dataclass()
class MBDataEntry:
    id: int
    title: str
    pages: int
    release_date: datetime
    comments: str
    characters: list[str]
    circles: list[str]
    authors: list[str]
    thumbnail: bytes


def mb_entries() -> list[MBDataEntry]:
    entries = []
    select_comments = CSSSelector(".item-detail.mt24")
    select_table_headers = CSSSelector("th")
    select_links = CSSSelector("a")
    for entry in MBEntry.select():
        page = strain_html(entry.data, "div", '<div class="item-page">')
        tree = etree.HTML(page)
        if not entry.thumbnail:
            continue

        table = {}
        for header in select_table_headers(tree):
            table[header.text] = header.getnext().text.strip()

        release_date = None
        release_date_key = "発行日"
        if release_date_key in table:
            release_date = datetime.strptime(table[release_date_key], "%Y/%m/%d")

        pages = None
        pages_key = "総ページ数・CG数・曲数"
        if pages_key in table:
            pages = int(table[pages_key])

        comments = []
        for comment in select_comments(tree):
            heading = comment.find("h3")
            content = etree.tostring(heading.getnext(), method="html", encoding="unicode")
            comments.append(f"<b>{heading.text}</b>\n{content}")

        characters, authors, circles = [], [], []
        for link in select_links(tree):
            href = link.attrib["href"]
            text = link.text and link.text.strip()

            prefix = "https://www.melonbooks.co.jp/tags/index.php?chara="
            if href.startswith(prefix):
                characters.append(text.removeprefix("#"))

            suffix = "&text_type=author"
            if href.endswith(suffix):
                authors.append(text)

            prefix = "https://www.melonbooks.co.jp/circle/index.php?circle_id="
            if href.startswith(prefix) and ("作品数" not in text):
                circles.append(text)

        entries.append(MBDataEntry(
            id=entry.id,
            title=tree.find(".//h1").text,
            pages=pages,
            release_date=release_date,
            comments=("<br/>".join(comments)),
            characters=characters,
            circles=circles,
            authors=authors,
            thumbnail=entry.thumbnail,
        ))
    return entries


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
        response = get_with_proxy(
            "https://www.melonbooks.co.jp/tags/index.php",
            retries=10,
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
            data = get_with_proxy(detail_url, retries=10, params={"product_id": product_id}).content
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
