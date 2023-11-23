import requests
from bs4 import BeautifulSoup
from peewee import SqliteDatabase, Model, IntegerField, CharField, BlobField

db = SqliteDatabase("data/tora.db")


class BaseModel(Model):
    class Meta:
        database = db


class ToraEntry(BaseModel):
    id = IntegerField(primary_key=True)
    data = CharField()
    thumbnail = BlobField(null=True)


def source_tora():
    page_number = 1
    while True:
        print(f"[page] {page_number}")
        response = requests.get(
            "https://ecs.toranoana.jp/tora/ec/app/catalog/list",
            params={
                "coterieGenreCode1": "GNRN00000696",
                "commodity_kind_name": "同人誌",
                "currentPage": page_number,
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
            data = requests.get(product_url).content
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
