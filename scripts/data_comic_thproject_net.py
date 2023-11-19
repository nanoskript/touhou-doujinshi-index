import datetime
import io
import os
import zipfile
from pathlib import Path

import rarfile
import requests
from bs4 import BeautifulSoup
from peewee import SqliteDatabase, Model, IntegerField, CharField, BlobField
from tqdm.contrib.concurrent import thread_map, process_map
from PIL import Image

from scripts.date_time_utc_field import DateTimeUTCField
from scripts.utility import HEADERS

DATA_DOWNLOAD_FOLDER = Path("data/cth")
ENTRY_INDICES = list(range(1, 1255))

db = SqliteDatabase("data/cth.db")


class BaseModel(Model):
    class Meta:
        database = db


class CTHEntry(BaseModel):
    id = IntegerField(primary_key=True)
    title = CharField()
    pages = IntegerField()
    thumbnail = BlobField()
    release_date = DateTimeUTCField(null=True)


# Requires a full installation of `unrar` to function correctly.
def build_entry(index: int):
    with open(DATA_DOWNLOAD_FOLDER / f"{index}.html", "rb") as f:
        html = BeautifulSoup(f.read().decode("GBK"), features="html.parser")
        title = html.find("td", string="中文名").nextSibling.text

    # Read archive.
    try:
        archive = rarfile.RarFile(DATA_DOWNLOAD_FOLDER / f"{index}.rar")
    except rarfile.NotRarFile:
        try:
            archive = zipfile.ZipFile(DATA_DOWNLOAD_FOLDER / f"{index}.rar")
        except zipfile.BadZipfile:
            return

    # Read and transcode cover.
    try:
        with open(DATA_DOWNLOAD_FOLDER / f"{index}.jpg", "rb") as f:
            result = io.BytesIO()
            cover = Image.open(io.BytesIO(f.read()))
            cover.save(result, "jpeg")
            thumbnail = result.getvalue()
    except OSError:
        return

    # Find latest timestamp.
    release_date = None
    items = archive.infolist()
    if items:
        timestamps = [item.date_time for item in items]
        release_date = datetime.datetime(*max(timestamps))

    # Count files.
    file_count = 0
    for item in items:
        if not item.is_dir():
            file_count += 1

    # Construct entry.
    return CTHEntry(
        id=index,
        title=title,
        pages=file_count,
        thumbnail=thumbnail,
        release_date=release_date,
    )


def build_entries():
    entries = process_map(build_entry, ENTRY_INDICES, chunksize=4)
    CTHEntry.bulk_create(filter(None, entries))


def download_all():
    # Assumption: site will not be updated.
    base_url = "http://comic.thproject.net"
    url = f"{base_url}/showinfo.php"
    os.makedirs(DATA_DOWNLOAD_FOLDER, exist_ok=True)

    def run_download(index: int):
        try:
            html_path = DATA_DOWNLOAD_FOLDER / f"{index}.html"
            if html_path.exists():
                return

            response = requests.get(url, headers=HEADERS, params={"id": index}).content
            html = BeautifulSoup(response.decode("GBK"), features="html.parser")
            download = html.find("a", string="HTTP下载").attrs["href"]

            archive = requests.get(download, headers=HEADERS).content
            with open(DATA_DOWNLOAD_FOLDER / f"{index}.rar", "wb") as f:
                f.write(archive)

            thumbnail_url = html.find("img").attrs["src"]
            thumbnail = requests.get(f"{base_url}/{thumbnail_url}").content
            with open(DATA_DOWNLOAD_FOLDER / f"{index}.jpg", "wb") as f:
                f.write(thumbnail)

            # Save HTML last to ensure consistency.
            with open(html_path, "wb") as f:
                f.write(response)
        except Exception as e:
            print(f"[download/failure] {index}")
            raise e

    thread_map(run_download, ENTRY_INDICES)


def main():
    db.connect()
    db.drop_tables([CTHEntry])
    db.create_tables([CTHEntry])

    download_all()
    build_entries()


if __name__ == '__main__':
    main()
