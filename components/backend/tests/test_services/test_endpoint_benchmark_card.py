"""Benchmark cards: what the Hub agrees to publish about an endpoint.

Health says an endpoint responds. A card says whether what comes back is any
good — measured by a benchmark the owner runs against his own endpoint and
forwarded here by his Space.

What is covered here is what would be expensive to get wrong: a card read as
something it is not, prose from a private corpus becoming a public document,
and an owner unable to take back what is published in his name.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from syfthub.schemas.endpoint import (
    CARD_VERSION,
    KIND_ANSWERING,
    KIND_RETRIEVAL,
    EndpointQualityItem,
    EndpointQualityRequest,
)
from syfthub.schemas.user import User
from syfthub.services.endpoint_service import EndpointService


@pytest.fixture
def owner():
    """The user who owns the endpoints being reported on."""
    return User(
        id=1,
        username="owner",
        email="owner@example.com",
        full_name="Endpoint Owner",
        role="user",
        is_active=True,
        created_at=datetime.fromisoformat("2026-01-01T00:00:00"),
        updated_at=datetime.fromisoformat("2026-01-01T00:00:00"),
        key_created_at=datetime.fromisoformat("2026-01-01T00:00:00"),
        age=30,
        public_key="public_key",
        password_hash="hashed_pass",
    )


@pytest.fixture
def service():
    """A service whose repository and session are stubs."""
    session = MagicMock()
    svc = EndpointService(session)
    svc.endpoint_repository = MagicMock()
    return svc


def card(**overrides):
    """A card as a benchmark actually sends one."""
    body = {
        "slug": "knowledge-base",
        "version": CARD_VERSION,
        "kind": KIND_ANSWERING,
        "arm": "open_book",
        "checked_at": "2026-09-14T03:00:00+00:00",
        "score": 0.71,
        "fabrication_rate": 0.04,
        "reliable": True,
        "samples": 515,
        "answerable": {
            "samples": 412,
            "correct": 0.71,
            "abstain": 0.12,
            "hallucinate": 0.17,
            "lmi": 0.19,
        },
        "unanswerable": {"samples": 103, "fabricated": 0.04},
        "discrimination": 0.63,
        "retrieval": 0.82,
        "models": [
            {
                "model": "anthropic/claude-sonnet-4",
                "samples": 412,
                "accuracy": 0.78,
                "fabrication": 0.02,
                "lmi": 0.1,
                "context_gain": 0.05,
            }
        ],
        "skills": [{"generator": "mcq", "samples": 80, "accuracy": 0.9}],
        "trust": {
            "judges": 3,
            "agreement": 0.86,
            "consistency": 0.91,
            "even_coverage": True,
            "failed": 2,
            "pending": 0,
            "flags": [],
        },
        "dataset": {
            "mode": "rolling",
            "window_days": 7,
            "cohort": "20260914-0300",
            "questions": 515,
        },
        "instrument": {
            "profile": "default",
            "judge": "gemma3-4b-gpu",
            "judges": 3,
            "subjects": 9,
        },
    }
    body.update(overrides)
    return body


class TestWhatTheHubAgreesToRead:
    """A card of a shape this Hub cannot read is refused, never guessed at."""

    def test_a_real_card_is_accepted(self):
        item = EndpointQualityItem.model_validate(card())

        assert item.kind == KIND_ANSWERING
        assert item.unanswerable is not None
        # The control half survives the trip: it is the half a consumer cannot
        # check for himself, and the reason it is measured at all.
        assert item.unanswerable.fabricated == 0.04
        assert item.trust is not None
        assert item.trust.judges == 3

    def test_an_unknown_version_is_refused(self):
        """A figure understood wrongly is worse than a figure not shown.

        The first publishes a number that means something else, and nobody
        looking at it can tell.
        """
        with pytest.raises(ValidationError, match="unsupported card version"):
            EndpointQualityItem.model_validate(card(version=1))

    def test_an_unknown_kind_is_refused(self):
        """The kind is what makes the headline share readable.

        "Finds 82%" and "correct 82%" are claims about different products; a
        badge that cannot tell them apart will state one as the other.
        """
        with pytest.raises(ValidationError, match="unknown kind"):
            EndpointQualityItem.model_validate(card(kind="great"))

    @pytest.mark.parametrize(
        "mutation",
        [
            {
                "skills": [
                    {
                        "generator": "a sentence about port 5442",
                        "samples": 1,
                        "accuracy": 1.0,
                    }
                ]
            },
            {"models": [{"model": "the model replied", "samples": 1, "accuracy": 1.0}]},
            {"arm": "open book"},
            {
                "instrument": {
                    "profile": "two words",
                    "judge": "j",
                    "judges": 1,
                    "subjects": 1,
                }
            },
        ],
        ids=["skill", "model", "arm", "profile"],
    )
    def test_prose_never_becomes_a_public_document(self, mutation):
        """The last place a benchmark's privacy promise can be checked.

        Its questions are built from a corpus nobody else may read, and only
        shares, counts and identifiers are supposed to leave it. Checked by
        form rather than by a list of forbidden words — every string here is
        one token, and a fragment of a private corpus always has spaces.
        """
        with pytest.raises(ValidationError, match="identifier, not text"):
            EndpointQualityItem.model_validate(card(**mutation))

    def test_a_share_outside_zero_to_one_is_refused(self):
        with pytest.raises(ValidationError):
            EndpointQualityItem.model_validate(card(score=1.4))

    def test_a_request_must_carry_at_least_one_card(self):
        with pytest.raises(ValidationError):
            EndpointQualityRequest.model_validate({"endpoints": []})


class TestStoringACard:
    """Two shapes, one write."""

    def test_the_scalar_figures_and_the_whole_card_are_stored_together(
        self, service, owner
    ):
        """The listing paints from columns; the detail page reads the document.

        Which is which is decided here, so a card gaining a section does not
        need a migration.
        """
        endpoint = MagicMock(id=7, slug="knowledge-base")
        service.endpoint_repository.get_endpoints_by_slugs_for_health.return_value = [
            endpoint
        ]
        service.endpoint_repository.bulk_update_quality.return_value = (1, [])

        got = service.report_endpoint_quality(
            [EndpointQualityItem.model_validate(card())], owner
        )

        assert got.updated == 1
        assert got.ignored == 0
        written = service.endpoint_repository.bulk_update_quality.call_args[0][0][0]
        assert written["endpoint_id"] == 7
        assert written["kind"] == KIND_ANSWERING
        assert written["score"] == 0.71
        assert written["fabrication_rate"] == 0.04
        assert written["reliable"] is True
        assert written["report"]["trust"]["agreement"] == 0.86

    def test_the_slug_identifies_the_row_and_is_not_kept_inside_the_card(
        self, service, owner
    ):
        """Storing it twice would let the two disagree."""
        service.endpoint_repository.get_endpoints_by_slugs_for_health.return_value = [
            MagicMock(id=7, slug="knowledge-base")
        ]
        service.endpoint_repository.bulk_update_quality.return_value = (1, [])

        service.report_endpoint_quality(
            [EndpointQualityItem.model_validate(card())], owner
        )

        written = service.endpoint_repository.bulk_update_quality.call_args[0][0][0]
        assert "slug" not in written["report"]

    def test_a_searching_endpoint_stores_a_retrieval_card(self, service, owner):
        """An endpoint that only searches is judged by what it finds.

        It never writes an answer, so it has no accuracy — and while the
        measured arm was a benchmark-wide setting, such a node published
        nothing at all, however good its search was.
        """
        service.endpoint_repository.get_endpoints_by_slugs_for_health.return_value = [
            MagicMock(id=7, slug="knowledge-base")
        ]
        service.endpoint_repository.bulk_update_quality.return_value = (1, [])

        service.report_endpoint_quality(
            [
                EndpointQualityItem.model_validate(
                    card(kind=KIND_RETRIEVAL, arm="model_with_context", score=0.82)
                )
            ],
            owner,
        )

        written = service.endpoint_repository.bulk_update_quality.call_args[0][0][0]
        assert written["kind"] == KIND_RETRIEVAL
        assert written["score"] == 0.82

    def test_a_slug_the_caller_does_not_own_is_ignored_not_fatal(self, service, owner):
        """One unknown slug must not throw away the cards that were good."""
        service.endpoint_repository.get_endpoints_by_slugs_for_health.return_value = []

        got = service.report_endpoint_quality(
            [EndpointQualityItem.model_validate(card(slug="not-mine"))], owner
        )

        assert got.updated == 0
        assert got.ignored == 1
        service.endpoint_repository.bulk_update_quality.assert_not_called()

    def test_a_failed_write_is_neither_updated_nor_ignored(self, service, owner):
        """A row a caller owns but that fails to store is not an unknown slug."""
        service.endpoint_repository.get_endpoints_by_slugs_for_health.return_value = [
            MagicMock(id=7, slug="knowledge-base")
        ]
        service.endpoint_repository.bulk_update_quality.return_value = (0, [7])

        got = service.report_endpoint_quality(
            [EndpointQualityItem.model_validate(card())], owner
        )

        assert got.updated == 0
        assert got.ignored == 0


class TestWhatReachesTheReader:
    """The card has to arrive where it is rendered."""

    def test_the_public_view_carries_the_whole_card(self):
        """The detail page is built from the public shape, not a private one.

        There is no public route returning one endpoint in any other form, so a
        document left off this schema could never be shown to the people it is
        written for — the badge would paint and the panel would render nothing,
        silently.
        """
        from syfthub.schemas.endpoint import EndpointPublicResponse

        fields = EndpointPublicResponse.model_fields
        assert "quality_report" in fields
        for badge_field in (
            "quality_kind",
            "quality_score",
            "quality_fabrication_rate",
            "quality_reliable",
            "quality_checked_at",
        ):
            assert badge_field in fields


class TestTheShapeOfAnAbsentCard:
    """A withdrawn card leaves nothing behind, because the row is the card."""

    def test_a_card_is_a_row_of_its_own_and_not_columns_on_the_endpoint(self):
        """Absence of a measurement has to be absence of a row.

        Held as columns on ``endpoints`` every one of these had to be nullable,
        and the schema then had to accept a half-card: a score with no kind to
        read it by, a run with no date. Keyed by the endpoint in a table of its
        own, a malformed card has nowhere to land, and "never benchmarked" is
        one unambiguous fact rather than seven NULLs that might disagree.
        """
        from syfthub.models.endpoint import EndpointBenchmarkCardModel, EndpointModel

        table = EndpointBenchmarkCardModel.__table__
        assert list(table.primary_key.columns.keys()) == ["endpoint_id"]
        for required in ("kind", "samples", "reliable", "checked_at", "report"):
            assert table.c[required].nullable is False, required

        # The endpoints table must not keep a second copy of any of this; two
        # places to read a card from is one place to read a stale one.
        for gone in ("quality_kind", "quality_score", "quality_report"):
            assert gone not in EndpointModel.__table__.c, gone

    def test_a_card_may_have_a_hole_in_it(self):
        """A retrieval card has no fabrication rate, and that is not an error.

        These two are nullable alone among the figures: an endpoint that only
        searches never writes an answer to fabricate in, and a run cut short may
        vouch for nothing at all. That is a card with a gap, not a missing card,
        and the reader can tell the difference only because the row exists.
        """
        from syfthub.models.endpoint import EndpointBenchmarkCardModel

        table = EndpointBenchmarkCardModel.__table__
        assert table.c.score.nullable is True
        assert table.c.fabrication_rate.nullable is True

    def test_a_deleted_endpoint_takes_its_card_with_it(self):
        """A card outliving its endpoint could only be shown against a wrong one."""
        from syfthub.models.endpoint import EndpointBenchmarkCardModel

        column = EndpointBenchmarkCardModel.__table__.c.endpoint_id
        foreign_key = next(iter(column.foreign_keys))
        assert foreign_key.column.table.name == "endpoints"
        assert foreign_key.ondelete == "CASCADE"

    def test_the_endpoint_still_reads_as_flat_quality_fields(self):
        """Where the card is stored is not the API's business.

        Consumers, the frontend and the SDK have always read ``quality_*`` off
        the endpoint. The accessors keep that promise across the move, and
        answer None — not raise — for an endpoint that has no card.
        """
        from syfthub.models.endpoint import EndpointBenchmarkCardModel, EndpointModel

        unmeasured = EndpointModel()
        unmeasured.benchmark_card = None
        assert unmeasured.quality_kind is None
        assert unmeasured.quality_score is None
        assert unmeasured.quality_report is None

        measured = EndpointModel()
        measured.benchmark_card = EndpointBenchmarkCardModel(
            kind=KIND_ANSWERING,
            score=0.71,
            fabrication_rate=0.04,
            samples=120,
            reliable=True,
            checked_at=datetime(2026, 9, 14, tzinfo=timezone.utc),
            report={"trust": {"agreement": 0.86}},
        )
        assert measured.quality_kind == KIND_ANSWERING
        assert measured.quality_score == 0.71
        assert measured.quality_fabrication_rate == 0.04
        assert measured.quality_samples == 120
        assert measured.quality_reliable is True
        assert measured.quality_report["trust"]["agreement"] == 0.86


class TestRetraction:
    """Publishing may be delegated; taking it back may not."""

    def test_an_owner_can_withdraw_a_published_card(self, service, owner):
        """A card carries no TTL, so it stands until someone takes it down."""
        service.endpoint_repository.get_by_owner_and_slug_any_state.return_value = (
            MagicMock(
                id=7,
                quality_checked_at=datetime(2026, 9, 14, tzinfo=timezone.utc),
                quality_score=0.71,
            )
        )
        service.endpoint_repository.clear_quality.return_value = True

        got = service.clear_endpoint_quality("knowledge-base", owner)

        assert got.cleared is True
        service.endpoint_repository.clear_quality.assert_called_once_with(endpoint_id=7)

    def test_retracting_what_was_never_published_is_not_an_error(self, service, owner):
        """Nothing to take down means the goal is already met."""
        service.endpoint_repository.get_by_owner_and_slug_any_state.return_value = (
            MagicMock(id=7, quality_checked_at=None, quality_score=None)
        )

        got = service.clear_endpoint_quality("knowledge-base", owner)

        assert got.cleared is False
        service.endpoint_repository.clear_quality.assert_not_called()

    def test_a_stranger_cannot_retract_what_he_does_not_own(self, service, owner):
        """A broken or hostile benchmark must not erase cards it never reported."""
        service.endpoint_repository.get_by_owner_and_slug_any_state.return_value = None

        with pytest.raises(HTTPException) as caught:
            service.clear_endpoint_quality("someone-elses", owner)

        assert caught.value.status_code == 404
