import dataclasses
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from lxml import etree
from lxml.cssselect import CSSSelector
from peewee import SqliteDatabase, Model, CharField, BlobField

from scripts.utility import get_with_proxy, strain_html

db = SqliteDatabase("data/tora.db")


class BaseModel(Model):
    class Meta:
        database = db


class ToraEntry(BaseModel):
    id = CharField(primary_key=True)
    data = CharField()
    thumbnail = BlobField(null=True)


@dataclasses.dataclass()
class ToraDataEntry:
    id: str
    title: str
    pages: int
    release_date: datetime
    comments: str
    thumbnail: bytes


def tora_entries() -> list[ToraDataEntry]:
    entries = []
    select_table_rows = CSSSelector("tr")
    select_comments = CSSSelector(".product-detail-comment-item")
    for entry in ToraEntry.select():
        title = strain_html(entry.data, "h1", '<h1 class="product-detail-desc-title">')
        title = etree.tostring(etree.HTML(title), method="text", encoding="unicode").strip()

        table = {}
        details = strain_html(entry.data, "div", '<div class="product-detail-spec">')
        for row in select_table_rows(etree.HTML(details)):
            header, value = row.getchildren()
            header = etree.tostring(header, method="text", encoding="unicode").strip()
            value = etree.tostring(value, method="text", encoding="unicode").strip()
            table[header] = value

        release_date = None
        release_date_key = "発行日"
        if release_date_key in table:
            release_date = datetime.strptime(table[release_date_key], "%Y/%m/%d")

        pages = None
        pages_key = "種別/サイズ"
        if pages_key in table:
            tokens = table[pages_key].split()
            if tokens[-1].endswith("p"):
                pages = int(tokens[-1][:-1])

        comments = []
        description = strain_html(entry.data, "div", '<div class="product-detail-comment">')
        for comment in select_comments(etree.HTML(description)):
            heading = comment.find("h3")
            content = etree.tostring(heading.getnext(), method="html", encoding="unicode")
            comments.append(f"<b>{heading.text}</b>\n{content}")

        entries.append(ToraDataEntry(
            id=entry.id,
            title=title,
            pages=pages,
            release_date=release_date,
            comments=("".join(comments)),
            thumbnail=entry.thumbnail,
        ))
    return entries


def source_tora():
    directories = [
        ("https://ecs.toranoana.jp/tora/ec/app/catalog/list", {
            "coterieGenreCode1": "GNRN00000696",
            "commodity_kind_name": "同人誌",
        }),
        ("https://ecs.toranoana.jp/tora_d/digi/app/catalog/list", {
            "coterieGenreCode1": "GNRN00000696"
        })
    ]

    for base_url, params in directories:
        page_number = 1
        while True:
            print(f"[page] {page_number}")
            response = get_with_proxy(
                base_url,
                retries=10,
                params={
                    **params,
                    "currentPage": str(page_number),
                }
            )

            html = BeautifulSoup(response.content, features="html.parser")
            items = html.find_all(attrs={"class": "product-list-item"})
            for item in items:
                link = item.find("a", attrs={"class": "product-list-img-inn"})
                product_id = link.attrs["href"].split("/")[-2]
                image_url = item.find("img").attrs["data-src"]
                print(f"[product] {product_id}")

                # TODO: Do not skip entries with empty thumbnails.
                if ToraEntry.get_or_none(ToraEntry.id == product_id):
                    print(f"[product/skip] {product_id}")
                    continue

                # FIXME: Handle empty thumbnail.
                thumbnail = requests.get(image_url).content
                product_url = f"https://ecs.toranoana.jp/tora/ec/item/{product_id}/"
                data = get_with_proxy(product_url, retries=10).content
                ToraEntry.create(
                    id=product_id,
                    data=data,
                    thumbnail=thumbnail,
                )

            if not items:
                break
            page_number += 1


def main():
    db.connect()
    db.create_tables([ToraEntry])
    source_tora()


if __name__ == '__main__':
    main()
