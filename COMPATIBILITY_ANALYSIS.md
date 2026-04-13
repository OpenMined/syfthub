# SyftHub ↔ Syft Space (`multi-wallet-fr`) Compatibility Analysis

**Branch under analysis:** `shubham/feat/multi-wallet-fr`
**Date:** 2026-04-13

---

## Integration Overview

When a Syft Space endpoint is published to SyftHub, `publish_handler._build_publish_payload()` constructs the endpoint JSON and sends it via the SyftHub sync API. That payload's `policies` array is what SyftHub stores and its frontend renders. The integration is one-directional: Syft Space pushes, SyftHub displays.

---

## Issue 1 — CRITICAL: `wallet_type` top-level field breaks SyftHub's `Policy` schema

**Location:** `publish_handler.py:467`

```python
policy_data["wallet_type"] = wtype   # ← top-level, not inside "config"
```

SyftHub's `Policy` Pydantic model has `extra="forbid"` (`schemas/endpoint.py:79`):

```python
class Policy(BaseModel):
    type: str
    version: str
    enabled: bool
    description: str
    config: Dict[str, Any]

    model_config = ConfigDict(extra="forbid")   # rejects unknown fields
```

Sending `wallet_type` as a top-level key causes a **Pydantic validation error** on SyftHub's endpoint sync/create routes. Any Xendit or MPP endpoint publish will fail.

**Fix (in Syft Space `publish_handler.py`):** Move `wallet_type` inside `config`:
```python
policy_data["config"]["wallet_type"] = wtype
```

---

## Issue 2 — CRITICAL: Wrong config key for the bundle-usage URL ✅ Fixed here

**Location (Syft Space):** `publish_handler.py:473`

```python
policy_data["config"]["credits_url"] = (
    f"{base}/api/v1/payments/gateway/bundle-usage/{endpoint.slug}"
)
```

**Location (SyftHub, before fix):** `xendit-policy-content.tsx:71`

```tsx
const bundleUsageUrl = isValidUrl(config.bundle_usage_url) ? config.bundle_usage_url : null;
```

The Syft Space publish handler sends `credits_url` but the SyftHub frontend was reading `bundle_usage_url`. Because the key didn't match, `bundleUsageUrl` was always `null` → the component permanently showed "not subscribed" even after purchase.

**Fix applied:** `xendit-policy-content.tsx` updated to read `config.credits_url`.

---

## Issue 3 — CRITICAL: Wrong URL path for bundle-usage endpoint ✅ Fixed here

**Location (Syft Space `publish_handler.py`, before fix):**
```
/api/v1/payments/gateway/bundles/{slug}
```

**Actual route defined in the PR (`payments/gateway/routes.py`):**
```
GET /payments/gateway/bundle-usage/{endpoint_slug}
```

The old path 404s. Even if the key name mismatch were fixed, calls to check remaining balance would fail.

**Fix applied:** SyftHub test fixtures updated to use `/bundle-usage/{slug}` and `credits_url` key throughout `test_endpoints.py`.

---

## Issue 4 — MAJOR: `bundles` vs `bundle_tiers` — field name and shape mismatch

**Location (Syft Space):** `publish_handler.py:460` sends `policy.configuration` verbatim.

`XenditPolicyConfig` produces:
```json
{
  "price_per_request": 100.0,
  "currency": "IDR",
  "bundles": [{ "name": "Starter", "amount": 10000 }]
}
```

SyftHub's `xendit-policy-content.tsx` reads `config.bundle_tiers` and expects:
```ts
interface BundleTier {
  name: string
  units: number       // request count
  unit_type: string   // "requests"
  price: number       // IDR amount
}
```

| What PR sends | What SyftHub frontend expects |
|---|---|
| `config.bundles` | `config.bundle_tiers` |
| `bundles[n].amount` | `bundle_tiers[n].price` |
| *(missing)* | `bundle_tiers[n].units` (derived: `amount / price_per_request`) |
| *(missing)* | `bundle_tiers[n].unit_type` ("requests") |

`units` can be derived: `Math.floor(bundle.amount / price_per_request)`.

**Fix (in Syft Space `publish_handler.py`):** Transform `bundles` → `bundle_tiers` before sending to SyftHub:
```python
raw_config = dict(policy.configuration)
price_per_req = raw_config.get("price_per_request", 1)
raw_bundles = raw_config.pop("bundles", None) or []
raw_config["bundle_tiers"] = [
    {
        "name": b["name"],
        "units": int(b["amount"] / price_per_req) if price_per_req else 0,
        "unit_type": "requests",
        "price": b["amount"],
    }
    for b in raw_bundles
]
policy_data["config"] = raw_config
```

---

## Issue 5 — MAJOR: `mpp_accounting` policy type unknown to SyftHub frontend

When a Syft Space endpoint with MPP pricing is published, the policy type sent is `"mpp_accounting"`. SyftHub's `policy-item.tsx` only maps these types to styled components:

```
transaction, xendit, public, private, authenticated, internal, rate_limit, quota, geographic
```

`mpp_accounting` has no entry in `POLICY_TYPE_CONFIG` → renders as a generic unknown policy, no pricing display.

**Fix options:**
- Add `mpp_accounting` as a new entry in SyftHub's `POLICY_TYPE_CONFIG` pointing to `TransactionPolicyContent` (or a new MPP-specific component)
- OR publish it under type name `"transaction"` from Syft Space (conflates semantics, not recommended)

---

## Issue 6 — MINOR: Archived endpoints not reflected in SyftHub

The PR adds `archived: bool` to the `Endpoint` entity with `POST /endpoints/{slug}/archive`. SyftHub has no concept of `archived`. When an endpoint is archived on Syft Space, new purchases should be blocked and it should not be prominently displayed as active on the marketplace. Currently, the sync flow still pushes it as `"visibility": "public"`.

**Fix (in Syft Space `publish_handler.py`):** When `endpoint.archived == True`, either delete the endpoint from SyftHub or set `visibility: "private"` in the sync payload.

---

## Summary Table

| # | Severity | Fix location | Description |
|---|---|---|---|
| 1 | **CRITICAL** | Syft Space `publish_handler.py` | `wallet_type` sent at top-level, `extra="forbid"` causes sync to fail |
| 2 | **CRITICAL** | **SyftHub** `xendit-policy-content.tsx` ✅ | Key mismatch: `credits_url` vs `bundle_usage_url` — balance check always fails |
| 3 | **CRITICAL** | **SyftHub** `test_endpoints.py` ✅ | URL path `/bundles/{slug}` → `/bundle-usage/{slug}` |
| 4 | **MAJOR** | Syft Space `publish_handler.py` | `bundles[{name,amount}]` not transformed to `bundle_tiers[{name,units,unit_type,price}]` |
| 5 | **MAJOR** | SyftHub `policy-item.tsx` | `mpp_accounting` type unknown — renders as generic policy |
| 6 | **MINOR** | Syft Space `publish_handler.py` | Archived state not communicated to SyftHub |
