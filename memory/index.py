"""Retrieval interface (spec 5.3). The rest of ASHURA never depends on a specific engine."""
from __future__ import annotations


class MemoryIndex:
    def add(self, memory_id: str, text: str) -> None:
        raise NotImplementedError

    def search(self, query: str, limit: int = 5) -> list[tuple[str, float]]:
        """Return [(memory_id, relevance)] best first. Relevance is higher = better."""
        raise NotImplementedError

    def delete(self, memory_id: str) -> None:
        raise NotImplementedError
