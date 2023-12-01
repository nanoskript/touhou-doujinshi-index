import dataclasses
import re
from collections import defaultdict
from datetime import datetime
from typing import Union, Optional

from .data_comic_thproject_net import CTHEntry
from .data_doujinshi_org import OrgEntry, org_entry_release_date
from .source_db import DBEntry, pool_translation_ratio, DBPoolDescription, DBComments
from .source_ds import DSEntry, ds_entry_characters, ds_entry_tags, ds_entry_series, ds_entry_comments, \
    ds_series_comments
from .source_eh import EHEntry
from .source_mb import MBDataEntry
from .source_md import MDEntry, md_manga_title, md_manga_tags, md_manga_descriptions, md_manga_comments
from .source_tora import ToraDataEntry

Entry = Union[
    DBEntry,
    EHEntry,
    DSEntry,
    MDEntry,
    OrgEntry,
    CTHEntry,
    MBDataEntry,
    ToraDataEntry,
]


@dataclasses.dataclass()
class EntryList:
    entries: list[Entry]


def entry_key(entry: Entry) -> str:
    if isinstance(entry, DBEntry):
        return f"db-{entry.pool_id}"
    if isinstance(entry, EHEntry):
        return f"eh-{entry.gid}"
    if isinstance(entry, DSEntry):
        return f"ds-{entry.slug}"
    if isinstance(entry, MDEntry):
        return f"md-{entry.slug}"
    if isinstance(entry, OrgEntry):
        return f"org-{entry.id}"
    if isinstance(entry, CTHEntry):
        return f"cth-{entry.id}"
    if isinstance(entry, MBDataEntry):
        return f"mb-{entry.id}"
    if isinstance(entry, ToraDataEntry):
        return f"tora-{entry.id}"


ALL_SOURCE_TYPES = {
    "eh": "EH",
    "db": "Danbooru",
    "ds": "Dynasty Scans",
    "md": "MangaDex",
    "org": "doujinshi.org",
    "cth": "comic.thproject.net",
    "mb": "Melonbooks",
    "tora": "Toranoana",
}


def entry_key_readable_source(key: str) -> str:
    for prefix, name in ALL_SOURCE_TYPES.items():
        if key.startswith(prefix):
            return name


def entry_title(entry: Entry) -> str:
    if isinstance(entry, DBEntry):
        return entry.data["name"].replace("_", " ")
    if isinstance(entry, EHEntry):
        return entry.data["title"].replace("_", " ")
    if isinstance(entry, DSEntry):
        return entry.data["title"]
    if isinstance(entry, MDEntry):
        return entry.title
    if isinstance(entry, OrgEntry):
        return entry.title
    if isinstance(entry, CTHEntry):
        return entry.title
    if isinstance(entry, MBDataEntry):
        return entry.title
    if isinstance(entry, ToraDataEntry):
        return entry.title


def entry_book_title(entry: Entry) -> str:
    if isinstance(entry, DBEntry):
        s = entry_title(entry)
        s = s.removeprefix("Touhou -")
        s = s.removeprefix("東方 -")
        return s.strip()
    if isinstance(entry, EHEntry):
        brackets = r"(\s|\([^()]+\)|(\[[^\[\]]+])|(\{[^{}]+}))+$"
        return re.sub(brackets, "", entry_title(entry))
    if isinstance(entry, MDEntry):
        s = md_manga_title(entry.manga)
        s = s.removeprefix("Touhou -")
        s = s.removesuffix("(Doujinshi)")
        return s.strip()
    return entry_title(entry)


# FIXME: Currently, we assume there is at least one thumbnail.
def entry_thumbnails(entry: Entry) -> list[bytes]:
    if isinstance(entry, DBEntry):
        return [entry.thumbnail]
    if isinstance(entry, EHEntry):
        return [entry.thumbnail]
    if isinstance(entry, DSEntry):
        return [entry.thumbnail]
    if isinstance(entry, MDEntry):
        return [entry.thumbnail, entry.manga.thumbnail]
    if isinstance(entry, OrgEntry):
        return [entry.thumbnail] if entry.thumbnail else None
    if isinstance(entry, CTHEntry):
        return [entry.thumbnail]
    if isinstance(entry, MBDataEntry):
        return [entry.thumbnail]
    if isinstance(entry, ToraDataEntry):
        return [entry.thumbnail]


def entry_date(entry: Entry) -> Optional[datetime]:
    if isinstance(entry, DBEntry):
        return datetime.fromisoformat(entry.data["created_at"])
    if isinstance(entry, EHEntry):
        return datetime.fromtimestamp(float(entry.data["posted"]))
    if isinstance(entry, DSEntry):
        return datetime.fromisoformat(entry.data["released_on"])
    if isinstance(entry, MDEntry):
        return datetime.fromisoformat(entry.date)
    if isinstance(entry, OrgEntry):
        return org_entry_release_date(entry)
    if isinstance(entry, CTHEntry):
        return entry.release_date
    if isinstance(entry, MBDataEntry):
        return entry.release_date
    if isinstance(entry, ToraDataEntry):
        return entry.release_date


def entry_url(entry: Entry) -> Optional[str]:
    if isinstance(entry, DBEntry):
        return f"https://danbooru.donmai.us/pools/{entry.pool_id}"
    if isinstance(entry, EHEntry):
        return f"https://e-hentai.org/g/{entry.gid}/{entry.data['token']}"
    if isinstance(entry, DSEntry):
        return f"https://dynasty-scans.com/chapters/{entry.slug}"
    if isinstance(entry, MDEntry):
        return f"https://mangadex.org/chapter/{entry.slug}"
    if isinstance(entry, CTHEntry):
        return f"http://comic.thproject.net/showinfo.php?id={entry.id}"
    if isinstance(entry, MBDataEntry):
        return f"https://www.melonbooks.co.jp/detail/detail.php?product_id={entry.id}"
    if isinstance(entry, ToraDataEntry):
        return f"https://ecs.toranoana.jp/tora/ec/item/{entry.id}/"


# If absent, the entry is considered to be metadata-only.
def entry_language(entry: Entry) -> Optional[str]:
    if isinstance(entry, DBEntry):
        if pool_translation_ratio(entry) >= 0.5:
            return "English"
        return "Japanese"
    if isinstance(entry, EHEntry):
        for tag in entry.data["tags"]:
            if tag.startswith("language:"):
                language = tag.removeprefix("language:")
                if language in ["rewrite", "translated"]:
                    continue
                return language.title()
        return "Japanese"
    if isinstance(entry, DSEntry):
        return "English"
    if isinstance(entry, MDEntry):
        return entry.language
    if isinstance(entry, CTHEntry):
        return "Chinese"


def entry_page_count(entry: Entry) -> Optional[int]:
    if isinstance(entry, DBEntry):
        return len(entry.posts)
    if isinstance(entry, EHEntry):
        return int(entry.data["filecount"])
    if isinstance(entry, DSEntry):
        return len(entry.data["pages"])
    if isinstance(entry, MDEntry):
        return entry.pages
    if isinstance(entry, OrgEntry):
        return entry.pages
    if isinstance(entry, CTHEntry):
        return entry.pages
    if isinstance(entry, MBDataEntry):
        return entry.pages
    if isinstance(entry, ToraDataEntry):
        return entry.pages


# List of strings that are guaranteed to be characters.
def entry_characters(entry: Entry) -> list[str]:
    if isinstance(entry, DBEntry):
        appearances = defaultdict(int)
        for post in entry.posts:
            for tag in post["tag_string_character"].split():
                appearances[tag.replace("_", " ").title()] += 1

        characters = []
        for character, count in appearances.items():
            if count >= 0.2 * len(entry.posts):
                characters.append(character)
        return list(sorted(characters))
    if isinstance(entry, EHEntry):
        characters = []
        for tag in entry.data["tags"]:
            if tag.startswith("character:"):
                character = tag.removeprefix("character:")
                characters.append(character.title())
        return list(sorted(characters))
    if isinstance(entry, DSEntry):
        return ds_entry_characters(entry)
    if isinstance(entry, OrgEntry):
        return entry.characters
    return []


# List of strings that may contain characters.
def entry_characters_plausible(entry: Entry) -> list[str]:
    if isinstance(entry, MBDataEntry):
        return entry.characters
    return []


def entry_tags(entry: Entry) -> list[str]:
    if isinstance(entry, DSEntry):
        return ds_entry_tags(entry)
    if isinstance(entry, MDEntry):
        return md_manga_tags(entry.manga)
    return []


def entry_descriptions(entry: Entry) -> dict[str, str]:
    if isinstance(entry, DBEntry):
        row = DBPoolDescription.get_or_none(DBPoolDescription.pool == entry)
        if row and row.html:
            return {"Danbooru description": row.html}
    if isinstance(entry, MDEntry):
        return md_manga_descriptions(entry.manga)
    if isinstance(entry, OrgEntry) and entry.comments:
        return {"doujinshi.org comments": entry.comments}
    if isinstance(entry, MBDataEntry) and entry.comments:
        return {"Melonbooks description (Japanese)": entry.comments}
    if isinstance(entry, ToraDataEntry) and entry.comments:
        return {"Toranoana description (Japanese)": entry.comments}
    return {}


def entry_comments(entry: Entry) -> Optional[int]:
    if isinstance(entry, DBEntry):
        return len(DBComments.get(pool=entry).comments)
    if isinstance(entry, DSEntry):
        return ds_entry_comments(entry)
    if isinstance(entry, MDEntry):
        return entry.comments


@dataclasses.dataclass()
class EntrySeries:
    key: str
    title: str
    comments: int


def entry_series(entry: Entry) -> Optional[EntrySeries]:
    if isinstance(entry, MDEntry):
        key = f"md-{entry.manga.slug}"
        title = entry_book_title(entry)
        comments = md_manga_comments(entry.manga)
        return EntrySeries(key=key, title=title, comments=comments)
    if isinstance(entry, DSEntry):
        tag = ds_entry_series(entry)
        if tag:
            key = f"ds-{tag['permalink']}"
            comments = ds_series_comments(tag["name"])
            return EntrySeries(key, title=tag["name"], comments=comments)
