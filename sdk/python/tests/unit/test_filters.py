"""``F`` builds the wire tree; ``FilterSchema.validate`` runs the Space's checks client-side."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from syfthub import Condition, F, FieldFilterSpec, FilterError, FilterSchema, Group

SCHEMA = FilterSchema(
    fields={
        "author": FieldFilterSpec(type="string", ops=("eq", "ne", "in", "nin")),
        "year": FieldFilterSpec(type="number", ops=("eq", "ne", "gt", "gte", "lt", "lte", "in")),
        "published": FieldFilterSpec(type="datetime", ops=("gt", "gte", "lt", "lte")),
        "draft": FieldFilterSpec(type="boolean", ops=("eq", "ne")),
        "tags": FieldFilterSpec(type="string[]", ops=("contains_any", "contains_all")),
        "scores": FieldFilterSpec(type="number[]", ops=("contains_any",)),
    },
    logic=("and", "or"),
    max_depth=3,
    max_conditions=4,
    max_list_values=2,
)


# ── builder ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("condition", "op", "value"),
    [
        (F("a") == 1, "eq", 1),
        (F("a") != 1, "ne", 1),
        (F("a") > 1, "gt", 1),
        (F("a") >= 1, "gte", 1),
        (F("a") < 1, "lt", 1),
        (F("a") <= 1, "lte", 1),
        (F("a").in_(["x", "y"]), "in", ["x", "y"]),
        (F("a").not_in(("x",)), "nin", ["x"]),
        (F("a").eq(1), "eq", 1),
        (F("a").ne(1), "ne", 1),
        (F("a").gt(1), "gt", 1),
        (F("a").gte(1), "gte", 1),
        (F("a").lt(1), "lt", 1),
        (F("a").lte(1), "lte", 1),
        (F("a").nin(["x"]), "nin", ["x"]),
        (F("a").contains_any({"x"}), "contains_any", ["x"]),
        (F("a").contains_all(["x", "y"]), "contains_all", ["x", "y"]),
        (F("a").op("gte", "2026-01-01"), "gte", "2026-01-01"),
    ],
)
def test_every_operator_builds_one_condition(condition: Condition, op: str, value: object) -> None:
    assert condition.to_wire() == {"type": "condition", "field": "a", "op": op, "value": value}


def test_in_range_is_a_closed_range_on_the_wire() -> None:
    assert F("n").in_range(1, 5).to_wire() == {
        "type": "group",
        "op": "and",
        "operands": [
            {"type": "condition", "field": "n", "op": "gte", "value": 1},
            {"type": "condition", "field": "n", "op": "lte", "value": 5},
        ],
    }


def test_and_or_make_groups_and_same_op_groups_flatten() -> None:
    a, b, c = F("a") == 1, F("b") == 2, F("c") == 3
    flat = a & b & c
    assert isinstance(flat, Group) and flat.op == "and" and len(flat.operands) == 3
    nested = a & (b | c)
    assert nested.to_wire() == {
        "type": "group",
        "op": "and",
        "operands": [
            a.to_wire(),
            {"type": "group", "op": "or", "operands": [b.to_wire(), c.to_wire()]},
        ],
    }
    assert F.all(a, b) == a & b and F.any(a, b) == a | b
    assert (a | b) | c == F.any(a, b, c)
    with pytest.raises(TypeError):
        a & "b"  # type: ignore[operator]


def test_datetimes_go_out_as_iso_with_a_zone_and_naive_means_utc() -> None:
    naive = F("published") >= datetime(2026, 1, 2, 3, 4, 5)
    assert naive.value == "2026-01-02T03:04:05+00:00"
    plus_two = datetime(2026, 1, 2, tzinfo=timezone(timedelta(hours=2)))
    assert (F("published") < plus_two).value == "2026-01-02T00:00:00+02:00"
    many = F("published").in_([datetime(2026, 1, 1, tzinfo=UTC)])
    assert many.value == ["2026-01-01T00:00:00+00:00"]


def test_filters_are_values_that_round_trip_through_dicts() -> None:
    f = (F("a") == 1) & F("tags").contains_any(["x"])
    assert Group.from_dict(f.to_dict()) == f and hash(f) == hash(Group.from_dict(f.to_dict()))
    assert Condition.from_dict((F("a") == 1).to_dict()) == (F("a") == 1)


# ── validation: the five server checks, in the server's words ─────────────


def test_a_good_filter_comes_back_unchanged() -> None:
    f = (F("author") == "peter") & (F("published") >= "2026-01-01") & F("draft").op("eq", "no")
    assert SCHEMA.validate(f) is f
    assert SCHEMA.validate(F("tags").contains_any(["a", "b"])) is not None
    assert SCHEMA.validate(F("year").in_(["1", 2])) is not None  # numbers as strings parse


@pytest.mark.parametrize(
    ("filter", "field", "reason"),
    [
        (F("status") == "x", "status", "not a filterable field"),
        (
            F("published").op("contains_any", ["x"]),
            "published",
            "operator 'contains_any' is not allowed for a datetime field; "
            "allowed: ['gt', 'gte', 'lt', 'lte']",
        ),
        (F("author").op("in", "x"), "author", "operator 'in' takes a list of values"),
        (F("author").op("eq", ["x"]), "author", "operator 'eq' takes a single value"),
        (F("author").in_(["a", "b", "c"]), "author", "at most 2 values in a list"),
        (F("published") >= "yesterday", "published", "cannot parse 'yesterday' as datetime"),
        (F("year") > "many", "year", "cannot parse 'many' as number"),
        (F("draft") == "maybe", "draft", "cannot parse 'maybe' as boolean"),
        (F("scores").contains_any(["x"]), "scores", "cannot parse 'x' as number"),
        (F("year") == True, "year", "cannot parse True as number"),  # noqa: E712
        (F("year") == None, "year", "cannot parse None as number"),  # noqa: E711
        (
            Group(op="not", operands=(F("year") == 1,)),
            "<group>",
            "operator 'not' is not allowed in a query",
        ),
    ],
)
def test_the_first_problem_is_raised_with_its_field_and_reason(
    filter: Condition | Group, field: str, reason: str
) -> None:
    with pytest.raises(FilterError) as info:
        SCHEMA.validate(filter)
    assert info.value.field == field and info.value.reason == reason
    assert str(info.value) == f"{field}: {reason}"
    assert isinstance(info.value, ValueError)


def test_size_caps_are_checked_before_anything_else() -> None:
    leaf = F("nope") == 1  # would fail the field check, but the caps come first
    deep = leaf
    for _ in range(4):
        deep = Group(op="and", operands=(deep,))
    with pytest.raises(FilterError, match="deeper than 3 groups"):
        SCHEMA.validate(deep)
    with pytest.raises(FilterError, match="more than 4 conditions"):
        SCHEMA.validate(F.all(*[leaf] * 5))
    assert SCHEMA.validate(F.all(*[F("year") == 1] * 4)) is not None


def test_schema_defaults_and_unknown_keys() -> None:
    schema = FilterSchema.from_dict(
        {"fields": {"a": {"type": "string", "ops": ["eq"], "x": 1}}, "y": 2}
    )
    assert schema.fields["a"].ops == ("eq",) and schema.max_depth == 5
    assert schema.max_conditions == 50 and schema.max_list_values == 100
    assert schema.logic == ("and", "or")
    assert FilterSchema().validate  # an empty schema refuses every field
    with pytest.raises(FilterError, match="not a filterable field"):
        FilterSchema().validate(F("a") == 1)


# ── guards against the usual slips ────────────────────────────────────────


@pytest.mark.parametrize("method", ["in_", "nin", "not_in", "contains_any", "contains_all"])
def test_list_operators_refuse_a_bare_string(method: str) -> None:
    with pytest.raises(TypeError, match="wrap it in a list"):
        getattr(F("author"), method)("abc")
    assert getattr(F("author"), method)(("a", "b")).value == ["a", "b"]


def test_a_condition_has_no_truth_value() -> None:
    with pytest.raises(TypeError, match="no truth value"):
        bool(F("author") == "x")
    with pytest.raises(TypeError, match="no truth value"):
        if (F("a") == 1) & (F("b") == 2):
            pass


def test_not_is_refused_with_a_hint() -> None:
    with pytest.raises(TypeError, match="accepts no ``not``"):
        ~(F("author") == "x")
    with pytest.raises(TypeError, match="accepts no ``not``"):
        ~F("author")


def test_missing_parentheses_name_the_cause() -> None:
    with pytest.raises(TypeError, match="parentheses"):
        F("a") == 1 & F("b") == 2  # type: ignore[operator]  # noqa: B015
    with pytest.raises(TypeError, match="is a field, not a filter"):
        (F("a") == 1) & F("b")  # type: ignore[operator]  # noqa: B015
    with pytest.raises(TypeError, match="is a field, not a filter"):
        F("a") | (F("b") == 2)  # type: ignore[operator]  # noqa: B015
    with pytest.raises(TypeError, match="parentheses"):
        1 & (F("b") == 2)  # type: ignore[operator]  # noqa: B015
