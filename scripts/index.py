import dataclasses

from peewee import SqliteDatabase, Model, CharField, BlobField, IntegerField, ForeignKeyField

from .date_time_utc_field import DateTimeUTCField
from .entry import Entry

db = SqliteDatabase("data/index.db")


class BaseModel(Model):
    class Meta:
        database = db


class IndexThumbnail(BaseModel):
    id = CharField(primary_key=True)
    data = BlobField()


class IndexBook(BaseModel):
    title = CharField()
    thumbnail = ForeignKeyField(IndexThumbnail)


class IndexCharacter(BaseModel):
    name = CharField(primary_key=True)


class IndexBookCharacter(BaseModel):
    book = ForeignKeyField(IndexBook)
    character = ForeignKeyField(IndexCharacter)


class IndexTag(BaseModel):
    name = CharField(primary_key=True)


class IndexBookTag(BaseModel):
    book = ForeignKeyField(IndexBook)
    tag = ForeignKeyField(IndexTag)


class IndexEntry(BaseModel):
    id = CharField(primary_key=True)
    book = ForeignKeyField(IndexBook)
    title = CharField()
    url = CharField()
    date = DateTimeUTCField(index=True)
    language = CharField(index=True)
    page_count = IntegerField()


@dataclasses.dataclass()
class EntryList:
    entries: list[Entry]
