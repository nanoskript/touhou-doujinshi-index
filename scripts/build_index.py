from tqdm import tqdm
from scipy.cluster.hierarchy import DisjointSet

from scripts.source_ds import filter_ds_entries
from scripts.source_mb import mb_entries
from scripts.source_tora import tora_entries
from .character_index import CharacterIndex
from .source_md import all_md_chapters
from .entry import *
from .entry_list_image_tree import EntryListImageTree
from .index import *
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


def entry_list_tags(entry_list: EntryList) -> list[str]:
    synonyms = {
        "Girls' Love": "Yuri",
        "Slice of Life": "Slice of life",
        "School Life": "School life",
        "Time Travel": "Time travel",
        "Sci-Fi": "Sci-fi",
        "4-Koma": "4-koma",
        "Full Color": "Full color",
        "Gender bender": "Genderswap",
        "Alien": "Aliens",
        "Ghost": "Ghosts",
        "Vampire": "Vampires",
    }

    tags = []
    for entry in entry_list.entries:
        for tag in entry_tags(entry):
            tags.append(synonyms.get(tag, tag))
    return list(sorted(set(tags)))


def entry_list_descriptions(entry_list: EntryList):
    descriptions = {}
    for entry in entry_list.entries:
        descriptions.update(entry_descriptions(entry))
    return descriptions


def entry_list_canonical(entry_list: EntryList) -> Optional[Entry]:
    return entry_list.entries[0]


# Assumes entry list indices will be identical to book IDs.
def coalesce_book_series(lists: list[EntryList]) -> dict[EntrySeries, list[int]]:
    # Combine overlapping series.
    tree = DisjointSet([])
    for item in lists:
        last_series = None
        for entry in item.entries:
            series = entry_series(entry)
            if series:
                tree.add(series)
                if last_series is not None:
                    tree.merge(last_series, series)
                last_series = series

    # Determine series for each book.
    pools = defaultdict(list)
    for book_id, item in enumerate(lists):
        for entry in item.entries:
            series = entry_series(entry)
            if series:
                pools[tree[series]].append(book_id)
                break

    # Only accept series with more than two books.
    return {series: book_ids
            for series, book_ids in pools.items()
            if len(book_ids) > 1}


def main():
    tree = form_gallery_groups()
    for entry in tqdm(filter_db_entries()):
        tree.add_or_create(entry, similarity=0.9)
    for entry in tqdm(filter_ds_entries()):
        tree.add_or_create(entry, similarity=0.9)
    for entry in tqdm(all_md_chapters()):
        tree.add_or_create(entry, similarity=0.9)
    for entry in tqdm(OrgEntry.select()):
        tree.add_or_create(entry, similarity=0.9)
    for entry in tqdm(CTHEntry.select()):
        tree.add_or_create(entry, similarity=0.9)
    for entry in tqdm(mb_entries()):
        tree.add_or_create(entry, similarity=0.9)
    for entry in tqdm(tora_entries()):
        tree.add_or_create(entry, similarity=0.9)
    lists = tree.all_entry_lists()

    # Construct database.
    tables = [
        IndexEntry,
        IndexBook,
        IndexCharacter,
        IndexBookCharacter,
        IndexTag,
        IndexBookTag,
        IndexBookDescription,
        IndexSeries,
        IndexThumbnail,
    ]

    db.connect()
    character_index = CharacterIndex()
    series_pools = coalesce_book_series(lists)
    batch_size = 10000

    with db.atomic():
        db.drop_tables(tables)
        db.create_tables(tables)

        thumbnails = [IndexThumbnail(
            id=entry_key(entry_list_canonical(item)),
            data=entry_thumbnails(entry_list_canonical(item))[0],
        ) for item in tqdm(lists)]
        IndexThumbnail.bulk_create(thumbnails, batch_size)

        series, book_series = [], {}
        for index, (model, book_ids) in enumerate(series_pools.items()):
            model = IndexSeries(id=index, title=model.title)
            series.append(model)
            for book in book_ids:
                book_series[book] = model
        IndexSeries.bulk_create(series, batch_size)

        books = [IndexBook(
            id=index,
            title=entry_book_title(entry_list_canonical(item)),
            series=book_series.get(index, None),
            thumbnail=thumbnail,
        ) for (index, item), thumbnail in zip(enumerate(tqdm(lists)), thumbnails)]
        IndexBook.bulk_create(books, batch_size)

        IndexBookDescription.bulk_create([
            IndexBookDescription(book=book, name=name, details=details)
            for item, book in zip(tqdm(lists), books)
            for name, details in entry_list_descriptions(item).items()
        ], batch_size)

        all_tags, book_tags = set(), []
        for item, book in zip(tqdm(lists), books):
            tags = entry_list_tags(item)
            all_tags.update(set(tags))
            book_tags.extend((IndexBookTag(book=book, tag=tag) for tag in tags))
        IndexTag.bulk_create([IndexTag(name=name) for name in all_tags], batch_size)
        IndexBookTag.bulk_create(book_tags, batch_size)

        all_characters, book_characters = set(), []
        for item, book in zip(tqdm(lists), books):
            characters = entry_list_characters(character_index, item)
            all_characters.update(set(characters))
            book_characters.extend((
                IndexBookCharacter(book=book, character=character)
                for character in characters
            ))
        all_character_models = [IndexCharacter(name=name) for name in all_characters]
        IndexCharacter.bulk_create(all_character_models, batch_size)
        IndexBookCharacter.bulk_create(book_characters, batch_size)

        IndexEntry.bulk_create([
            IndexEntry(
                id=entry_key(entry),
                book=book,
                title=entry_title(entry),
                url=entry_url(entry),
                date=entry_date(entry),
                language=entry_language(entry),
                page_count=entry_page_count(entry),
            )
            for item, book in zip(tqdm(lists), books)
            for entry in item.entries
        ], batch_size)


if __name__ == '__main__':
    main()
