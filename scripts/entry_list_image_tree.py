import dataclasses

import pybktree

from .build_image_hashes import entry_h8s
from .entry import Entry
from .index import EntryList
from .utility import deduplicate_by_identity


@dataclasses.dataclass()
class BookGroupImageNode:
    h8: int
    group: EntryList | None


def node_distance(a: BookGroupImageNode, b: BookGroupImageNode) -> int:
    return (a.h8 ^ b.h8).bit_count()


class EntryListImageTree:
    tree: pybktree.BKTree
    orphans: list[Entry]

    def __init__(self, initial_groups=None):
        if initial_groups is None:
            initial_groups = []

        self.tree = pybktree.BKTree(node_distance)
        self.orphans = []

        for group in initial_groups:
            for entry in group.entries:
                for h8 in entry_h8s(entry):
                    self.tree.add(BookGroupImageNode(h8=h8, group=group))

    def add_or_create(self, entry: Entry, similarity: float):
        h8s = entry_h8s(entry)
        if not h8s:
            self.orphans.append(entry)
            return

        threshold = int((1.0 - similarity) * (8 * 8))
        for h8 in h8s:
            query_node = BookGroupImageNode(h8=h8, group=None)
            results = self.tree.find(query_node, threshold)

            if results:
                (_distance, node) = results[0]
                node.group.entries.append(entry)
                group = node.group
                break
        else:
            # No match found so create new group.
            group = EntryList(entries=[entry])

        for h8 in h8s:
            self.tree.add(BookGroupImageNode(h8=h8, group=group))

    def all_entry_lists(self) -> list[EntryList]:
        groups = []
        for orphan in self.orphans:
            groups.append(EntryList(entries=[orphan]))
        for node in self.tree:
            groups.append(node.group)
        return deduplicate_by_identity(groups)
