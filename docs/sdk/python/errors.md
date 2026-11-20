# Errors

[← Python SDK guide](README.md)

Two kinds of trouble, kept apart on purpose: a mistake in your process raises, and trouble with one
source at execute time lands in that source's row, so one bad Space never costs you the others.

## What raises

All errors derive from `syfthub.SyftHubError`.

| Error | When |
|---|---|
| `ConfigurationError` | Bad URL, token and password both given, invalid `Options`. |
| `ValidationError` | Also a `ValueError`: blank query, threshold out of range, malformed path, no bundle covers a shortfall. |
| `FilterError` | Also a `ValueError`: a filter the source's published schema refuses; `.field` and `.reason` are the Space's own words, `.path` the source. |
| `AuthError` | Login refused, or the token expired and could not be renewed. |
| `HubUnreachable` | The Hub itself cannot be reached after retries. |
| `SourceNotFound` | `hub.sources.get` on an unknown path. |
| `ActionRequired` | `execute(strict=True)` with pending actions; carries `.actions`. |
| `PaymentFailed` | A wallet, top-up or invoice call was refused; `.code` carries the Hub's code when there is one. At execute time an MPP refusal lands in the row instead. |
| `PaymentTimeout` | `invoice.wait_paid` ran out of time. |
| `StaleSnapshot` | A dict from an incompatible SDK version. |

`TypeError` is raised by the filter builder for the slips listed in
[Filtering by metadata](filters.md#slips-the-builder-refuses), and by the sync twin for a call
from its own loop thread or after `close()` (as `RuntimeError`).

## Per-source outcomes

Every `SourceResult` in `Results` has an `Outcome` and, when it did not return, a `Reason`.

| Outcome | Meaning |
|---|---|
| `RETURNED` | The Space answered. `documents`, `summary`, `cost`, `charges`. |
| `HELD` | Not sent: `reason` is the pre-flight verdict (`NO_CREDITS`, `OVER_BUDGET`, `ACCESS_DENIED`, `CIRCUIT_OPEN`, `BY_USER`, `UNREACHABLE`). |
| `REJECTED` | The Space refused: `RATE_LIMITED` (with `rate_limit.reset_seconds`), `ACCESS_DENIED`, `NO_PRICING_TIER`, `BLOCKED`, `NOT_PUBLISHED`, `AUTH`. |
| `FAILED` | Transport or server trouble: `TIMEOUT`, `SERVER_ERROR`, `UNREACHABLE`, `NOT_FOUND`; or `INVALID_FILTER` when the Space refused the plan's filter, with `error` carrying its `field: reason`. |
| `PAYMENT_REQUIRED` | A 402 the SDK could not settle: `topup` or `charge` says why. |

`row.retryable` is True for a transient failure, a rate limit, or a host whose circuit was open at
the time; `results.retry()` re-sends exactly those. A row held for credits, budget, access or by
you is not retryable: something has to change first, and `pre.actions` says what.
