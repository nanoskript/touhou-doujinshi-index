from peewee import SqliteDatabase, Model, CharField, BlobField, IntegerField, ForeignKeyField

from .date_time_utc_field import DateTimeUTCField

db = SqliteDatabase("data/index.db")


class BaseModel(Model):
    class Meta:
        database = db


class IndexThumbnail(BaseModel):
    id = CharField(primary_key=True)
    data = BlobField()


class IndexBook(BaseModel):
    id = IntegerField(primary_key=True)
    title = CharField()
    thumbnail = ForeignKeyField(IndexThumbnail)


class IndexTag(BaseModel):
    name = CharField(primary_key=True)


class IndexBookTag(BaseModel):
    book = ForeignKeyField(IndexBook)
    tag = ForeignKeyField(IndexTag)


class IndexCharacter(BaseModel):
    name = CharField(primary_key=True)


class IndexBookCharacter(BaseModel):
    book = ForeignKeyField(IndexBook)
    character = ForeignKeyField(IndexCharacter)


class IndexBookDescription(BaseModel):
    book = ForeignKeyField(IndexBook)
    name = CharField()
    details = CharField()


class IndexEntry(BaseModel):
    id = CharField(primary_key=True)
    book = ForeignKeyField(IndexBook)
    title = CharField()
    url = CharField()
    date = DateTimeUTCField(index=True)
    language = CharField(index=True)
    page_count = IntegerField()
