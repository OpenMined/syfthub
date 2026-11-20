# Filtering by metadata

[← Python SDK guide](README.md)

A source that publishes `query_schema.filters` can narrow a search by document metadata: only this
author, only after this date, only chunks tagged with one of these. You build the filter with `F`,
attach it to the source with `where`, and pass that selection to `hub.search` in place of the path.

```python
from syfthub import F

source = await hub.sources.get("nasa/news")
source.filter_schema.fields          # {"published": FieldFilterSpec(type="datetime", ops=(...)), ...}

recent = F("published") >= "2026-10-01"
moon = F("tags").contains_any(["moon", "artemis"])
plan = hub.search("Artemis launches", [source.where(recent, moon), "esa/news"])
```

Filters apply per source, because fields differ per source: a filter rides only on a source you
name, never on an automatic pick. `where(a, b)` is `where(a & b)`.

## What you may filter on

`source.filter_schema` is what the publisher's Space said: the filterable fields, each with its
type and operators, the group logic a query may use, and the size caps.

```python
schema = source.filter_schema            # None when the source publishes no schema
schema.fields["published"].type          # "datetime"
schema.fields["published"].ops           # ("eq", "ne", "gt", "gte", "lt", "lte")
schema.logic, schema.max_depth           # ("and", "or"), 5
```

Types are `string`, `number`, `boolean`, `datetime` and the list forms `string[]` and `number[]`.
A scalar field takes the comparisons and `in` / `nin`; a list field takes `contains_any` /
`contains_all`. The Space decides which of those each field gets; the SDK does not guess.

## Building a filter

Every operator a schema lists is a method of `F` with the same name, so what `filter_schema`
prints is what you type. The scalar comparisons double as Python operators.

| Wire operator | Method | Operator form | Takes |
|---|---|---|---|
| `eq`, `ne` | `.eq(v)`, `.ne(v)` | `F(x) == v`, `F(x) != v` | one value |
| `gt`, `gte`, `lt`, `lte` | `.gt(v)` ... `.lte(v)` | `>`, `>=`, `<`, `<=` | one value |
| `in`, `nin` | `.in_([...])`, `.nin([...])` (`.not_in` is the same) | | a list |
| `contains_any`, `contains_all` | `.contains_any([...])`, `.contains_all([...])` | | a list, list fields only |
| any | `.op("name", v)` | | for operators that arrive as text |

```python
F("author") == "Joe Rogan"                              # Condition
F("published").in_range("2026-10-01", "2026-10-31")     # gte & lte, both ends included
F("author").in_(["Joe Rogan", "Theo Von"])
F("published").op("gte", "2026-01-01")                  # the operator as a string, from a form or a model
```

`&` and `|` combine conditions into groups; `F.all(...)` and `F.any(...)` do the same for a list.
A same-operator group flattens, so `a & b & c` is one `and` of three.

```python
(F("published") >= "2026-10-01") & (F("author") != "Joe Rogan")
F.any(*[F("author") == name for name in names])
```

Values go out as JSON: a `datetime` as ISO 8601 with a zone, a naive one taken as UTC; a string
such as `"2026-10-01"` is passed through and checked against the field's type at `where`.

### Slips the builder refuses

Each of these raises `TypeError` at once rather than sending a wrong query:

- `if F("a") == "x":` has no truth value. `==` built a `Condition`; compare with `is None` instead.
- `~filter`. The Space accepts no `not`; use `ne`, `nin` or `contains_any`.
- `F("author").in_("abc")`. A bare string where a list is due; wrap it in a list.
- `F("a") == 1 & F("b") == 2`. `&` binds tighter than `==`; wrap each comparison in parentheses.

## Where a filter is checked

1. **`source.where(filter)`** runs the Space's own checks against the published schema and raises
   `FilterError(field, reason)` with the words the Space would answer: unknown field, operator not
   allowed for the field's type, list operator with a single value or the reverse, a value that
   does not read as the field's type, too deep or too many conditions. A source with no schema
   refuses every filter.
2. **`FilterSchema.validate(filter)`** runs the same checks on their own, for an app that builds
   filters from user input and wants to show the reason before composing a plan.
3. **Pre-flight** checks again, so a plan rebuilt from a dict is covered.
4. **The Space** has the last word. A filter it still refuses lands in `results.failed` for that
   source as `Reason.INVALID_FILTER` with `error` carrying its `field: reason`, never as a
   silently unfiltered answer.

```python
try:
    selection = source.where(F("title") == "x")
except syfthub.FilterError as e:
    e.path, e.field, e.reason    # "nasa/news", "title", "not a filterable field"
```

## In a plan

`SearchPlan.filters` maps a path to its filter, and `plan.filter_for(path)` reads one back; the
plan's `to_dict` carries them, so a saved plan resumes with its filters. `results.retry()` keeps
them too.

## In tests

`FakeHub.add_source(..., filters=...)` declares a schema, and the fake Space refuses a filter
outside it with the Space's own 400:

```python
fake.add_source("nasa", "news", filters={"fields": {"published": {"type": "datetime", "ops": ["gte"]}}})
```

See [Testing your app](testing.md). The example `examples/openai_chat_filters.py` turns a published
schema into an OpenAI tool, validates what the model extracted, and feeds a refusal back to it once.
