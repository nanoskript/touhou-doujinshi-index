# cython: language_level = 3

from cython.operator cimport dereference, preincrement

from libcpp.utility cimport pair
from libcpp.unordered_map cimport unordered_map
from libcpp.queue cimport queue
from libcpp.vector cimport vector
from libcpp.algorithm cimport sort
from libcpp.bit cimport popcount

ctypedef unsigned long long u64

cdef hamming_distance(a: u64, b: u64):
    return popcount(a ^ b)

# Defining a `struct` causes a compilation stack overflow.
cdef cppclass BKNode:
    u64 value
    unordered_map[u64, BKNode] children

    BKNode():
        pass

# Based on:
# https://github.com/benhoyt/pybktree/blob/master/pybktree.py
cdef class BKTree:
    is_empty: bool
    root: BKNode

    def __cinit__(self):
        self.is_empty = True

    def add(self, h8: u64):
        cdef BKNode * node = &self.root
        if self.is_empty:
            self.is_empty = False
            self.root.value = h8
            return

        cdef u64 distance
        while True:
            distance = hamming_distance(h8, node.value)
            if node.children.count(distance):
                node = &node.children[distance]
            else:
                node.children[distance].value = h8
                break

    def find_closest(self, h8: u64, n: u64):
        if self.is_empty:
            return None

        cdef vector[pair[u64, u64]] found
        cdef queue[BKNode *] candidates
        candidates.push(&self.root)

        cdef u64 distance, d
        while not candidates.empty():
            node = candidates.front()
            candidates.pop()

            distance = hamming_distance(node.value, h8)
            if distance <= n:
                found.push_back(pair[u64, u64](distance, node.value))

            it = node.children.begin()
            while it != node.children.end():
                d = dereference(it).first
                c = &dereference(it).second
                preincrement(it)

                if distance <= d + n and d <= n + distance:
                    candidates.push(c)

        sort(found.begin(), found.end())
        return None if found.empty() else found[0].second
