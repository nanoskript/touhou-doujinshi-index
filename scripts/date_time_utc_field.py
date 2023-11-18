import datetime
from typing import Optional

from peewee import DateTimeField


class DateTimeUTCField(DateTimeField):
    def db_value(self, value: Optional[datetime.datetime]):
        if value is None:
            return None

        utc = value.astimezone(datetime.timezone.utc)
        utc = utc.replace(tzinfo=None)
        return super().db_value(utc)

    def python_value(self, value):
        if value is None:
            return None

        naive = super().python_value(value)
        return naive.replace(tzinfo=datetime.timezone.utc)
