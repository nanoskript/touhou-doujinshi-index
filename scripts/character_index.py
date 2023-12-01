from typing import Optional

from scripts.source_db import significant_characters, DBWikiPage


def tag_to_name(tag: str):
    return (tag.replace("_", " ").title()
            .replace("Pc-98", "PC-98")
            .replace("(Touhou)", "")
            .strip())


class CharacterIndex:
    unique: set[str]
    mapping: dict[str, str]

    def __init__(self):
        characters = significant_characters()
        self.unique = set(map(tag_to_name, characters.keys()))

        # Tokenize by most common first.
        self.mapping = {}
        for name, _count in characters.most_common():
            readable_name = tag_to_name(name)
            for token in readable_name.split():
                if token not in self.mapping:
                    self.mapping[token] = readable_name

            # Add character aliases.
            wiki_page = DBWikiPage.get_or_none(title=name)
            if wiki_page:
                other_names = wiki_page.data["other_names"]
                for alias in other_names:
                    self.mapping[alias] = readable_name

    def find_and_canonicalize(self, name: str) -> Optional[str]:
        if name in self.unique:
            return name

        swapped = " ".join(reversed(name.split()))
        if swapped in self.unique:
            return swapped

        for token in name.split():
            if token.title() in self.mapping:
                return self.mapping[token.title()]

    def canonicalize(self, name: str) -> str:
        name = tag_to_name(name)
        return self.find_and_canonicalize(name) or name
