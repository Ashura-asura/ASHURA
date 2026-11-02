"""Working memory: bounded, RAM-only, auto-expiring (spec 5.1.A)."""
from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any, Callable


class WorkingMemory:
    def __init__(self, slots: int = 8, ttl_s: float = 600.0, clock: Callable[[], float] = time.monotonic):
        self.slots, self.ttl_s, self._clock = slots, ttl_s, clock
        self._items: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    def _expire(self) -> None:
        now = self._clock()
        for k in [k for k, (t, _) in self._items.items() if now - t > self.ttl_s]:
            del self._items[k]

    def put(self, key: str, value: Any) -> None:
        self._expire()
        self._items.pop(key, None)
        self._items[key] = (self._clock(), value)
        while len(self._items) > self.slots:       # evict least recently used
            self._items.popitem(last=False)

    def get(self, key: str, default: Any = None) -> Any:
        self._expire()
        if key not in self._items:
            return default
        t, v = self._items.pop(key)
        self._items[key] = (self._clock(), v)      # touch
        return v

    def items(self) -> dict[str, Any]:
        self._expire()
        return {k: v for k, (_, v) in self._items.items()}

    def clear(self) -> None:
        self._items.clear()

    def __len__(self) -> int:
        self._expire()
        return len(self._items)
