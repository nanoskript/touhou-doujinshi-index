from tqdm import tqdm

from scripts.source_ds import filter_ds_entries
from .character_index import CharacterIndex
from .source_md import all_md_chapters
from .entry import *
from .entry_list_image_tree import EntryListImageTree
from .index import EntryList, db, IndexEntry, IndexBook, IndexCharacter, IndexBookCharacter, IndexThumbnail
from .source_db import filter_db_entries
from .source_eh import gallery_circles, gallery_artists, filter_eh_entries


def form_gallery_groups() -> EntryListImageTree:
    # Bucket by circles or artists first.
    orphan_entries = []
    works_by_circle = defaultdict(list)
    for entry in filter_eh_entries():
        circles = gallery_circles(entry)
        artists = gallery_artists(entry)

        if not (circles or artists):
            orphan_entries.append(entry)
            continue

        # Arrange into unique unordered key.
        key = tuple(sorted(circles or artists))
        works_by_circle[key].append(entry)

    lists = []
    for entries in tqdm(works_by_circle.values()):
        tree = EntryListImageTree()
        for entry in entries:
            if "language:translated" not in entry.data["tags"]:
                tree.add_or_create(entry, similarity=0.8)
        for entry in entries:
            if "language:translated" in entry.data["tags"]:
                tree.add_or_create(entry, similarity=0.8)
        lists += tree.all_entry_lists()

    tree = EntryListImageTree(lists)
    for entry in orphan_entries:
        if "language:translated" not in entry.data["tags"]:
            tree.add_or_create(entry, similarity=0.9)
    for entry in orphan_entries:
        if "language:translated" in entry.data["tags"]:
            tree.add_or_create(entry, similarity=0.9)
    return tree


def entry_list_characters(index: CharacterIndex, entry_list: EntryList) -> list[str]:
    characters = []
    for entry in entry_list.entries:
        characters += entry_characters(entry)
    characters = [index.canonicalize(name) for name in characters]
    return list(sorted(set(characters)))


def main():
    tree = form_gallery_groups()
    for entry in tqdm(filter_db_entries()):
        tree.add_or_create(entry, similarity=0.9)
    for entry in tqdm(filter_ds_entries()):
        tree.add_or_create(entry, similarity=0.9)
    for entry in tqdm(all_md_chapters()):
        tree.add_or_create(entry, similarity=0.9)
    lists = tree.all_entry_lists()

    # Construct database.
    tables = [
        IndexEntry,
        IndexBook,
        IndexCharacter,
        IndexBookCharacter,
        IndexThumbnail,
    ]

    db.connect()
    character_index = CharacterIndex()
    with db.atomic():
        db.drop_tables(tables)
        db.create_tables(tables)

        for entry_list in tqdm(lists):
            canonical = entry_list.entries[0]
            thumbnail = IndexThumbnail.create(
                id=entry_key(canonical),
                data=entry_thumbnails(canonical)[0],
            )

            book = IndexBook.create(
                title=entry_book_title(canonical),
                thumbnail=thumbnail,
            )

            for name in entry_list_characters(character_index, entry_list):
                (character, _created) = IndexCharacter.get_or_create(name=name)
                IndexBookCharacter.create(book=book, character=character)

            IndexEntry.bulk_create([IndexEntry(
                id=entry_key(entry),
                book=book,
                title=entry_title(entry),
                url=entry_url(entry),
                date=entry_date(entry),
                language=entry_language(entry),
                page_count=entry_page_count(entry),
            ) for entry in entry_list.entries])


if __name__ == '__main__':
    main()
