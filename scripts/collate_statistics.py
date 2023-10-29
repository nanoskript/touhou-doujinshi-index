import json

from peewee import fn
import pandas as pd
import plotly.express as px

from scripts.entry import entry_key_readable_source
from scripts.index import IndexEntry, IndexBookCharacter, IndexBook

LAYOUT = {
    "xaxis_title": None,
    "yaxis_title": None,
    "margin": dict(l=20, r=20, t=20, b=20),
}


def graph_languages_over_time():
    languages = [
        "Japanese",
        "English",
        "Chinese",
        "Spanish",
    ]

    query = (IndexEntry
             .select(fn.Min(IndexEntry.date), IndexEntry.language)
             .where(IndexEntry.language << languages)
             .group_by(IndexEntry.book, IndexEntry.language))

    df = (pd.DataFrame(query.dicts())
          .groupby("language")
          .resample("1M", on="date").count()
          .rename(columns={"language": "count"})
          .groupby("language").cumsum()
          .reset_index())

    legend = (df.groupby("language")
              .max().sort_values(by="count", ascending=False)
              .reset_index()["language"].tolist())

    fig = px.line(
        df, x="date", y="count", color="language",
        labels={"date": "Date", "count": "Count", "language": "Language"},
        category_orders={"language": legend},
    )

    fig.update_layout(LAYOUT)
    return fig.to_json()


def graph_websites_over_time():
    query = [
        {"site": entry_key_readable_source(entry.id), "date": entry.date}
        for entry in IndexEntry.select(IndexEntry.id, IndexEntry.date)
    ]

    df = (pd.DataFrame(query)
          .groupby("site")
          .resample("1M", on="date").count()
          .rename(columns={"site": "count"})
          .groupby("site").cumsum()
          .reset_index())

    legend = (df.groupby("site")
              .max().sort_values(by="count", ascending=False)
              .reset_index()["site"].tolist())

    fig = px.line(
        df, x="date", y="count", color="site",
        labels={"date": "Date", "count": "Count", "site": "Website"},
        category_orders={"site": legend},
    )

    fig.update_layout(LAYOUT)
    return fig.to_json()


def graph_page_counts():
    query = (IndexEntry
             .select(fn.Max(IndexEntry.page_count))
             .group_by(IndexEntry.book))

    df = pd.DataFrame(query.dicts())
    df = df[df["page_count"] <= 100]

    fig = px.histogram(
        df, x="page_count", nbins=20,
        labels={"page_count": "Number of pages"}
    )

    fig.update_layout(LAYOUT)
    return fig.to_json()


def graph_characters_over_time():
    query = (IndexBookCharacter
             .select(fn.Min(IndexEntry.date), IndexBookCharacter.character)
             .join(IndexBook).join(IndexEntry)
             .group_by(IndexEntry.book, IndexBookCharacter.character))

    df = (pd.DataFrame(query.dicts())
          .groupby("character")
          .resample("1M", on="date").count()
          .rename(columns={"character": "count"})
          .groupby("character").cumsum()
          .reset_index())

    significant = set()
    for name in list(df.character.unique()):
        if max(df[df.character == name]["count"]) > 500:
            significant.add(name)
    df = df[df.character.isin(significant)]

    legend = (df.groupby("character")
              .max().sort_values(by="count", ascending=False)
              .reset_index()["character"].tolist())

    fig = px.line(
        df, x="date", y="count", color="character",
        labels={"date": "Date", "count": "Count", "character": "Character"},
        category_orders={"character": legend},
    )

    fig.update_layout(LAYOUT)
    return fig.to_json()


def main():
    data = {
        "languages": graph_languages_over_time(),
        "websites": graph_websites_over_time(),
        "page-counts": graph_page_counts(),
        "characters": graph_characters_over_time(),
    }

    with open("data/statistics.json", "w") as f:
        json.dump(data, f)


if __name__ == '__main__':
    main()
