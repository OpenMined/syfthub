"""Pagination utilities for SyftHub SDK."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

# Type alias for fetch functions
FetchFn = Callable[[int, int], list[dict[str, object]]]


class PageIterator(Generic[T]):
    """Lazy pagination iterator that fetches pages on demand.

    Example usage:
        # Iterate through all items
        for endpoint in client.hub.browse():
            print(endpoint.name)

        # Get just the first page
        first_page = client.hub.browse().first_page()

        # Get all items as a list
        all_items = client.hub.browse().all()

        # Get first 50 items
        items = client.hub.browse().take(50)
    """

    def __init__(
        self,
        fetch_fn: FetchFn,
        model_class: type[T],
        page_size: int = 20,
    ) -> None:
        """Initialize the page iterator.

        Args:
            fetch_fn: Function that takes (skip, limit) and returns list of dicts
            model_class: Pydantic model class to parse items into
            page_size: Number of items per page (default 20)
        """
        self._fetch_fn = fetch_fn
        self._model_class = model_class
        self._page_size = page_size
        self._reset()

    def _reset(self) -> None:
        """Reset iterator state for fresh iteration."""
        self._buffer: list[T] = []
        self._current_page = 0
        self._exhausted = False
        self._started = False

    def _fetch_page(self, page: int) -> list[T]:
        """Fetch a single page and convert to models."""
        skip = page * self._page_size
        raw_items = self._fetch_fn(skip, self._page_size)

        # Convert dicts to model instances
        items = [self._model_class.model_validate(item) for item in raw_items]

        # Check if this is the last page
        if len(items) < self._page_size:
            self._exhausted = True

        return items

    def __iter__(self) -> Iterator[T]:
        """Return iterator (resets state for fresh iteration)."""
        self._reset()
        return self

    def __next__(self) -> T:
        """Return next item, fetching pages as needed."""
        # If we have items in buffer, return next one
        if self._buffer:
            return self._buffer.pop(0)

        # If exhausted, stop iteration
        if self._exhausted:
            raise StopIteration

        # Fetch next page
        self._started = True
        page_items = self._fetch_page(self._current_page)
        self._current_page += 1

        if not page_items:
            self._exhausted = True
            raise StopIteration

        # Buffer all but first item
        self._buffer = page_items[1:]
        return page_items[0]

    def first_page(self) -> list[T]:
        """Get just the first page of results.

        Returns:
            List of items from the first page
        """
        return self._fetch_page(0)

    def all(self) -> list[T]:
        """Fetch all pages and return as a single list.

        Warning: This loads all items into memory.

        Returns:
            List of all items across all pages
        """
        return list(self)

    def take(self, n: int) -> list[T]:
        """Get the first n items (may span multiple pages).

        Args:
            n: Maximum number of items to return

        Returns:
            List of up to n items
        """
        result: list[T] = []
        for item in self:
            result.append(item)
            if len(result) >= n:
                break
        return result
