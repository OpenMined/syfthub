"""Fake backends. The only thing that gets swapped for the real SDK."""
from .hub import FakeHub
from .space import FakeSpace
from .aggregator import FakeAggregator

__all__ = ["FakeHub", "FakeSpace", "FakeAggregator"]
