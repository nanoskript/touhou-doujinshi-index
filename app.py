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
from scripts.index import IndexEntry, IndexBook, IndexBookCharacter, IndexThumbnail

app = Flask(__name__)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 60 * 60


@dataclasses.dataclass()
class BookData:
    title: str
    thumbnail_id: str
    characters: list[str]
    entries: list[IndexEntry]


def build_book(book: int, language: str = None) -> BookData:
    book = IndexBook.get_by_id(book)
    characters = [str(row.character) for row in
                  (IndexBookCharacter.select()
                   .where(IndexBookCharacter.book == book)
                   .order_by(IndexBookCharacter.character)
                   .distinct())]

    query = IndexEntry.select().where(IndexEntry.book == book)
    if language:
        query = query.where(IndexEntry.language == language)

    entries = list(query.order_by(
        IndexEntry.language,
        IndexEntry.date.desc(),
        IndexEntry.title.desc(),
    ))

    return BookData(
        title=book.title,
        thumbnail_id=book.thumbnail_id,
        characters=characters,
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
    return app.url_for(route, **{**request.args, **kwargs})


@app.template_global()
def pluralize(number: int, string: str) -> str:
    if number == 1:
        return f"{number} {string}"
    return f"{number} {string}s"


def build_full_query(
    title: str | None,
    language: str | None,
    must_include_characters: list[str],
    exclude_on_source: str | None,
):
    query = IndexBook.select(IndexBook.id).join(IndexEntry)
    if title:
        query = query.where(
            IndexBook.title.contains(title) |
            IndexEntry.title.contains(title)
        )
    if language:
        query = query.where(IndexEntry.language == language)

    for character in must_include_characters:
        books_with_character = (IndexBook.select()
                                .join(IndexBookCharacter)
                                .where(IndexBookCharacter.character.contains(character)))
        query = query.where(IndexBook.id << books_with_character)

    if exclude_on_source:
        books_with_source = (IndexBook.select()
                             .join(IndexEntry)
                             .where(IndexEntry.id.startswith(exclude_on_source)))
        query = query.where(~(IndexBook.id << books_with_source))

    # Sort by earliest entry present in book.
    return (query
            .group_by(IndexEntry.book)
            .order_by(fn.Min(IndexEntry.date).desc(), IndexBook.title.desc()))


@app.route("/")
def route_index():
    page = int(request.args.get("page", 1))
    language = request.args.get("language", None)

    # Build query.
    query = build_full_query(
        title=request.args.get("title", None),
        language=language,
        must_include_characters=request.args.get("include_characters", "").split(),
        exclude_on_source=request.args.get("exclude_on_source", None),
    )

    # Calculate statistics.
    limit = 20
    total_books = query.count()
    total_pages = math.ceil(total_books / limit)

    # Retrieve dataset.
    books = []
    for row in query.offset((page - 1) * limit).limit(limit):
        books.append(build_book(row, language=language))

    # Find all languages available.
    languages = [row.language for row in
                 IndexEntry.select(IndexEntry.language)
                 .distinct()
                 .order_by(IndexEntry.language)]

    return render_template(
        "index.html",
        books=books,
        total_books=total_books,
        total_pages=total_pages,
        page=page,
        languages=languages,
        sources=ALL_SOURCE_TYPES,
    )


@app.route("/book/<key>")
def route_book(key: str):
    def build_description(b: BookData) -> str:
        lines = [f"{pluralize(len(b.entries), 'entry')}."]
        if b.characters:
            lines.append(f"Characters: {', '.join(b.characters)}.")
        return " ".join(lines)

    book = IndexEntry.get_by_id(key).book
    return render_template(
        "book.html",
        book=build_book(book),
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


@app.errorhandler(peewee.OperationalError)
def handle_database_error(_e):
    return render_template(
        "error.html",
        message="The database is being updated. Please check back later.",
    ), 503


if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True, threaded=True)
