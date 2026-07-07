"""Tests for DataSourceClient response parsing.

Covers hybrid (model_data_source) endpoints that return an AI-generated
`summary` in addition to (or instead of) `references.documents`. The
aggregator must surface the generated summary as a Document so hybrid
sources don't report "0 documents retrieved".
"""

from aggregator.clients.data_source import DataSourceClient


def test_parse_extracts_reference_documents() -> None:
    client = DataSourceClient()
    data = {
        "summary": None,
        "references": {
            "documents": [
                {
                    "document_id": "d1",
                    "content": "doc one",
                    "metadata": {"k": "v"},
                    "similarity_score": 0.9,
                }
            ]
        },
    }

    docs = client._parse_syftai_response(data)

    assert len(docs) == 1
    assert docs[0].content == "doc one"
    assert docs[0].score == 0.9


def test_parse_surfaces_generated_summary_as_document() -> None:
    """Hybrid source returns only a generated summary, no reference docs."""
    client = DataSourceClient()
    data = {
        "summary": {
            "model": "gpt-x",
            "message": {"role": "assistant", "content": "The generated answer."},
        },
        "references": None,
    }

    docs = client._parse_syftai_response(data)

    assert len(docs) == 1
    assert docs[0].content == "The generated answer."
    assert docs[0].metadata.get("source_type") == "generated"
    assert docs[0].metadata.get("model") == "gpt-x"


def test_parse_includes_both_documents_and_summary() -> None:
    """Hybrid source returns both real docs and a generated summary."""
    client = DataSourceClient()
    data = {
        "summary": {
            "model": "gpt-x",
            "message": {"role": "assistant", "content": "The generated answer."},
        },
        "references": {
            "documents": [
                {"content": "doc one", "similarity_score": 0.8, "metadata": {}}
            ]
        },
    }

    docs = client._parse_syftai_response(data)

    contents = [d.content for d in docs]
    assert "doc one" in contents
    assert "The generated answer." in contents
    assert len(docs) == 2


def test_parse_empty_when_no_summary_and_no_references() -> None:
    client = DataSourceClient()
    docs = client._parse_syftai_response({"summary": None, "references": None})
    assert docs == []


def test_parse_ignores_empty_summary_content() -> None:
    client = DataSourceClient()
    data = {"summary": {"message": {"role": "assistant", "content": ""}}, "references": None}
    assert client._parse_syftai_response(data) == []
