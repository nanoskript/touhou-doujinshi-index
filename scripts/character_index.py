from collections import Counter

from scripts.source_db import DBEntry


class CharacterIndex:
    unique: set[str]
    mapping: dict[str, str]

    def __init__(self):
        def tag_to_name(tag: str):
            return (tag.replace("_", " ").title()
                    .replace("Pc-98", "PC-98")
                    .replace("(Touhou)", "")
                    .strip())

        characters = Counter()
        for entry in DBEntry.select(DBEntry.posts):
            names = []
            for post in entry.posts:
                names += post["tag_string_character"].split()
            for name in set(names):
                characters[name] += 1

        # Take only significant characters.
        self.unique = set([
            tag_to_name(name)
            for name, count in characters.items()
            if count >= 20
        ])

        # Tokenize by most common first.
        self.mapping = {}
        for name, _count in characters.most_common():
            readable_name = tag_to_name(name)
            for token in readable_name.split():
                if token not in self.mapping:
                    self.mapping[token] = readable_name

    def canonicalize(self, name: str) -> str:
        if name in self.unique:
            return name

        swapped = " ".join(reversed(name.split()))
        if swapped in self.unique:
            return swapped

        for token in name.split():
            if token.title() in self.mapping:
                return self.mapping[token.title()]

        return name
