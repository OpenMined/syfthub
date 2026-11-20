"""Query filters: the ``F`` builder, the wire tree, and the schema a source publishes.

A filter narrows a search by document metadata: only this author, only after this date, only
chunks tagged with one of these. It is a tree of conditions and groups, the same shape the Space
accepts in a query's ``filters``. ``F`` builds it; ``FilterSchema.validate`` runs the Space's own
checks before the request is sent, so a filter that passes here is not refused there.

The usual path::

    from syfthub import F

    source = await hub.sources.get("nasa/news")
    source.filter_schema.fields              # what you may filter on, with types and operators
    recent = F("published") >= "2026-10-01"
    moon = F("tags").contains_any(["moon", "artemis"])
    plan = hub.search("Artemis launches", [source.where(recent & moon)])
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import Field

from ..errors import FilterError
from .base import Frozen

LIST_OPS: frozenset[str] = frozenset({"in", "nin", "contains_any", "contains_all"})


def _values(values: Any) -> list[Any]:
    """``values`` as a list for a list operator; a bare string is one value, not many."""
    if isinstance(values, (str, bytes)):
        raise TypeError(f"expected an iterable of values, got {values!r}; wrap it in a list")
    return list(values)


def _wire_value(value: Any) -> Any:
    """Datetimes go out as ISO 8601 with a zone, naive ones as UTC; lists are lists."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.isoformat()
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_wire_value(v) for v in value]
    return value


_PRECEDENCE_HINT = (
    "``&`` and ``|`` bind tighter than a comparison: wrap each in parentheses, "
    "(F('a') == 1) & (F('b') == 2)"
)
_NO_NOT_HINT = "the Space accepts no ``not``: use ``ne``, ``nin`` or ``contains_any`` instead"


def _operand(node: Any) -> Condition | Group:
    """``node`` as a filter, or a TypeError that names the usual cause."""
    if isinstance(node, (Condition, Group)):
        return node
    if isinstance(node, F):
        raise TypeError(f"{node!r} is a field, not a filter; {_PRECEDENCE_HINT}")
    raise TypeError(f"not a filter: {node!r}; {_PRECEDENCE_HINT}")


class _Node(Frozen):
    def __and__(self, other: Condition | Group) -> Group:
        return _join("and", self, _operand(other))

    def __or__(self, other: Condition | Group) -> Group:
        return _join("or", self, _operand(other))

    def __rand__(self, other: Any) -> Group:
        return _join("and", _operand(other), self)

    def __ror__(self, other: Any) -> Group:
        return _join("or", _operand(other), self)

    def __invert__(self) -> Group:
        # TypeError is what Python raises for an unsupported ``~``; ours says what to use.
        raise TypeError(_NO_NOT_HINT)

    def __bool__(self) -> bool:
        # ``if F("a") == "x":`` is always a bug: ``==`` built a Condition, not a bool.
        raise TypeError(
            f"a {type(self).__name__} has no truth value; compare with ``is None`` "
            "or validate it against a schema"
        )

    def to_wire(self) -> dict[str, Any]:
        """The ``{type, ...}`` tree a query sends as ``filters``.

        Example:
            >>> (F("published") >= "2026-01-01").to_wire()
            {'type': 'condition', 'field': 'published', 'op': 'gte', 'value': '2026-01-01'}
        """
        return self.to_dict()


class Condition(_Node):
    """One test on one field: ``field op value``.

    Build it with ``F``; ``&`` and ``|`` combine it with others into a ``Group``.

    ``op`` is a wire name (``eq``, ``gte``, ``contains_any``, ...), ``value`` a JSON scalar or,
    for the list operators, a list. A ``Condition`` is immutable and hashable, so it can be a
    dict key or sit in a set, and it round-trips through ``to_dict`` / ``from_dict``.

    Example:
        >>> c = F("author") == "Joe Rogan"
        >>> c.field, c.op, c.value
        ('author', 'eq', 'Joe Rogan')
        >>> Condition.from_dict(c.to_dict()) == c
        True
    """

    type: Literal["condition"] = "condition"
    field: str
    op: str
    value: Any


class Group(_Node):
    """Conditions or groups joined by ``and`` or ``or``.

    ``&`` and ``|`` build one, and a same-op operand is flattened, so ``a & b & c`` is one
    ``and`` of three, not two nested.

    Example:
        >>> g = (F("a") == 1) & (F("b") == 2) & (F("c") == 3)
        >>> g.op, len(g.operands)
        ('and', 3)
        >>> mixed = (F("a") == 1) | ((F("b") == 2) & (F("c") == 3))
        >>> [o.type for o in mixed.operands]
        ['condition', 'group']
    """

    type: Literal["group"] = "group"
    op: str
    operands: tuple[Annotated[Condition | Group, Field(discriminator="type")], ...]


Group.model_rebuild()

Filter = Annotated[Condition | Group, Field(discriminator="type")]
"""A ``Condition`` or a ``Group``: anything ``F`` builds."""


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
    """A field to filter on. Apply an operator to get a ``Condition``.

    Every operator a schema may list is a method of the same name (``in`` is ``in_`` because of
    the keyword), and the scalar ones double as Python comparison operators:

    ======================  ==================================  =============================
    wire operator           method                              operator form
    ======================  ==================================  =============================
    eq, ne                  ``.eq(v)``, ``.ne(v)``              ``F(x) == v``, ``F(x) != v``
    gt, gte, lt, lte        ``.gt(v)`` ... ``.lte(v)``          ``>``, ``>=``, ``<``, ``<=``
    in, nin                 ``.in_([..])``, ``.nin([..])``
    contains_any, _all      ``.contains_any([..])``, ``_all``    list fields only
    anything                ``.op("name", v)``                  for operators that arrive as text
    ======================  ==================================  =============================

    ``in_range(lo, hi)`` is ``gte & lte``. ``&`` and ``|`` make groups; ``F.all(...)`` and
    ``F.any(...)`` do the same for a list of filters.

    Nothing is checked here: a field, operator or value is validated against a source's
    published schema when the filter meets one, in ``Source.where`` or ``FilterSchema.validate``.
    The usual slips raise at once instead: a condition has no truth value (``if F(x) == v:``
    is always a bug), ``~`` is refused because the Space accepts no ``not``, a bare string is
    refused where a list is due, and a missing pair of parentheses around a comparison is
    named as such.

    Example:
            >>> F("author") == "Joe Rogan"
            Condition(type='condition', field='author', op='eq', value='Joe Rogan')
            >>> F("tags").contains_any(["sleep", "health"]).to_wire()
            {'type': 'condition', 'field': 'tags', 'op': 'contains_any', 'value': ['sleep', 'health']}
            >>> both = F("published").in_range("2026-01-01", "2026-06-30") & F("author").ne("Joe Rogan")
            >>> both.op, [c.op for c in both.operands]
            ('and', ['gte', 'lte', 'ne'])

        Because ``==`` builds a condition, an ``F`` is not hashable and never compares equal to
        anything; compare the conditions it builds instead.
    """

    def __init__(self, name: str) -> None:
        """Name the field to filter on.

        Args:
            name: a metadata key the source publishes as filterable.
        """
        self.name = name

    def op(self, op: str, value: Any) -> Condition:
        """``field op value`` with the operator given as a string.

        The generic entry point for a condition that arrives from a form or a model.

        Args:
            op: a wire operator name, as a schema lists it: ``eq``, ``gte``, ``in``, ...
            value: a scalar, a ``datetime``, or an iterable for the list operators.

        Returns:
            The condition.

        Example:
            >>> F("published").op("gte", "2026-01-01") == (F("published") >= "2026-01-01")
            True
        """
        return Condition(field=self.name, op=op, value=_wire_value(value))

    def eq(self, value: Any) -> Condition:
        """``field == value``.

        Args:
            value: a scalar, or a ``datetime`` (sent as ISO 8601).

        Returns:
            The condition.

        Example:
            >>> F("author").eq("Joe Rogan").to_wire()["op"]
            'eq'
        """
        return self.op("eq", value)

    def ne(self, value: Any) -> Condition:
        """``field != value``.

        Args:
            value: a scalar, or a ``datetime`` (sent as ISO 8601).

        Returns:
            The condition.

        Example:
            >>> F("author").ne("Joe Rogan") == (F("author") != "Joe Rogan")
            True
        """
        return self.op("ne", value)

    def gt(self, value: Any) -> Condition:
        """``field > value``.

        Args:
            value: a scalar, or a ``datetime`` (sent as ISO 8601).

        Returns:
            The condition.

        Example:
            >>> F("score").gt(0.5).value
            0.5
        """
        return self.op("gt", value)

    def gte(self, value: Any) -> Condition:
        """``field >= value``.

        Args:
            value: a scalar, or a ``datetime`` (sent as ISO 8601).

        Returns:
            The condition.

        Example:
            >>> F("published").gte("2026-01-01").op
            'gte'
        """
        return self.op("gte", value)

    def lt(self, value: Any) -> Condition:
        """``field < value``.

        Args:
            value: a scalar, or a ``datetime`` (sent as ISO 8601).

        Returns:
            The condition.

        Example:
            >>> F("pages").lt(10).to_wire()
            {'type': 'condition', 'field': 'pages', 'op': 'lt', 'value': 10}
        """
        return self.op("lt", value)

    def lte(self, value: Any) -> Condition:
        """``field <= value``.

        Args:
            value: a scalar, or a ``datetime`` (sent as ISO 8601).

        Returns:
            The condition.

        Example:
            >>> F("pages").lte(10) == (F("pages") <= 10)
            True
        """
        return self.op("lte", value)

    def in_range(self, lo: Any, hi: Any) -> Group:
        """``lo <= field <= hi``, both ends included.

        One ``and`` group of ``gte`` and ``lte``. A half-open range is written out:
        ``(F(x) >= lo) & (F(x) < hi)``.

        Args:
            lo: the low end, included.
            hi: the high end, included.

        Returns:
            The ``and`` group.

        Example:
            >>> F("n").in_range(1, 5).to_wire()["operands"][1]
            {'type': 'condition', 'field': 'n', 'op': 'lte', 'value': 5}
        """
        return self.gte(lo) & self.lte(hi)

    def in_(self, values: Any) -> Condition:
        """``field`` is one of ``values``. Any iterable; sent as a list.

        Args:
            values: any iterable of scalars; sent as a list. A bare string is refused.

        Returns:
            The condition.

        Example:
            >>> F("author").in_(("Joe Rogan", "Theo Von")).to_wire()["value"]
            ['Joe Rogan', 'Theo Von']
        """
        return self.op("in", _values(values))

    def nin(self, values: Any) -> Condition:
        """``field`` is none of ``values``. ``not_in`` is the same method.

        Args:
            values: any iterable of scalars; sent as a list.

        Returns:
            The condition.

        Example:
            >>> F("author").nin(["a"]).op, F("author").not_in(["a"]).op
            ('nin', 'nin')
        """
        return self.op("nin", _values(values))

    not_in = nin

    def __eq__(self, value: object) -> Condition:  # type: ignore[override]
        return self.eq(value)

    def __ne__(self, value: object) -> Condition:  # type: ignore[override]
        return self.ne(value)

    __gt__ = gt
    __ge__ = gte
    __lt__ = lt
    __le__ = lte

    def contains_any(self, values: Any) -> Condition:
        """A list field shares at least one element with ``values``.

        Args:
            values: any iterable of elements; sent as a list.

        Returns:
            The condition.

        Example:
            >>> F("tags").contains_any(["sleep", "health"]).to_wire()["value"]
            ['sleep', 'health']
        """
        return self.op("contains_any", _values(values))

    def contains_all(self, values: Any) -> Condition:
        """A list field holds every element of ``values``.

        Args:
            values: any iterable of elements; sent as a list.

        Returns:
            The condition.

        Example:
            >>> F("tags").contains_all(["sleep", "health"]).op
            'contains_all'
        """
        return self.op("contains_all", _values(values))

    __hash__ = None  # type: ignore[assignment]

    def __invert__(self) -> Condition:
        # TypeError is what Python raises for an unsupported ``~``; ours says what to use.
        raise TypeError(_NO_NOT_HINT)

    def __and__(self, other: Any) -> Group:
        # Raised, not ``NotImplemented``: ``1 & F("b")`` would otherwise fall back to
        # Python's bare "unsupported operand" message and lose the parentheses hint.
        raise TypeError(f"{self!r} is a field, not a filter; {_PRECEDENCE_HINT}")

    __or__ = __and__
    __rand__ = __and__
    __ror__ = __and__

    @staticmethod
    def all(*filters: Condition | Group) -> Group:
        """Every filter must hold: ``a & b & ...`` for a list.

        Args:
            *filters: conditions or groups.

        Returns:
            One ``and`` group.

        Example:
            >>> F.all(F("a") == 1, F("b") == 2).op
            'and'
        """
        return _join("and", *filters)

    @staticmethod
    def any(*filters: Condition | Group) -> Group:
        """At least one filter must hold: ``a | b | ...`` for a list.

        Args:
            *filters: conditions or groups.

        Returns:
            One ``or`` group.

        Example:
            >>> F.any(*[F("author") == a for a in ("a", "b")]).to_wire()["op"]
            'or'
        """
        return _join("or", *filters)

    def __repr__(self) -> str:
        return f"F({self.name!r})"


def depth(node: Condition | Group) -> int:
    """Groups on the longest path: a bare condition is 0, a flat group 1.

    Args:
        node: a condition or group.

    Returns:
        The nesting depth.
    """
    if isinstance(node, Condition):
        return 0
    return 1 + max(depth(o) for o in node.operands)


def condition_count(node: Condition | Group) -> int:
    """Conditions in the tree, however nested.

    Args:
        node: a condition or group.

    Returns:
        The count.
    """
    if isinstance(node, Condition):
        return 1
    return sum(condition_count(o) for o in node.operands)


class FieldFilterSpec(Frozen):
    """What a query may do with one field: its published ``type`` and operators.

    Types are ``string``, ``number``, ``boolean``, ``datetime`` and the list forms ``string[]``
    and ``number[]``. A list field takes ``contains_any`` / ``contains_all``; a scalar field
    takes the comparisons and ``in`` / ``nin``. The Space decides; this is what it said.
    """

    type: str
    ops: tuple[str, ...] = ()


class FilterSchema(Frozen):
    """``query_schema.filters`` as the Space published it.

    The filterable ``fields``, the group ``logic`` a query may use, and the size caps.
    ``Source.filter_schema`` holds one per source. Unknown keys in the published dict are
    ignored, so a newer Space never breaks an older SDK.

    ``validate`` runs the same checks the Space runs, in the same order and with the same words,
    so an app can refuse a filter before sending it and show the Space's own reason.

    Example:
        >>> schema = FilterSchema.from_dict({
        ...     "fields": {
        ...         "author": {"type": "string", "ops": ["eq", "ne", "in", "nin"]},
        ...         "tags": {"type": "string[]", "ops": ["contains_any", "contains_all"]},
        ...         "published": {"type": "datetime", "ops": ["gt", "gte", "lt", "lte"]},
        ...     },
        ... })
        >>> schema.validate(F("author") == "x") == (F("author") == "x")
        True
        >>> for bad in (F("title") == "x", F("tags") == "x", F("published") >= "soon"):
        ...     try:
        ...         schema.validate(bad)
        ...     except FilterError as e:
        ...         print(f"{e.field}: {e.reason}")
        title: not a filterable field
        tags: operator 'eq' is not allowed for a string[] field; allowed: ['contains_any', 'contains_all']
        published: cannot parse 'soon' as datetime
    """

    fields: dict[str, FieldFilterSpec] = Field(default_factory=dict)
    logic: tuple[str, ...] = ("and", "or")
    max_depth: int = 5
    max_conditions: int = 50
    max_list_values: int = 100

    def validate(self, filter: Condition | Group) -> Condition | Group:  # type: ignore[override]
        """Run the Space's checks on ``filter`` before it is sent.

        Checks run in the Space's order: the depth and condition caps, then per node the group
        logic, the field, the operator, list versus single value, the list cap, and whether
        each value reads as the field's type.

        Args:
            filter: the condition or group to check.

        Returns:
            The filter, unchanged.

        Raises:
            FilterError: for the first thing the Space would refuse, with the Space's own
                ``field`` and ``reason``; ``field`` is ``<group>`` for a group-level problem.
        """
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
    """A source named in a plan, with the filter it is queried with.

    ``Source.where`` builds one, already checked against that source's schema; it goes into
    ``hub.search`` in place of the path. A bare path is a selection with no filter.

    Example:
        >>> SourceSelection(path="nasa/news", filters=F("author") == "x").filters.op
        'eq'
    """

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
