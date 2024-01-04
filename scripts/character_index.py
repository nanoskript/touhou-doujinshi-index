from typing import Optional

from scripts.source_db import significant_characters, DBWikiPage
from scripts.source_ds import ds_all_pairings


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
                    if alias not in self.mapping:
                        self.mapping[alias] = readable_name
                    if alias.replace("・", "") not in self.mapping:
                        self.mapping[alias.replace("・", "")] = readable_name

        # Manually added mappings.
        self.mapping["アリス"] = "Alice Margatroid"
        self.mapping["リリ"] = "Lily White"
        self.mapping["メディスン"] = "Medicine Melancholy"

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


def canonicalize_pairing_characters(index: CharacterIndex, pairing: frozenset[str]) -> frozenset[str]:
    return frozenset([index.canonicalize(character) for character in pairing])


class PairingIndex:
    characters: CharacterIndex
    mapping: dict[frozenset[str], frozenset[str]] = {}

    def __init__(self, characters: CharacterIndex):
        self.characters = characters
        for pairing in ds_all_pairings():
            self.mapping[canonicalize_pairing_characters(characters, pairing)] = pairing

        # Manually added entries.
        self.mapping[frozenset(["マリアリ"])] = frozenset(["Alice", "Marisa"])
        self.mapping[frozenset(["秘封倶楽部"])] = frozenset(["Maribel", "Renko"])

    # Canonicalize to Dynasty pairing names.
    def canonicalize(self, pairing: frozenset[str]) -> frozenset[str]:
        pairing = canonicalize_pairing_characters(self.characters, pairing)
        if pairing in self.mapping:
            return self.mapping[pairing]
        return pairing
