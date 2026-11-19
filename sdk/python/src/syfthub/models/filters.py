"""Query filters: the ``F`` builder, the wire tree, and the schema a source publishes.

A filter is a tree of conditions and groups, the same shape the Space accepts in a query's
``filters``. ``F`` builds it; ``FilterSchema.validate`` runs the Space's own checks before the
request is sent, so a filter that passes here is not refused there.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import Field

from ..errors import FilterError
from .base import Frozen

LIST_OPS: frozenset[str] = frozenset({"in", "nin", "contains_any", "contains_all"})
SCALAR_TYPES = (str, int, float, bool)


def _wire_value(value: Any) -> Any:
    """Datetimes go out as ISO 8601 with a zone, naive ones as UTC; lists are lists."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.isoformat()
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_wire_value(v) for v in value]
    return value


class _Node(Frozen):
    def __and__(self, other: Condition | Group) -> Group:
        return _join("and", self, other)

    def __or__(self, other: Condition | Group) -> Group:
        return _join("or", self, other)

    def to_wire(self) -> dict[str, Any]:
        """The ``{type, ...}`` tree a query sends as ``filters``."""
        return self.to_dict()


class Condition(_Node):
    """``field op value``. Build one with ``F``."""

    type: Literal["condition"] = "condition"
    field: str
    op: str
    value: Any


class Group(_Node):
    """Conditions or groups joined by ``and`` or ``or``. ``&`` and ``|`` build one."""

    type: Literal["group"] = "group"
    op: str
    operands: tuple[Annotated[Condition | Group, Field(discriminator="type")], ...]


Group.model_rebuild()

Filter = Annotated[Condition | Group, Field(discriminator="type")]


def _join(op: str, *nodes: Any) -> Group:
    """One group; a same-op operand is flattened so ``a & b & c`` is one ``and`` of three."""
    operands: list[Condition | Group] = []
    for node in nodes:
        if not isinstance(node, (Condition, Group)):
            raise TypeError(f"not a filter: {node!r}")
        if isinstance(node, Group) and node.op == op:
            operands.extend(node.operands)
        else:
            operands.append(node)
    return Group(op=op, operands=tuple(operands))


class F:
    """A field to filter on: ``F("published") >= "2026-01-01"``, ``F("tags").contains_any([...])``.

    Operators are methods or the comparison operators; ``op(name, value)`` takes the operator as
    a string, for conditions that arrive from a form or a model. Nothing is checked here: the
    filter is validated against a source's schema when it meets one.
    """

    def __init__(self, name: str) -> None:
        self.name = name

    def op(self, op: str, value: Any) -> Condition:
        return Condition(field=self.name, op=op, value=_wire_value(value))

    def __eq__(self, value: object) -> Condition:  # type: ignore[override]
        return self.op("eq", value)

    def __ne__(self, value: object) -> Condition:  # type: ignore[override]
        return self.op("ne", value)

    def __gt__(self, value: Any) -> Condition:
        return self.op("gt", value)

    def __ge__(self, value: Any) -> Condition:
        return self.op("gte", value)

    def __lt__(self, value: Any) -> Condition:
        return self.op("lt", value)

    def __le__(self, value: Any) -> Condition:
        return self.op("lte", value)

    def in_(self, values: Any) -> Condition:
        return self.op("in", list(values))

    def not_in(self, values: Any) -> Condition:
        return self.op("nin", list(values))

    def contains_any(self, values: Any) -> Condition:
        return self.op("contains_any", list(values))

    def contains_all(self, values: Any) -> Condition:
        return self.op("contains_all", list(values))

    __hash__ = None  # type: ignore[assignment]

    @staticmethod
    def all(*filters: Condition | Group) -> Group:
        return _join("and", *filters)

    @staticmethod
    def any(*filters: Condition | Group) -> Group:
        return _join("or", *filters)

    def __repr__(self) -> str:
        return f"F({self.name!r})"


def depth(node: Condition | Group) -> int:
    """Groups on the longest path: a bare condition is 0, a flat group 1."""
    if isinstance(node, Condition):
        return 0
    return 1 + max(depth(o) for o in node.operands)


def condition_count(node: Condition | Group) -> int:
    if isinstance(node, Condition):
        return 1
    return sum(condition_count(o) for o in node.operands)


class FieldFilterSpec(Frozen):
    """What a query may do with one field: its published type and operators."""

    type: str
    ops: tuple[str, ...] = ()


class FilterSchema(Frozen):
    """``query_schema.filters`` as the Space published it: the filterable fields, the group
    logic and the size caps. ``validate`` runs the Space's checks client-side."""

    fields: dict[str, FieldFilterSpec] = Field(default_factory=dict)
    logic: tuple[str, ...] = ("and", "or")
    max_depth: int = 5
    max_conditions: int = 50
    max_list_values: int = 100

    def validate(self, filter: Condition | Group) -> Condition | Group:  # type: ignore[override]
        """The filter back, or ``FilterError(field, reason)`` for the first thing the Space
        would refuse: size caps, group logic, unknown field, operator, list shape, value."""
        if depth(filter) > self.max_depth:
            raise FilterError("<group>", f"filter nests deeper than {self.max_depth} groups")
        if condition_count(filter) > self.max_conditions:
            raise FilterError("<group>", f"filter has more than {self.max_conditions} conditions")
        self._check(filter)
        return filter

    def _check(self, node: Condition | Group) -> None:
        if isinstance(node, Group):
            if node.op not in self.logic:
                raise FilterError("<group>", f"operator '{node.op}' is not allowed in a query")
            for operand in node.operands:
                self._check(operand)
            return
        spec = self.fields.get(node.field)
        if spec is None:
            raise FilterError(node.field, "not a filterable field")
        if node.op not in spec.ops:
            raise FilterError(
                node.field,
                f"operator '{node.op}' is not allowed for a {spec.type} field; "
                f"allowed: {list(spec.ops)}",
            )
        takes_list = node.op in LIST_OPS
        if takes_list != isinstance(node.value, list):
            raise FilterError(
                node.field,
                f"operator '{node.op}' takes "
                + ("a list of values" if takes_list else "a single value"),
            )
        if takes_list and len(node.value) > self.max_list_values:
            raise FilterError(node.field, f"at most {self.max_list_values} values in a list")
        values = node.value if takes_list else [node.value]
        for value in values:
            problem = _coercion_problem(value, spec.type)
            if problem:
                raise FilterError(node.field, problem)


def _coercion_problem(value: Any, type: str) -> str | None:
    """Why the Space could not read ``value`` as a ``type``; None when it can."""
    element = type.removesuffix("[]")
    if isinstance(value, bool):
        ok = element in ("boolean", "string")
    elif isinstance(value, (int, float)):
        ok = element in ("number", "string")
    elif isinstance(value, str):
        ok = element == "string" or _parses(value, element)
    else:
        ok = False
    return None if ok else f"cannot parse {value!r} as {element}"


def _parses(text: str, element: str) -> bool:
    text = text.strip()
    try:
        if element == "number":
            float(text)
        elif element == "boolean":
            return text.lower() in ("true", "1", "yes", "false", "0", "no")
        elif element == "datetime":
            datetime.fromisoformat(text)
        else:
            return False
    except ValueError:
        return False
    return True


class SourceSelection(Frozen):
    """A source named in a plan with the filter it is queried with. ``Source.where`` builds
    one; a bare path is a selection with no filter."""

    path: str
    filters: Filter | None = None


__all__ = [
    "LIST_OPS",
    "Condition",
    "F",
    "FieldFilterSpec",
    "Filter",
    "FilterSchema",
    "Group",
    "SourceSelection",
    "condition_count",
    "depth",
]
