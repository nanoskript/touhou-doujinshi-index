import glob
from datetime import datetime
from typing import Optional
from zipfile import ZipFile

import ftfy
from peewee import SqliteDatabase, Model, BlobField, IntegerField, CharField
from playhouse.reflection import generate_models
from playhouse.sqlite_ext import JSONField
from tqdm import tqdm
from split_file_reader import SplitFileReader

db = SqliteDatabase("data/org.db")

# Must be configured.
DOUJINSHI_ORG_DB_PATH = "../doujinshi-org/doujinshi.org.db"
DOUJINSHI_ORG_IMAGES_PATH = "../doujinshi-org/Cache/doujinshi.org_dump/Images"


class BaseModel(Model):
    class Meta:
        database = db


class OrgEntry(BaseModel):
    id = IntegerField(primary_key=True)
    titles = JSONField()
    release_date = CharField()
    characters = JSONField()
    authors = JSONField()
    circles = JSONField()
    pages = IntegerField(null=True)
    thumbnail = BlobField(null=True)
    comments = CharField(null=True)


def org_entry_release_date(entry: OrgEntry) -> Optional[datetime]:
    if entry.release_date == "0000-00-00":
        return None

    date = datetime.fromisoformat(entry.release_date)
    if date.year <= 2003:
        return None

    return date


def extract_entries():
    org_db = SqliteDatabase(DOUJINSHI_ORG_DB_PATH)
    org_models = generate_models(org_db)
    globals().update(org_models)
    print(f"[models] {list(org_models.keys())}")

    image_archives = glob.glob(f"{DOUJINSHI_ORG_IMAGES_PATH}/*.zip.*")
    archive = ZipFile(SplitFileReader(sorted(image_archives)))
    no_picture = archive.read("big/0/474.jpg")

    def read_thumbnail(book_id: int) -> Optional[bytes]:
        try:
            buffer = archive.read(f"big/{book_id // 2000}/{book_id}.jpg")
            if buffer != no_picture:
                return buffer
        except KeyError:
            pass

    safe_for_work_age = 0
    parody = Parody.get(Parody.name_en == "Touhou Project")
    books = list(Book.select()
                 .join(BookParody, on=(Book.book_id == BookParody.book_id))
                 .where(BookParody.parody_id == parody.parody_id)
                 .where(Book.age == safe_for_work_age))

    entries = []
    for book in tqdm(books):
        thumbnail = read_thumbnail(book.book_id)
        if not thumbnail:
            continue

        characters = [character.name_en
                      for character in Character.select()
                      .join(BookCharacter, on=(Character.character_id == BookCharacter.character_id))
                      .where(BookCharacter.book_id == book.book_id)]

        authors = [author.name_en or author.name_jp
                   for author in Author.select()
                   .join(BookAuthor, on=(Author.author_id == BookAuthor.author_id))
                   .where(BookAuthor.book_id == book.book_id)]

        circles = [circle.name_en or circle.name_jp
                   for circle in Circle.select()
                   .join(BookCircle, on=(Circle.circle_id == BookCircle.circle_id))
                   .where(BookCircle.book_id == book.book_id)]

        entries.append(OrgEntry(
            id=book.book_id,
            titles=list(filter(None, [book.name_en, book.name_jp])),
            release_date=book.released,
            characters=characters,
            authors=authors,
            circles=circles,
            pages=book.pages or None,
            thumbnail=thumbnail,
            comments=ftfy.fix_text(book.info) or None,
        ))

    batch_size = 10000
    OrgEntry.bulk_create(entries, batch_size)


def main():
    db.connect()
    db.drop_tables([OrgEntry])
    db.create_tables([OrgEntry])
    extract_entries()


if __name__ == '__main__':
    main()
