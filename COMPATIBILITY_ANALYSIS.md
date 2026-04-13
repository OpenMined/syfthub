# SyftHub ↔ Syft Space (`multi-wallet-fr`) Compatibility Analysis

**Branch under analysis:** `shubham/feat/multi-wallet-fr`
**Date:** 2026-04-13

---

## Integration Overview

When a Syft Space endpoint is published to SyftHub, `publish_handler._build_publish_payload()` constructs the endpoint JSON and sends it via the SyftHub sync API. That payload's `policies` array is what SyftHub stores and its frontend renders. The integration is one-directional: Syft Space pushes, SyftHub displays.

---

## Issue 1 — CRITICAL: `wallet_type` top-level field breaks SyftHub's `Policy` schema ⚠️ Not fixed

**Location:** Syft Space `publish_handler.py:467`

```python
policy_data["wallet_type"] = wtype   # ← top-level, not inside "config"
```

SyftHub's `Policy` Pydantic model has `extra="forbid"` (`schemas/endpoint.py`):

```python
class Policy(BaseModel):
    type: str
    version: str
    enabled: bool
    description: str
    config: Dict[str, Any]

    model_config = ConfigDict(extra="forbid")   # rejects unknown fields
```

Sending `wallet_type` as a top-level key causes a **Pydantic validation error** on SyftHub's endpoint sync/create routes. Any endpoint with a Xendit or MPP policy will fail to publish.

**Required fix (in Syft Space `publish_handler.py`):** Remove the `wallet_type` line entirely — SyftHub has no use for it.

---

## Issue 2 — CRITICAL: Wrong config key for the credits URL ✅ Fixed

**Location (SyftHub frontend, before fix):** `xendit-policy-content.tsx`

```tsx
// Before
const bundleUsageUrl = isValidUrl(config.bundle_usage_url) ? config.bundle_usage_url : null;

// After
const bundleUsageUrl = isValidUrl(config.credits_url) ? config.credits_url : null;
```

The Syft Space publish handler injects `credits_url` into the policy config, but the SyftHub frontend was reading `bundle_usage_url`. The key never matched so `bundleUsageUrl` was always `null` — the component permanently showed "not subscribed" even after a valid purchase.

**Fix applied:** `xendit-policy-content.tsx` updated to read `config.credits_url`. Committed to `feat/credits-url-fix`.

---

## Issue 3 — CRITICAL: `credits_url` path consistency ✅ Not an issue

**Original claim:** The publish handler used `/bundles/{slug}` but the actual route was `/bundle-usage/{slug}`.

**Correction:** This was a documentation error. The actual route in the Space PR is:

```python
# payments/gateway/routes.py:62
@router.get("/bundles/{endpoint_slug}", response_model=BundleUsageResponse)
```

And the publish handler correctly injects:

```python
# publish_handler.py:474
f"{base}/api/v1/payments/gateway/bundles/{endpoint.slug}"
```

Both are `/bundles/{slug}` — they were always consistent. The SyftHub test fixtures were aligned to use `/bundles/test-endpoint` to match.

---

## Issue 4 — MAJOR: `bundles` vs `bundle_tiers` — field name and shape mismatch ✅ Fixed

**Syft Space sends** (from `XenditPolicyConfig`):
```json
{
  "price_per_request": 500.0,
  "currency": "IDR",
  "bundles": [{ "name": "Starter", "amount": 10000 }]
}
```

**SyftHub frontend was reading** `config.bundle_tiers` with shape `{name, units, unit_type, price}`.

Because the field names didn't match, the Available Plans table always rendered empty.

**Fix applied:** `xendit-policy-content.tsx` rewritten to consume `config.bundles` as `MoneyBundle[]` directly (no transformation). The `BundleTier` interface, the conditional normalization block, and the `pricePerRequest` fallback logic were all removed. Committed to `feat/credits-url-fix`.

---

## Issue 5 — MAJOR: `mpp_accounting` policy type unknown to SyftHub frontend ✅ Fixed

**Location (SyftHub, before fix):** `policy-item.tsx`

`POLICY_TYPE_CONFIG` had no entry for `"mpp_accounting"` → the policy card rendered as a generic unstyled fallback with no label, icon, or description.

**Fix applied:** Added `mpp_accounting` entry to `POLICY_TYPE_CONFIG`:

```tsx
mpp_accounting: {
  icon: Coins,
  label: 'MPP Micro-payment',
  color: 'text-emerald-600 dark:text-emerald-400',
  bgColor: 'bg-emerald-50 dark:bg-emerald-950/30',
  borderColor: 'border-emerald-200 dark:border-emerald-800',
  description: 'Pay-per-request micro-payment via MPP blockchain'
},
```

Committed to `feat/credits-url-fix`.

---

## Issue 6 — MINOR: Archived endpoints not reflected in SyftHub ✅ Fixed

The Space PR adds `archived: bool` to the `Endpoint` entity with `POST /endpoints/{slug}/archive` and `POST /endpoints/{slug}/unarchive`. SyftHub had no `archived` concept — archived endpoints would continue appearing as active on the marketplace.

**Fix applied** (all committed to `feat/credits-url-fix`):

- **`models/endpoint.py`** — added `archived: Mapped[bool]` column + `idx_endpoints_archived` index
- **`schemas/endpoint.py`** — added `archived` to `EndpointBase`, `EndpointUpdate`, `Endpoint`, `EndpointResponse`, `EndpointPublicResponse`
- **`services/endpoint_service.py`** — forces `visibility = PRIVATE` when `archived=True` on create and update
- **`alembic/versions/20260413_000000_add_archived_to_endpoints.py`** — migration `009_add_archived` (down_revision: `008_encrypt_accounting_pw`)

---

## Summary Table

| # | Severity | Status | Description |
|---|---|---|---|
| 1 | **CRITICAL** | ⚠️ **Not fixed** — requires change in Syft Space `publish_handler.py` | `wallet_type` at top-level fails SyftHub's `extra="forbid"` on every publish |
| 2 | **CRITICAL** | ✅ Fixed in `xendit-policy-content.tsx` | Key mismatch: frontend was reading `bundle_usage_url`, Space PR sends `credits_url` |
| 3 | **CRITICAL** | ✅ Not an issue — documentation error | Path is `/bundles/{slug}` in both publish handler and actual route |
| 4 | **MAJOR** | ✅ Fixed in `xendit-policy-content.tsx` | Frontend now reads `bundles[{name,amount}]` directly; `bundle_tiers` logic removed |
| 5 | **MAJOR** | ✅ Fixed in `policy-item.tsx` | `mpp_accounting` type added to `POLICY_TYPE_CONFIG` |
| 6 | **MINOR** | ✅ Fixed — model + schema + service + migration | `archived` field propagated through SyftHub's data layer |
