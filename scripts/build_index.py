import itertools

from tqdm import tqdm
from scipy.cluster.hierarchy import DisjointSet

from scripts.source_ds import filter_ds_entries
from scripts.source_mb import mb_entries
from scripts.source_tora import tora_entries
from .character_index import CharacterIndex, PairingIndex
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


def entry_list_characters(
    character_index: CharacterIndex,
    pairing_index: PairingIndex,
    entry_list: EntryList,
) -> list[str]:
    characters, plausible = [], []
    for entry in entry_list.entries:
        characters += entry_characters(entry)
        plausible += entry_characters_plausible(entry)
        for pairing in entry_pairings(entry):
            characters += list(pairing_index.canonicalize(pairing))

    characters = [character_index.canonicalize(name) for name in characters]
    plausible = [character_index.find_and_canonicalize(name) for name in plausible]
    characters += list(filter(None, plausible))
    return list(sorted(set(characters)))


def entry_list_pairing_tags(index: PairingIndex, entry_list: EntryList) -> list[str]:
    tags = []
    for entry in entry_list.entries:
        for pairing in entry_pairings(entry):
            pairing = index.canonicalize(pairing)
            tags.append(" x ".join(sorted(pairing)))
    return list(sorted(set(tags)))


def entry_list_tags(pairings: PairingIndex, entry_list: EntryList) -> list[str]:
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
        "Artbook": "Artbook",
    }

    tags = []
    for entry in entry_list.entries:
        for tag in entry_tags(entry):
            tags.append(synonyms.get(tag, tag))
        for tag in entry_tags_plausible(entry):
            if tag in synonyms:
                tags.append(synonyms[tag])

    tags += entry_list_pairing_tags(pairings, entry_list)
    return list(sorted(set(tags)))


def entry_list_descriptions(entry_list: EntryList):
    descriptions = {}
    for entry in entry_list.entries:
        descriptions.update(entry_descriptions(entry))
    return descriptions


def entry_list_artists(entry_list: EntryList) -> list[str]:
    artists = []
    for entry in entry_list.entries:
        for artist in entry_artists(entry):
            # TODO: Canonicalize artist names based on Danbooru database.
            uppercase = artist.upper()
            artist = uppercase if uppercase in ["ZUN"] else artist.title()
            artists.append(artist)
    return list(set(artists))


def entry_list_canonical(entry_list: EntryList) -> Optional[Entry]:
    return entry_list.entries[0]


# Assumes entry list indices will be identical to book IDs.
def coalesce_book_series(lists: list[EntryList]) -> list[tuple[EntrySeries, list[int]]]:
    book_series: dict[int, list[EntrySeries]] = defaultdict(list)
    for book_id, item in enumerate(lists):
        for entry in item.entries:
            series = entry_series(entry)
            if series:
                book_series[book_id].append(series)

    # Populate and combine overlapping series.
    series_by_key = {}
    tree = DisjointSet([])
    for series_list in book_series.values():
        last_series_key = None
        for series in series_list:
            tree.add(series.key)
            series_by_key[series.key] = series
            if last_series_key is not None:
                tree.merge(last_series_key, series.key)
            last_series_key = series.key

    # Generate mappings between series.
    roots: dict[str, tuple[EntrySeries, list[int]]] = {}
    roots_by_key: dict[str, str] = {}
    for subset in map(list, tree.subsets()):
        root, others = subset[0], subset[1:]
        root_series = series_by_key[root]

        for key in others:
            series = series_by_key[key]
            root_series.comments += series.comments
            roots_by_key[key] = root

        roots[root] = root_series, []
        roots_by_key[root] = root

    # Determine series for each book.
    for book_id, series_list in book_series.items():
        for series in series_list:
            series, book_ids = roots[roots_by_key[series.key]]
            book_ids.append(book_id)
            break
    return list(roots.values())


def main():
    # Form groups based on thumbnail similarity.
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

    # Add linked entries to each group.
    # This includes Pixiv sources.
    for entry_list in lists:
        for entry in entry_list.entries.copy():
            entry_list.entries += linked_entries(entry)

    # Construct database.
    tables = [
        IndexEntry,
        IndexBook,
        IndexBookTitle,
        IndexArtist,
        IndexBookArtist,
        IndexCharacter,
        IndexBookCharacter,
        IndexTag,
        IndexBookTag,
        IndexBookDescription,
        IndexSeries,
        IndexThumbnail,
        IndexLanguage,
    ]

    db.connect()
    character_index = CharacterIndex()
    pairing_index = PairingIndex(character_index)
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
        for index, (model, book_ids) in enumerate(series_pools):
            model = IndexSeries(
                id=index,
                title=model.title,
                comments=model.comments,
            )

            series.append(model)
            for book in book_ids:
                book_series[book] = model
        IndexSeries.bulk_create(series, batch_size)

        books, book_titles = [], []
        for (index, item), thumbnail in zip(enumerate(tqdm(lists)), thumbnails):
            main_title = entry_book_titles(entry_list_canonical(item))[0]
            all_titles = itertools.chain(*[entry_book_titles(entry) for entry in item.entries])
            all_titles = list(set(all_titles))

            book = IndexBook(
                id=index,
                main_title=main_title,
                series=book_series.get(index, None),
                thumbnail=thumbnail,
            )

            books.append(book)
            book_titles += [IndexBookTitle(book=book, title=title)
                            for title in all_titles]
        IndexBook.bulk_create(books, batch_size)
        IndexBookTitle.bulk_create(book_titles, batch_size)

        IndexBookDescription.bulk_create([
            IndexBookDescription(book=book, name=name, details=details)
            for item, book in zip(tqdm(lists), books)
            for name, details in entry_list_descriptions(item).items()
        ], batch_size)

        all_tags, book_tags = set(), []
        for item, book in zip(tqdm(lists), books):
            tags = entry_list_tags(pairing_index, item)
            all_tags.update(set(tags))
            book_tags.extend((IndexBookTag(book=book, tag=tag) for tag in tags))
        IndexTag.bulk_create([IndexTag(name=name) for name in all_tags], batch_size)
        IndexBookTag.bulk_create(book_tags, batch_size)

        all_characters, book_characters = set(), []
        for item, book in zip(tqdm(lists), books):
            characters = entry_list_characters(character_index, pairing_index, item)
            all_characters.update(set(characters))
            book_characters.extend((
                IndexBookCharacter(book=book, character=character)
                for character in characters
            ))
        all_character_models = [IndexCharacter(name=name) for name in all_characters]
        IndexCharacter.bulk_create(all_character_models, batch_size)
        IndexBookCharacter.bulk_create(book_characters, batch_size)

        all_artists, book_artists = set(), []
        for item, book in zip(tqdm(lists), books):
            artists = entry_list_artists(item)
            all_artists.update(set(artists))
            book_artists.extend((IndexBookArtist(book=book, artist=artist) for artist in artists))
        IndexArtist.bulk_create([IndexArtist(name=name) for name in all_artists], batch_size)
        IndexBookArtist.bulk_create(book_artists, batch_size)

        # Entries may sometimes belong to more than one book.
        all_languages, entries = set(), {}
        for item, book in zip(tqdm(lists), books):
            for entry in item.entries:
                language = entry_language(entry)
                if language:
                    all_languages.add(language)

                key = entry_key(entry)
                entries[key] = IndexEntry(
                    id=key,
                    book=book,
                    title=entry_title(entry),
                    url=entry_url(entry),
                    date=entry_date_sanitized(entry),
                    language=entry_language(entry),
                    page_count=entry_page_count_sanitized(entry),
                    comments=entry_comments(entry),
                )

        all_language_models = [IndexLanguage(name=name) for name in all_languages]
        IndexLanguage.bulk_create(all_language_models)
        IndexEntry.bulk_create(entries.values(), batch_size)


if __name__ == '__main__':
    main()
