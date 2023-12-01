from scripts.source_db import significant_characters


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

    def canonicalize(self, name: str) -> str:
        name = tag_to_name(name)
        if name in self.unique:
            return name

        swapped = " ".join(reversed(name.split()))
        if swapped in self.unique:
            return swapped

        for token in name.split():
            if token.title() in self.mapping:
                return self.mapping[token.title()]

        return name
