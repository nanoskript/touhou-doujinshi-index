import dataclasses
import datetime
import io
import json
import math
from collections import defaultdict
from typing import Optional

import peewee
import timeago
from dateutil.relativedelta import relativedelta
from flask import Flask, render_template, send_file, request, url_for, make_response
from peewee import fn

from scripts.entry import entry_key_readable_source, ALL_SOURCE_TYPES
from scripts.index import *

app = Flask(__name__, static_folder="static", static_url_path="")
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 60 * 60

SITEMAP_URL_LIMIT = 5000


@dataclasses.dataclass()
class BookData:
    title: str
    series: Optional[str]
    thumbnail_id: str
    tags: list[str]
    characters: list[str]
    descriptions: list[IndexBookDescription]
    entries: list[IndexEntry]


@dataclasses.dataclass()
class EntriesFilter:
    language: str | None = None
    min_pages: int | None = None
    max_pages: int | None = None
    exclude_sources: list[str] = dataclasses.field(default_factory=list)


def filter_entries(query, f: EntriesFilter):
    if f.language:
        query = query.where(IndexEntry.language ** f.language)
    if f.min_pages:
        query = query.where(IndexEntry.page_count >= f.min_pages)
    if f.max_pages:
        query = query.where(IndexEntry.page_count <= f.max_pages)
    for source in f.exclude_sources:
        query = query.where(~(IndexEntry.id.startswith(source)))
    return query


def build_books(book_ids: list[int], f: EntriesFilter) -> dict[int, BookData]:
    models = (IndexBook.select()
              .where(IndexBook.id << book_ids)
              .order_by(IndexBook.id))

    tags = (IndexBookTag
            .select(IndexBookTag, IndexTag)
            .join(IndexTag)
            .order_by(IndexTag.name))

    characters = (IndexBookCharacter
                  .select(IndexBookCharacter, IndexCharacter)
                  .join(IndexCharacter)
                  .order_by(IndexCharacter.name))

    descriptions = (IndexBookDescription.select()
                    .order_by(IndexBookDescription.name))

    query = IndexEntry.select()
    query = filter_entries(query, f)
    entries = query.order_by(
        IndexEntry.language,
        IndexEntry.date.desc(),
        IndexEntry.title.desc(),
    )

    # Count number of books in a series.
    relevant_series = IndexBook.select(IndexBook.series).where(IndexBook.id << book_ids)
    series_book_counts: dict[str, int] = dict((IndexSeries.select(IndexSeries.id, fn.count())
                                               .join(IndexBook).where(IndexSeries.id << relevant_series)
                                               .group_by(IndexSeries).tuples()))

    books = {}
    for book in peewee.prefetch(models, tags, characters, descriptions, entries):
        # Only include series if there are separate books.
        series = book.series
        if series and series_book_counts[series.id] <= 1:
            series = None

        # Construct model.
        books[book.id] = BookData(
            title=book.title,
            series=(series and series.title),
            thumbnail_id=book.thumbnail_id,
            tags=[row.tag.name for row in book.indexbooktag_set],
            characters=[row.character.name for row in book.indexbookcharacter_set],
            descriptions=book.indexbookdescription_set,
            entries=book.indexentry_set,
        )
    return books


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
    title_tokens: list[str],
    must_include_tags: list[str],
    must_include_characters: list[str],
    exclude_on_sources: list[str],
    exclude_on_language: str | None,
    include_metadata_only: bool,
    f: EntriesFilter,
):
    query = IndexBook.select(IndexBook.id).join(IndexEntry)
    query = filter_entries(query, f)

    for token in title_tokens:
        books_by_series = (IndexBook.select()
                           .join(IndexSeries)
                           .where(IndexSeries.title.contains(token)))

        query = query.where(
            IndexBook.title.contains(token) |
            IndexEntry.title.contains(token) |
            (IndexBook.id << books_by_series)
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


# FIXME: Currently performs a full table scan.
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


@app.template_filter("encode_query_term")
def encode_query_term(term: str) -> str:
    return term.lower().replace(" ", "_")


def decode_query_term(query: str) -> str:
    return query.replace("_", " ")


def decode_query(query: str) -> dict[str, list[str]]:
    decoded = defaultdict(list)
    for token in query.lower().split():
        if ":" in token:
            [key, value] = token.split(":", maxsplit=1)
            decoded[key].append(decode_query_term(value))
        else:
            decoded["title"].append(token)
    return decoded


@app.route("/")
def route_index():
    # Only filter by first language term.
    query = decode_query(request.args.get("q", ""))
    language = query["language"][0] if "language" in query else None

    f = EntriesFilter(
        language=language,
        min_pages=request.args.get("min_pages", None),
        max_pages=request.args.get("max_pages", None),
        exclude_sources=request.args.getlist("exclude_source"),
    )

    query = build_full_query(
        title_tokens=query.get("title", []),
        must_include_tags=query.get("tag", []),
        must_include_characters=query.get("character", []),
        exclude_on_sources=request.args.getlist("exclude_on_source"),
        exclude_on_language=request.args.get("exclude_on_language", None),
        include_metadata_only=("include_metadata_only" in request.args),
        f=f,
    )

    # Perform count and selection in single query.
    limit = 20
    page = int(request.args.get("page", 1))
    total_column = fn.Count("*").over().alias("total")
    query = (IndexBook.select(total_column, peewee.SQL("*"))
             .from_(query).paginate(page, limit))

    total_books, book_ids = 0, []
    for result in query:
        total_books = result.total
        book_ids.append(result.id)

    total_pages = math.ceil(total_books / limit)
    book_data = build_books(book_ids, f)
    books = [book_data[book] for book in book_ids]

    # Number of advanced options selected.
    selected = set()
    for key, value in request.args.items():
        if value and key not in ["q", "page"]:
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


@app.get("/autocomplete")
def route_autocomplete():
    q = request.args.get("q", "")
    q = decode_query_term(q)

    languages = [row.language for row in
                 (IndexEntry.select(IndexEntry.language)
                  .where(IndexEntry.language.startswith(q))
                  .distinct().limit(10))]

    characters = [row.name for row in
                  (IndexCharacter.select()
                   .where(IndexCharacter.name.contains(q))
                   .order_by(fn.length(IndexCharacter.name))
                   .limit(10))]

    tags = [row.name for row in
            (IndexTag.select()
             .where(IndexTag.name.startswith(q))
             .order_by(fn.length(IndexTag.name))
             .limit(10))]

    return [*[("Language", term, f"language:{encode_query_term(term)}") for term in languages],
            *[("Character", term, f"character:{encode_query_term(term)}") for term in characters],
            *[("Tag", term, f"tag:{encode_query_term(term)}") for term in tags]][:10]


@app.route("/popular")
def route_popular():
    @dataclasses.dataclass()
    class TimeRange:
        name: str
        description: str
        start_date: datetime.datetime

    now = datetime.datetime.now(datetime.timezone.utc)
    time_ranges = [
        ("forever", TimeRange(name="All time", description="of all time",
                              start_date=datetime.datetime.fromtimestamp(0))),
        ("past-year", TimeRange(name="Past year", description="uploaded in the past year",
                                start_date=now - relativedelta(years=1))),
        ("past-month", TimeRange(name="Past month", description="uploaded in the past month",
                                 start_date=now - relativedelta(months=1))),
    ]

    time_range = dict(time_ranges)[request.args.get("range", "forever")]
    exclude_sources = [key for key in ALL_SOURCE_TYPES.keys() if key not in {"ds", "md"}]
    f = EntriesFilter(language="English", exclude_sources=exclude_sources)

    # Query total comments for each book.
    book_comments = fn.SUM(IndexEntry.comments).alias("book_comments")
    latest_release_date = fn.MAX(IndexEntry.date).alias("latest_release_date")
    books = (IndexBook.select(book_comments, IndexBook, latest_release_date)
             .join(IndexEntry).group_by(IndexBook)
             .order_by(fn.MAX(IndexEntry.date).desc()))
    books = filter_entries(books, f)

    # Query total comments in book or series.
    # FIXME: Uses `thumbnail_id` as a unique identifier.
    total_comments = fn.SUM(books.c.book_comments) + fn.COALESCE(IndexSeries.comments, 0)
    combined = (IndexBook.select(total_comments.alias("comments"), books.c.id, books.c.latest_release_date)
                .from_(books).join(IndexSeries, peewee.JOIN.LEFT_OUTER, on=(IndexSeries.id == books.c.series_id))
                .group_by(fn.COALESCE(IndexSeries.id, books.c.thumbnail_id)))

    # Order results by the most number of comments first.
    query = (IndexBook.select(combined.c.comments, combined.c.id).from_(combined)
             .where(combined.c.latest_release_date > time_range.start_date)
             .order_by(combined.c.comments.desc()))

    # Perform count and selection in single query.
    limit = 20
    page = int(request.args.get("page", 1))
    total_column = fn.Count("*").over().alias("total")
    query = (IndexBook.select(total_column, peewee.SQL("*"))
             .from_(query).paginate(page, limit))

    total_books, comments, book_ids = 0, [], []
    for result in query:
        total_books = result.total
        comments.append(result.comments or 0)
        book_ids.append(result.id)

    total_pages = math.ceil(total_books / limit)
    book_data = build_books(book_ids, f)
    books = [book_data[book] for book in book_ids]

    return render_template(
        "popular.html",
        books=list(zip(comments, books)),
        total_books=total_books,
        total_pages=total_pages,
        page=page,
        time_range=time_range,
        time_ranges=time_ranges,
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

    book_id = IndexEntry.get_by_id(key).book_id
    book = build_books([book_id], EntriesFilter())[book_id]
    return render_template(
        "book.html",
        book=book,
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


def as_xml(xml: str):
    response = make_response(xml)
    response.headers["Content-Type"] = "application/xml"
    return response


@app.route("/sitemap.xml")
def route_sitemap_index():
    book_page_count = math.ceil(IndexBook.select().count() / SITEMAP_URL_LIMIT)
    book_sitemaps = [url_for("route_sitemap_books", page=page)
                     for page in range(book_page_count)]

    return as_xml(render_template("sitemap_index.xml", paths=[
        url_for("route_sitemap_static"),
        *book_sitemaps,
    ]))


@app.route("/sitemap/static.xml")
def route_sitemap_static():
    return as_xml(render_template("sitemap.xml", paths=[
        url_for("route_index"),
        url_for("route_popular"),
        url_for("route_recipes"),
        url_for("route_about"),
    ]))


@app.route("/sitemap/books/<int:page>.xml")
def route_sitemap_books(page: int):
    paths = [url_for("route_book", key=row.id)
             for row in (IndexEntry.select(IndexEntry.id)
                         .group_by(IndexEntry.book)
                         .limit(SITEMAP_URL_LIMIT)
                         .offset(page * SITEMAP_URL_LIMIT))]
    return as_xml(render_template("sitemap.xml", paths=paths))


@app.errorhandler(peewee.OperationalError)
def handle_database_error(_e):
    return render_template(
        "error.html",
        message="The database is being updated. Please check back later.",
    ), 503


if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True, threaded=True)
