# cython: language_level = 3

from libcpp.utility cimport pair
from libcpp.vector cimport vector
from libcpp.algorithm cimport sort
from libcpp.bit cimport popcount

ctypedef unsigned long long u64

# Using a vectorized linear search is significantly faster
# than specialized metric data structures like the BKTree.
cdef class HammingHashList:
    h8s: vector[u64]

    def add(self, h8: u64):
        self.h8s.push_back(h8)

    def find_closest(self, h8: u64, n: u64):
        cdef vector[u64] distances = vector[u64](self.h8s.size())
        for i in range(self.h8s.size()):
            # Calculates the hamming distance.
            # This must be inlined to enable vectorization.
            distances[i] = popcount(self.h8s[i] ^ h8)

        cdef vector[pair[u64, u64]] candidates
        for i in range(self.h8s.size()):
            if distances[i] <= n:
                candidates.push_back(pair[u64, u64](distances[i], self.h8s[i]))

        if not candidates.empty():
            sort(candidates.begin(), candidates.end())
            return candidates[0].second
