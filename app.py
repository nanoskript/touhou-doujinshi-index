import dataclasses
import datetime
import io
import json
import math

import peewee
import timeago
from flask import Flask, render_template, send_file, request
from peewee import fn

from scripts.entry import entry_key_readable_source, ALL_SOURCE_TYPES
from scripts.index import *

app = Flask(__name__)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 60 * 60


@dataclasses.dataclass()
class BookData:
    title: str
    thumbnail_id: str
    tags: list[str]
    characters: list[str]
    descriptions: list[IndexBookDescription]
    entries: list[IndexEntry]


@dataclasses.dataclass()
class EntriesFilter:
    language: str | None = None
    exclude_sources: list[str] = dataclasses.field(default_factory=list)


def filter_entries(query, f: EntriesFilter):
    if f.language:
        query = query.where(IndexEntry.language == f.language)
    for source in f.exclude_sources:
        query = query.where(~(IndexEntry.id.startswith(source)))
    return query


def build_book(book: int, f: EntriesFilter) -> BookData:
    book = IndexBook.get_by_id(book)
    tags = [str(row.tag) for row in
            (IndexBookTag.select()
             .where(IndexBookTag.book == book)
             .order_by(IndexBookTag.tag)
             .distinct())]

    characters = [str(row.character) for row in
                  (IndexBookCharacter.select()
                   .where(IndexBookCharacter.book == book)
                   .order_by(IndexBookCharacter.character)
                   .distinct())]

    descriptions = list(IndexBookDescription.select()
                        .where(IndexBookDescription.book == book)
                        .order_by(IndexBookDescription.name))

    query = IndexEntry.select().where(IndexEntry.book == book)
    query = filter_entries(query, f)
    entries = list(query.order_by(
        IndexEntry.language,
        IndexEntry.date.desc(),
        IndexEntry.title.desc(),
    ))

    return BookData(
        title=book.title,
        thumbnail_id=book.thumbnail_id,
        tags=tags,
        characters=characters,
        descriptions=descriptions,
        entries=entries,
    )


@app.template_filter("age")
def template_age(date: datetime.datetime) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    return timeago.format(date, now=now)


@app.template_filter("entry_readable_source")
def template_entry_readable_source(entry: IndexEntry) -> str:
    return entry_key_readable_source(entry.id)


@app.template_global()
def url_with(route: str, **kwargs):
    args = request.args.to_dict(flat=False)
    return app.url_for(route, **{**args, **kwargs})


@app.template_global()
def pluralize(number: int, string: str, plural: str = None) -> str:
    if number == 1:
        return f"{number} {string}"
    if not plural:
        plural = f"{string}s"
    return f"{number} {plural}"


def build_full_query(
    title: str | None,
    must_include_tags: list[str],
    must_include_characters: list[str],
    exclude_on_sources: list[str],
    exclude_on_language: str | None,
    include_metadata_only: bool,
    f: EntriesFilter,
):
    query = IndexBook.select(IndexBook.id).join(IndexEntry)
    query = filter_entries(query, f)

    if title:
        query = query.where(
            IndexBook.title.contains(title) |
            IndexEntry.title.contains(title)
        )

    for tag in must_include_tags:
        books_with_tag = (IndexBook.select()
                          .join(IndexBookTag)
                          .where(IndexBookTag.tag.contains(tag)))
        query = query.where(IndexBook.id << books_with_tag)

    for character in must_include_characters:
        books_with_character = (IndexBook.select()
                                .join(IndexBookCharacter)
                                .where(IndexBookCharacter.character.contains(character)))
        query = query.where(IndexBook.id << books_with_character)

    for source in exclude_on_sources:
        books_with_source = (IndexBook.select()
                             .join(IndexEntry)
                             .where(IndexEntry.id.startswith(source)))
        if f.language:
            books_with_source = (books_with_source
                                 .where(IndexEntry.language == f.language))
        query = query.where(~(IndexBook.id << books_with_source))

    if exclude_on_language:
        books_with_language = (IndexBook.select()
                               .join(IndexEntry)
                               .where(IndexEntry.language == exclude_on_language))
        query = query.where(~(IndexBook.id << books_with_language))

    if not include_metadata_only:
        not_metadata_only = (IndexBook.select()
                             .join(IndexEntry)
                             .where(~IndexEntry.language.is_null()))
        query = query.where(IndexBook.id << not_metadata_only)

    # Sort by earliest entry present in book.
    return (query
            .group_by(IndexEntry.book)
            .order_by(fn.Min(IndexEntry.date).desc(), IndexBook.title.desc()))


def build_language_groups() -> list[tuple[str, list[str]]]:
    common = ["Japanese", "English", "Chinese", "Spanish"]
    special = ["Speechless", "Text Cleaned"]

    other = [row.language for row in
             IndexEntry.select(IndexEntry.language)
             .where(~(IndexEntry.language << (common + special)))
             .distinct().order_by(IndexEntry.language)]

    return [
        ("Common", common),
        ("Special", special),
        ("Other", other),
    ]


@app.route("/")
def route_index():
    f = EntriesFilter(
        language=request.args.get("language", None),
        exclude_sources=request.args.getlist("exclude_source"),
    )

    query = build_full_query(
        title=request.args.get("title", None),
        must_include_tags=request.args.get("include_tags", "").split(),
        must_include_characters=request.args.get("include_characters", "").split(),
        exclude_on_sources=request.args.getlist("exclude_on_source"),
        exclude_on_language=request.args.get("exclude_on_language", None),
        include_metadata_only=("include_metadata_only" in request.args),
        f=f,
    )

    # Calculate statistics.
    limit = 20
    total_books = query.count()
    total_pages = math.ceil(total_books / limit)

    # Retrieve dataset.
    books = []
    page = int(request.args.get("page", 1))
    for row in query.offset((page - 1) * limit).limit(limit):
        books.append(build_book(row, f))

    # Number of advanced options selected.
    selected = set()
    for key, value in request.args.items():
        if value and key not in ["title", "page"]:
            selected.add(key)

    # Render.
    return render_template(
        "index.html",
        books=books,
        total_books=total_books,
        total_pages=total_pages,
        page=page,
        selected_count=len(selected),
        languages=build_language_groups(),
        sources=ALL_SOURCE_TYPES,
    )


@app.route("/book/<key>")
def route_book(key: str):
    def build_description(b: BookData) -> str:
        lines = [f"{pluralize(len(b.entries), 'entry', 'entries')}."]
        if b.tags:
            lines.append(f"Tags: {', '.join(b.tags)}.")
        if b.characters:
            lines.append(f"Characters: {', '.join(b.characters)}.")
        return " ".join(lines)

    book = IndexEntry.get_by_id(key).book
    return render_template(
        "book.html",
        book=build_book(book, EntriesFilter()),
        build_description=build_description,
    )


@app.route("/thumbnail/<key>.jpg")
def route_thumbnail(key: str):
    data = IndexThumbnail.get_by_id(key).data
    return send_file(io.BytesIO(data), mimetype="octet-stream")


@app.route("/about")
def route_about():
    with open("data/statistics.json", "r") as f:
        statistics = json.load(f)

    return render_template(
        "about.html",
        statistics=statistics,
    )


@app.route("/recipes")
def route_recipes():
    return render_template("recipes.html")


@app.errorhandler(peewee.OperationalError)
def handle_database_error(_e):
    return render_template(
        "error.html",
        message="The database is being updated. Please check back later.",
    ), 503


if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True, threaded=True)
