"""The examples in the public docstrings run."""

import doctest

import pytest

import syfthub.models.filters
import syfthub.models.results
import syfthub.models.sources


@pytest.mark.parametrize(
    "module", [syfthub.models.filters, syfthub.models.sources, syfthub.models.results]
)
def test_docstring_examples_run(module: object) -> None:
    result = doctest.testmod(module, optionflags=doctest.NORMALIZE_WHITESPACE)
    assert result.attempted > 0
    assert result.failed == 0
