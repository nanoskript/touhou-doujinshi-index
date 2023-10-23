import datetime

from peewee import DateTimeField


class DateTimeUTCField(DateTimeField):
    def db_value(self, value: datetime.datetime):
        utc = value.astimezone(datetime.timezone.utc)
        utc = utc.replace(tzinfo=None)
        return super().db_value(utc)

    def python_value(self, value):
        naive = super().python_value(value)
        return naive.replace(tzinfo=datetime.timezone.utc)
