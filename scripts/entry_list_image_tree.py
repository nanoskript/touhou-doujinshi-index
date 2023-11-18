import pyximport

pyximport.install()

from .bktree import BKTree
from .build_image_hashes import entry_h8s
from .entry import Entry, EntryList
from .utility import deduplicate_by_identity


class EntryListImageTree:
    tree: BKTree
    groups: dict[int, EntryList]
    orphans: list[Entry]

    def _try_add_entry(self, h8s: list[int], group: EntryList):
        for h8 in h8s:
            if h8 not in self.groups:
                self.groups[h8] = group
                self.tree.add(h8)

    def __init__(self, initial_groups=None):
        if initial_groups is None:
            initial_groups = []

        self.tree = BKTree()
        self.groups = {}
        self.orphans = []

        for group in initial_groups:
            for entry in group.entries:
                self._try_add_entry(entry_h8s(entry), group)

    def add_or_create(self, entry: Entry, similarity: float):
        h8s = entry_h8s(entry)
        if not h8s:
            self.orphans.append(entry)
            return

        threshold = int((1.0 - similarity) * (8 * 8))
        for h8 in h8s:
            closest = self.tree.find_closest(h8, threshold)
            if closest is not None:
                group = self.groups[closest]
                group.entries.append(entry)
                break
        else:
            # No match found so create new group.
            group = EntryList(entries=[entry])
        self._try_add_entry(h8s, group)

    def all_entry_lists(self) -> list[EntryList]:
        groups = list(self.groups.values())
        for orphan in self.orphans:
            groups.append(EntryList(entries=[orphan]))
        return deduplicate_by_identity(groups)
