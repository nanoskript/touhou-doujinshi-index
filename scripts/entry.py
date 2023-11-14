import dataclasses
import re
from collections import defaultdict
from datetime import datetime
from typing import Union

from .source_db import DBEntry, pool_translation_ratio, pool_description
from .source_ds import DSEntry, ds_entry_characters, ds_entry_tags
from .source_eh import EHEntry
from .source_md import MDEntry, md_manga_title, md_manga_tags, md_manga_descriptions

Entry = Union[
    DBEntry,
    EHEntry,
    DSEntry,
    MDEntry,
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


ALL_SOURCE_TYPES = {
    "eh": "EH",
    "db": "Danbooru",
    "ds": "Dynasty Scans",
    "md": "MangaDex",
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


def entry_book_title(entry: Entry) -> str:
    if isinstance(entry, DBEntry):
        s = entry_title(entry)
        s = s.removeprefix("Touhou -")
        s = s.removeprefix("東方 -")
        return s.strip()
    if isinstance(entry, EHEntry):
        brackets = r"(\s|\([^()]+\)|(\[[^\[\]]+])|(\{[^{}]+}))+$"
        return re.sub(brackets, "", entry_title(entry))
    if isinstance(entry, DSEntry):
        return entry_title(entry)
    if isinstance(entry, MDEntry):
        s = md_manga_title(entry.manga)
        s = s.removeprefix("Touhou -")
        s = s.removesuffix("(Doujinshi)")
        return s.strip()


def entry_thumbnails(entry: Entry) -> list[bytes]:
    if isinstance(entry, DBEntry):
        return [entry.thumbnail]
    if isinstance(entry, EHEntry):
        return [entry.thumbnail]
    if isinstance(entry, DSEntry):
        return [entry.thumbnail]
    if isinstance(entry, MDEntry):
        return [entry.thumbnail, entry.manga.thumbnail]


def entry_date(entry: Entry) -> datetime:
    if isinstance(entry, DBEntry):
        return datetime.fromisoformat(entry.data["created_at"])
    if isinstance(entry, EHEntry):
        return datetime.fromtimestamp(float(entry.data["posted"]))
    if isinstance(entry, DSEntry):
        return datetime.fromisoformat(entry.data["released_on"])
    if isinstance(entry, MDEntry):
        return datetime.fromisoformat(entry.date)


def entry_url(entry: Entry) -> str:
    if isinstance(entry, DBEntry):
        return f"https://danbooru.donmai.us/pools/{entry.pool_id}"
    if isinstance(entry, EHEntry):
        return f"https://e-hentai.org/g/{entry.gid}/{entry.data['token']}"
    if isinstance(entry, DSEntry):
        return f"https://dynasty-scans.com/chapters/{entry.slug}"
    if isinstance(entry, MDEntry):
        return f"https://mangadex.org/chapter/{entry.slug}"


def entry_language(entry: Entry) -> str:
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


def entry_page_count(entry: Entry) -> int:
    if isinstance(entry, DBEntry):
        return len(entry.posts)
    if isinstance(entry, EHEntry):
        return int(entry.data["filecount"])
    if isinstance(entry, DSEntry):
        return len(entry.data["pages"])
    if isinstance(entry, MDEntry):
        return entry.pages


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
    if isinstance(entry, MDEntry):
        return []


def entry_tags(entry: Entry) -> list[str]:
    if isinstance(entry, DSEntry):
        return ds_entry_tags(entry)
    if isinstance(entry, MDEntry):
        return md_manga_tags(entry.manga)
    return []


def entry_descriptions(entry: Entry) -> dict[str, str]:
    if isinstance(entry, DBEntry):
        description = pool_description(entry)
        if description:
            return {"Danbooru description": description}
    if isinstance(entry, MDEntry):
        return md_manga_descriptions(entry.manga)
    return {}
