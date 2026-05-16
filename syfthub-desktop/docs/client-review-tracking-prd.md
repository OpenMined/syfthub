# PRD — Client-Side Manual Review Tracking

| | |
|---|---|
| **Status** | Draft |
| **Created** | 2026-05-16 |
| **Owner** | TBD |
| **Surface** | SyftHub Desktop app (`syfthub-desktop`) — client/chat side |
| **Related** | Host-side "Requests" tab (`syfthub-desktop/manual_review_operations.go`, `RequestsTab.tsx`); `ManualReviewPolicy` in `policy-manager`; `syfthubapi` Go SDK |

---

## 1. Summary

When a SyftHub user sends a request to an agent or endpoint protected by a
**Manual Review policy**, the request does not fail and it does not return a
real answer — the response is *held* on the host for a human to approve or
reject, and the caller receives a short placeholder instead.

Today the **caller has no memory of this and no way to follow up.** The
"pending review" notice lives only in an in-memory chat transcript that is
destroyed on app restart, and there is no channel by which the caller ever
learns whether their request was eventually approved or rejected.

This PRD specifies a **Client-Side Manual Review Tracking** feature delivered
in two phases:

- **Phase 1 — Local Ledger (Strategy 1).** The desktop app durably records
  every held request the user made, with full context, in a client-local
  store, and surfaces a dedicated view to browse them. Ships against the
  system exactly as it exists today; requires no host cooperation.
- **Phase 2 — Status Query Channel (Strategy 2).** A new network capability
  the host *voluntarily exposes* lets the client ask "what happened to review
  X?" and — when approved — retrieve the real held response. The client still
  never touches the host's database or filesystem.

Phase 2's ledger **is** Phase 1's ledger; Phase 1 is a strict foundation, not
throwaway work.

A centralized, cross-device variant (hub-mediated registry, "Strategy 3") is
explicitly **out of scope** for this PRD and deferred.

---

## 2. Background & Context

### 2.1 The Manual Review policy

`ManualReviewPolicy` (in the `policy-manager` framework) is a post-execution
policy. The endpoint's handler still runs and produces a *real* response, but
the policy:

1. records the real request + response in a `manual_reviews` table inside the
   endpoint's `policy/store.db` SQLite database, with `status = 'pending'`;
2. **substitutes** the response with a short placeholder
   (`"Request submitted to manual review (reference: <review_id>)"`);
3. returns success — the caller receives the placeholder as if it were a
   normal answer.

Resolution is out of band: a human approves or rejects each held entry, which
flips the row's `status` to `approved` / `rejected`. Nothing re-delivers the
real response, and nothing notifies the original caller.

### 2.2 What already exists — the host side

The endpoint **owner** (the host) already has a complete UI: the **"Requests"
tab** under an endpoint's *General* section in the desktop app. It reads the
`manual_reviews` table directly from `policy/store.db`, lists held requests,
and lets the host approve/reject them. See `manual_review_operations.go` and
`RequestsTab.tsx`.

This PRD covers the **mirror image**: the *caller's* side. The host can see
"requests submitted *to* my endpoint"; the caller currently cannot see
"requests *I* submitted that are awaiting review."

### 2.3 Who the client is, and their hard constraints

The **client** is any party that invoked a manual-review-gated endpoint. In
the desktop app this is the **chat user** talking to an agent they do not own.
The defining constraints — which shape every decision in this document — are:

- **No database access.** The client cannot read `policy/store.db` or its
  `manual_reviews` table.
- **No filesystem access.** The client cannot see the endpoint folder where
  the host defines and runs the agent.
- **Remote.** The client reaches the endpoint only over the network
  (hub → NATS tunnel → endpoint SDK).

These constraints are *not* a limitation to engineer around — they are correct
and intentional. The client and host are different parties.

> **Key reframing:** "no database/filesystem access" does **not** mean "no
> network access." The client being unable to read the host's *files* still
> permits the host to *voluntarily expose a network API*. That distinction is
> the entire basis of Phase 2.

---

## 3. Problem Statement

From the caller's point of view, today:

1. **The record is ephemeral.** A held reply renders as a "Pending review"
   notice card in the live chat transcript. The transcript is React state in
   `use-agent-workflow.ts` — there is **no persistence** (no `localStorage`,
   no backing store). Closing the chat, switching endpoints, or restarting the
   app destroys all evidence the request was ever made.

2. **There is no status visibility.** Even within a single session, the notice
   is frozen at "pending." The host's eventual approve/reject is completely
   invisible to the caller. There is no polling, no callback, no API.

3. **The handle is fragile.** The `review_id` — the only durable reference to
   a held request — currently reaches the client **only embedded in the
   placeholder text** (`"... (reference: <id>)"`). The structured policy
   notice (`PolicyNoticeData`) carries `status`, `policy_name`, and `reason`
   but **not** `review_id`. Scraping it from free text breaks the moment a
   host customizes `placeholder_message`.

4. **The real answer is unreachable.** When a held request is approved, the
   real response exists on the host but is never delivered back. The caller is
   left permanently holding a placeholder.

**Net effect:** a user can ask an agent something, be told "this is pending
review," and then have *zero* durable record and *zero* way to ever learn the
outcome or get the answer.

---

## 4. Goals & Non-Goals

### 4.1 Goals

- **G1.** Durably persist, client-side, every manual-review-held request the
  user made — with full context: the messages/prompt sent, the target
  endpoint, the timestamp, the policy, and the `review_id`.
- **G2.** Provide a dedicated client-side view to browse and filter these
  records by status (pending / approved / rejected).
- **G3. (Phase 2)** Let the client learn the *real* resolution of a held
  request and retrieve the *approved response* — without any database or
  filesystem access.
- **G4.** Survive app restarts and chat-session changes; the record must
  outlive the in-memory transcript.

### 4.2 Non-Goals

- **N1.** Changing how the host reviews/approves requests — the host-side
  "Requests" tab is done and unchanged.
- **N2.** Centralized, cross-device, multi-client tracking (the "hub-mediated
  registry", Strategy 3). Explicitly deferred; see §11.
- **N3.** Real-time push notification of resolution. Phase 2 is **pull-only**
  (the client asks). Push is a future consideration.
- **N4.** Automatically re-injecting an approved response back into the
  original chat thread. Phase 2 *retrieves* the approved response on demand
  and displays it in the tracking view; seamless re-threading is later work.
- **N5.** Tracking for non-chat callers (raw SDK / MCP). The Phase 2 channel
  *could* serve them, but the UI in this PRD targets the desktop chat client.

---

## 5. Users & Personas

| Persona | Description | In scope |
|---|---|---|
| **The Requester** (primary) | A desktop-app user who chats with agents/endpoints owned by other people. Wants to know "what did I submit, and what happened to it?" | Yes — full UI |
| **The Host** (context only) | The endpoint owner who approves/rejects. Already served by the Requests tab. | No — unchanged |
| **SDK/MCP caller** (secondary) | A non-interactive client invoking the endpoint programmatically. | Phase 2 channel may serve them; no UI in this PRD |

---

## 6. Current State — How a Held Request Flows Today

Grounded in `use-agent-workflow.ts`, `policy-notice.tsx`, and the
`ManualReviewPolicy` / `syfthubapi` execution path.

```
Requester (desktop chat)        Hub / NATS tunnel        Endpoint host (SyftAPI process)
        |                              |                             |
        |  send message ----------------------------------------->   | run agent handler
        |                              |                             | ManualReviewPolicy.post_execute:
        |                              |                             |   • write row to manual_reviews
        |                              |                             |     (status = 'pending')
        |                              |                             |   • substitute response w/ placeholder
        |  <--- agent.message ---------------------------------------|
        |        { content: "<placeholder text w/ (reference: id)>", |
        |          policy: { status:'pending', policy_name, reason } } <-- NOTE: no review_id
        |                              |                             |
   render PolicyNotice card            |                             |
   (in-memory only — lost on restart)  |                             |
        |                              |                             |
        X  no further contact ever                                   |
                                                       host approves/rejects
                                                       (Requests tab) — caller never told
```

The two defects this feature fixes are visible above: the client-side record
is **in-memory only**, and the arrow from the host's resolution back to the
client **does not exist**.

---

## 7. Strategy & Phasing

This feature is delivered as one product in two phases plus a shared
prerequisite.

```
  ┌─────────────────────────────────────────────────────────────┐
  │ P0 — Prerequisite: surface review_id structurally            │
  │      (small SDK/notice-payload change; blocks reliable P1)    │
  └───────────────────────────┬─────────────────────────────────┘
                              │
  ┌───────────────────────────▼─────────────────────────────────┐
  │ Phase 1 — Local Ledger (Strategy 1)                          │
  │   Capture + persist + display. No host cooperation.          │
  │   Status is captured-once ('pending') + manual override.     │
  └───────────────────────────┬─────────────────────────────────┘
                              │  (same ledger, extended)
  ┌───────────────────────────▼─────────────────────────────────┐
  │ Phase 2 — Status Query Channel (Strategy 2)                  │
  │   New host-exposed network API. Real status + approved       │
  │   response retrieval. Requires framework work (see §10).     │
  └─────────────────────────────────────────────────────────────┘
```

**Phase 1 is shippable independently and immediately.** Phase 2 is the
committed end-state but is gated on the research in §10.

---

## 8. Prerequisite P0 — Surface `review_id` Structurally

**Problem.** Every strategy needs a stable, machine-readable handle on a held
request. Today the `review_id` is only inside placeholder *text*.

**Requirement.** The structured policy outcome attached to a held response
must carry the `review_id` — and, ideally, the endpoint identity and policy
name. Concretely:

- The `policy` object on a held `agent.message` event gains a `review_id`
  field (and SHOULD gain `endpoint`/`policy_name` if not already unambiguous).
- The frontend `PolicyNoticeData` interface (`policy-notice.tsx`) gains
  `review_id?: string`.
- This data originates from `PolicyResult.metadata` (which already contains
  `review_id` and `status`) — the work is *plumbing it through* the agent
  event payload, not generating anything new.

**Scope of change.** Host/SDK side: `syfthubapi` (`agent_executor.go` builds
the held `agent.message`). Small, well-contained.

**Open question (R1, see §10).** For **non-agent** endpoints (model /
data_source), confirm whether *any* structured `policy_result` reaches the
remote caller, or only the placeholder body. If only the body, P0 must also
cover those response envelopes, or Phase 1 capture for non-agent endpoints
will have to fall back to text parsing (degraded).

**Degraded fallback.** If P0 is not yet shipped, Phase 1 may still capture
entries by parsing `(reference: <id>)` from placeholder text, flagged as a
low-confidence `review_id`. Such entries cannot be reliably queried in
Phase 2. P0 should therefore land first.

---

## 9. Phase 1 — Local Ledger (Strategy 1)

### 9.1 Overview

When the desktop chat receives a held response, the app writes a record to a
**client-local store** and exposes a **"Sent for Review"** view. The user
gains a durable, browsable history of everything they submitted that is (or
was) under review. Status is captured as `pending` and — because Phase 1 has
no channel to the host — can otherwise only be changed by an explicit **manual
override** by the user.

This phase requires **zero** changes on the host and **zero** new network
traffic.

### 9.2 Data model

A ledger entry (illustrative shape — final storage format is a §10 decision):

```
ReviewLedgerEntry {
  review_id:        string        // host's id (P0); empty/low-confidence if scraped
  identity:         string        // the desktop user who submitted it (scoping key)
  endpoint_slug:    string
  endpoint_owner:   string
  endpoint_name:    string        // display name shown in chat
  endpoint_type:    "agent" | "model" | "data_source"
  policy_name:      string
  request_messages: { role, content }[]   // what the user actually sent
  placeholder:      string        // the placeholder text the client received
  submitted_at:     string        // ISO-8601, client clock
  status:           "pending" | "approved" | "rejected" | "unknown"
  status_source:    "captured" | "manual" | "queried"   // "queried" reserved for Phase 2
  resolved_at:      string | null // set by manual override (P1) or query (P2)
  reject_reason:    string | null
  user_note:        string | null // optional free text the requester adds
}
```

Notes:
- `review_id` is the natural primary key. If absent (degraded capture), fall
  back to a locally generated id and mark the entry non-queryable.
- `identity` scopes the ledger to the logged-in user — the desktop app can be
  used by different identities; one user must not see another's submissions.
- `request_messages` is the heart of "context": it preserves exactly what was
  asked, independent of the ephemeral chat transcript.

### 9.3 Capture

**Trigger.** In `use-agent-workflow.ts`, when an `agent.message` arrives with a
`policy` object whose `status === 'pending'`.

**Disambiguation (R2, see §10).** A `pending` policy notice is *also* produced
by transaction/payment policies (`agent.payment_required` → a synthetic
`kind:'policy'` pending entry). Phase 1 must record **only manual-review**
holds. The discriminator is the presence of a `review_id` (manual review) vs.
a payment challenge (transaction). This rule must be specified precisely once
P0 fixes the payload.

**Idempotency.** Capture must be keyed by `review_id` so a re-render or
duplicate event does not create duplicate ledger rows.

**What to capture.** The user message(s) of the held turn, the endpoint
identity (already known to the chat — it selected the agent), the placeholder
text, `submitted_at` from the client clock, `status = 'pending'`,
`status_source = 'captured'`.

### 9.4 Storage

The ledger is **client-local**, owned by the desktop app's Go backend
(consistent with how `settings.go` owns `settings.json`). Two candidate
mechanisms — final choice is decision **D1** (§10):

| Option | Pros | Cons |
|---|---|---|
| **JSON file** in the app data dir (e.g. `sent-reviews.json`) | Simplest; mirrors `settings.go`; trivially inspectable | Whole-file rewrite; no indexed queries; awkward as it grows |
| **Local SQLite DB** (the app already bundles `modernc.org/sqlite`) | Indexed status filter; scales; natural fit for Phase 2's larger needs | Slightly more setup; a second SQLite file in the app |

**Recommendation:** lean SQLite — Phase 2 adds polling, status history, and
larger result payloads, and the dependency is already present. But JSON is
acceptable if Phase 1 must ship as fast as possible. Either way the store is
**Go-managed**, exposed to the frontend via Wails bindings, and scoped by
`identity`.

### 9.5 Display / UX

A new **"Sent for Review"** view. Important IA point: unlike the host-side
Requests tab (which is *per endpoint you own*, under *General*), this view is
**cross-endpoint** — it is "requests *I* sent to *anyone's* endpoints." It
belongs near the **Chat** experience, not under an endpoint's settings.

- **Placement (D2, §10):** a top-level destination reachable from the chat
  area, or a panel within `ChatView`.
- **List:** columns for Endpoint (agent name), Submitted (date), Status badge,
  and a one-line request preview. Status filter: All / Pending / Approved /
  Rejected — defaulting to **Pending**.
- **Detail:** the full messages sent, endpoint + policy + `review_id`,
  `submitted_at`, status, the placeholder received, `user_note`.
- **Visual language:** reuse the host Requests tab's status colours and
  badge/modal patterns (`chart-3` = pending, `chart-2` = approved,
  `destructive` = rejected) so the two surfaces feel like one system.
- **In-chat affordance:** the live `PolicyNotice` card should gain a subtle
  "Tracked in Sent for Review" cue, so the user learns the record persists.

### 9.6 Manual status override

Because Phase 1 has no channel to the host, an entry's status cannot update on
its own. The detail view offers an explicit **"Mark as approved / rejected"**
action for when the host communicates the outcome out of band (chat, email,
etc.). Such entries are stamped `status_source = 'manual'` and clearly
labelled as manually set — they must never be confused with a
system-confirmed status. This affordance is **removed/superseded** in Phase 2
for queryable entries.

### 9.7 Phase 1 edge cases

- **No `review_id`** (P0 not shipped, or non-agent endpoint): record the entry
  with a generated local id, mark it non-queryable, surface a quiet caveat.
- **Same prompt held twice:** two distinct entries (two `review_id`s).
- **Multi-turn chat after a hold:** later turns are independent; each held
  turn is its own entry.
- **Identity switch / logout:** the view shows only the active identity's
  entries; entries are retained, not deleted, on logout.
- **Storage corruption / migration:** the Go store must tolerate a
  missing/old-schema file and self-heal (see D1).

### 9.8 Phase 1 explicit limitation

Phase 1 is, honestly, a **"what I submitted"** log — not a **"what happened"**
tracker. The status column is truthful only for `pending` and for manually
overridden entries. This limitation is the entire motivation for Phase 2 and
should be stated plainly in the UI (e.g., empty-state and tooltip copy).

---

## 10. Phase 2 — Status Query Channel (Strategy 2)

> This is the section that needs **heavy research and planning.** Phase 2
> introduces a new network capability and spans three codebases
> (`policy-manager`, `syfthubapi`, the hub, plus the desktop client). What
> follows is the design intent and the open questions — not a finalized spec.

### 10.1 Overview & intent

Phase 2 adds a **read-only status-query capability** that a host *voluntarily
exposes*. The client sends a query carrying a `review_id`; the host process
reads its **own** `manual_reviews` table and answers with the current status —
and, if approved, the **real held response**. The client never touches the
database; it calls an API the host chooses to answer. The client's local
ledger (Phase 1) becomes a cache that polling keeps in sync.

This closes the loop: `pending → approved/rejected` becomes real, and the
approved answer is finally retrievable.

### 10.2 Target workflow

```
=== SUBMIT (unchanged from Phase 1) ===
Requester                Hub / tunnel             Endpoint host
   | send message ------------------------------------> run agent → hold
   | <-- agent.message { placeholder, policy:{ pending, review_id } }
   | ledger.insert(status = pending, status_source = captured)

=== POLL (new) ===
Requester                Hub / tunnel             Endpoint host (SyftAPI process)
   | review.status { review_id } --------------------->  control-request handler:
   |                                                       reads manual_reviews
   |                                                       WHERE review_id = ?
   | <-- { status, resolved_at, reject_reason?, response? } ----
   | ledger.update(entry)  // status_source = queried
   |
   |   status == pending   → leave pending, schedule next poll
   |   status == approved  → store real response, stop polling
   |   status == rejected  → store reject_reason, stop polling
```

### 10.3 RESEARCH — The query channel itself

This is the central unknown. Findings to produce before committing a spec:

- **R3 — Which component answers?** A status query is *not* a normal endpoint
  invocation (it must not run the agent handler). The `ManualReviewPolicy`
  itself is not a service — it runs inside a short-lived per-request runner
  subprocess. The **long-lived endpoint SDK process** (`syfthubapi`,
  `SyftAPI.Run()`) is the natural responder: it already configures the policy
  store path (`StoreConfig.Path = policy/store.db`) and so can read the
  `manual_reviews` table directly and cheaply, without spawning the policy
  runner. **Proposed direction:** a new *control request type* the SDK
  recognizes and handles inline, ahead of normal handler dispatch.

- **R4 — Request type & routing.** How does a `review.status` request travel
  the existing hub → NATS-tunnel path and get distinguished from a normal
  invocation? Options to evaluate: a reserved message type/header on the
  tunnel protocol; a dedicated subject; a reserved slug/path. Must coexist
  with current routing without breaking older endpoints.

- **R5 — Capability & auth model.** The `review_id` is a 12-hex unguessable
  token. Treat it as a **bearer capability** (holding it authorizes querying
  that one review). Evaluate whether to *additionally* bind to identity: the
  `manual_reviews` row stores `user_id`; the SDK could require the
  authenticated caller to equal `review.user_id`. Decision: capability-only
  (simple) vs. capability + identity (defense in depth). Recommendation leans
  capability + identity, since the caller is already hub-authenticated.

- **R6 — Response semantics & rejected-content safety.** The query result:
  - `pending` → `{ status: 'pending' }`
  - `approved` → `{ status, resolved_at, response: <real held output> }`
  - `rejected` → `{ status, resolved_at, reject_reason }` — and **must not**
    include the held `output`. The host gated delivery deliberately; a
    rejection must never leak the content through the status channel. This is
    a hard security requirement, not a preference.

- **R7 — Capability discovery / versioning.** Endpoints running an older SDK
  will not understand `review.status`. The client must detect "this endpoint
  does not support status queries" and degrade gracefully to Phase 1 behavior
  (entry stays `pending`, manual override still offered). Evaluate explicit
  capability advertisement vs. a well-defined "unsupported" error.

- **R8 — Offline hosts.** If the endpoint process is not running, the query
  simply fails. The client must treat this as "unknown, retry later" — never
  as rejected, never as an error state that loses the entry.

- **R9 — Non-agent endpoints.** Confirm the channel works uniformly for
  `model` and `data_source` endpoints, whose held outputs have different
  shapes (e.g. a data_source returns a document list). The decode logic
  already in `manual_review_operations.go` (`decodeReviewOutput`) is a
  reference for shaping the returned `response`.

### 10.4 RESEARCH — Polling lifecycle

- **R10 — Cadence.** When does the client poll? Candidates: on app launch, on
  opening the "Sent for Review" view, on an explicit Refresh, and/or a gentle
  background interval. A held review may take hours or days to resolve —
  aggressive polling is wasteful and hammers hosts.
- **R11 — Backoff & batching.** Define a backoff curve for long-pending
  entries. Consider batching: one query carrying multiple `review_id`s for the
  *same endpoint*, vs. one query per review.
- **R12 — Termination.** Polling for an entry stops permanently once it
  reaches a terminal status (`approved` / `rejected`).
- **R13 — Trust of queried status.** A `queried` status from the host is
  authoritative and supersedes any `manual` override. Define precedence.

### 10.5 Phase 2 UI deltas

- The "Sent for Review" list reflects real, queried statuses; entries move out
  of the **Pending** filter automatically as they resolve.
- The detail view, for an `approved` entry, shows the **retrieved real
  response** — the answer the caller was originally denied.
- A per-entry and global **Refresh** triggers an immediate poll.
- The manual-override affordance (§9.6) is hidden for queryable entries; it
  remains only for entries with no usable `review_id`.
- A subtle indicator distinguishes `captured` / `queried` / `manual` status
  provenance.

### 10.6 Phase 2 scope note

Phase 2 is **cross-repo**: it touches `policy-manager` (and/or `syfthubapi`)
for the responder, the tunnel/hub layer for routing, and the desktop client.
It cannot be scoped or estimated until R3–R13 are resolved. Treat §10 as a
**research spike deliverable** that precedes a Phase 2 engineering PRD.

---

## 11. Out of Scope — Strategy 3 (Hub-Mediated Registry)

A centralized variant — where the hub records held requests as they pass
through and exposes a `GET /me/reviews` list to the client — would add
cross-device and multi-client (web + SDK + desktop) parity. It is **explicitly
deferred** because it is the heaviest infrastructure change (new hub storage,
aggregator observation of held responses, a host→hub resolution-reporting
channel), introduces a second source of truth to reconcile, and carries a
centralization/privacy cost (the hub would see who holds requests where). It
is recorded here so the phasing is intentional, not accidental. Revisit only
if multi-client parity becomes a hard requirement.

---

## 12. Consolidated Research & Open Questions

| ID | Item | Type | Blocks |
|----|------|------|--------|
| R1 | Does `policy_result` reach non-agent callers, or only the placeholder body? | Research | P0 / non-agent capture |
| R2 | Precise discriminator: manual-review pending vs. transaction/payment pending | Decision | Phase 1 capture |
| R3 | Which component answers a status query (proposed: long-lived `syfthubapi` process) | Research | Phase 2 |
| R4 | Query request type & routing over hub/NATS tunnel | Research | Phase 2 |
| R5 | Auth model: `review_id` capability-only vs. capability + identity binding | Decision | Phase 2 |
| R6 | Response semantics; guarantee rejected content never leaks | Decision (security) | Phase 2 |
| R7 | Capability discovery / SDK version negotiation; graceful degradation | Research | Phase 2 |
| R8 | Offline-host handling in the client poller | Decision | Phase 2 |
| R9 | Uniform channel behavior for `model` / `data_source` endpoints | Research | Phase 2 |
| R10–R13 | Polling cadence, backoff/batching, termination, status precedence | Decision | Phase 2 |
| D1 | Client ledger storage: JSON file vs. local SQLite | Decision | Phase 1 |
| D2 | IA placement of the "Sent for Review" view | Decision | Phase 1 |

---

## 13. Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| `review_id` never surfaced structurally (P0 slips) | Phase 1 entries unreliable; Phase 2 impossible | Land P0 first; degraded text-parse fallback as a stopgap only |
| Phase 1 ships and users read stale `pending` as truth | Misleading UX | Honest copy (§9.8); visibly distinct `manual` provenance |
| Rejected held content leaks via the status channel | Security / trust breach | R6 hard requirement: rejection responses carry no `output` |
| Status channel hammers hosts with polling | Host load, bad citizenship | R10–R11 backoff + batching before GA |
| Older endpoints can't answer queries | Phase 2 silently broken for them | R7 capability detection → graceful Phase-1 degradation |
| Scope creep toward Strategy 3 | Timeline blowout | §11 keeps Strategy 3 explicitly deferred |

---

## 14. Success Metrics

- **Adoption:** % of users who, after receiving a held response, open the
  "Sent for Review" view at least once.
- **Durability (Phase 1):** held requests recorded in the ledger ÷ held
  responses received — target ≈ 100% (minus the no-`review_id` degraded case).
- **Loop closure (Phase 2):** median time from host resolution to the client's
  ledger reflecting it; % of pending entries that ever reach a confirmed
  terminal status.
- **Answer recovery (Phase 2):** % of approved entries whose real response was
  successfully retrieved by the client.

---

## 15. Milestones

1. **M0 — Prerequisite.** Surface `review_id` (P0); resolve R1, R2.
2. **M1 — Phase 1 ships.** Local ledger, capture, "Sent for Review" view,
   manual override. Resolve D1, D2.
3. **M2 — Phase 2 research spike.** Resolve R3–R13; produce a Phase 2
   engineering PRD with a concrete protocol spec.
4. **M3 — Phase 2 ships.** Status query channel, polling, approved-response
   retrieval, capability degradation.

---

## 16. Appendix

### 16.1 Glossary

- **Held request** — a request whose real response was withheld by
  `ManualReviewPolicy` pending a human decision.
- **Placeholder** — the short substitute body the caller receives instead of
  the real response.
- **`review_id`** — the 12-hex identifier of a held request; the durable
  handle and (in Phase 2) the capability token.
- **Ledger** — the client-local store of held requests this feature
  introduces.
- **Resolution** — the host's act of approving or rejecting a held request.

### 16.2 Reference points in the codebase

- Host-side review storage/decoding: `syfthub-desktop/manual_review_operations.go`
- Host-side review UI: `syfthub-desktop/frontend/src/components/tabs/RequestsTab.tsx`
- Client chat event handling: `syfthub-desktop/frontend/src/hooks/use-agent-workflow.ts`
- Client policy notice rendering: `syfthub-desktop/frontend/src/components/chat/policy-notice.tsx`
- Policy behavior: `ManualReviewPolicy` in the `policy-manager` framework
- Agent execution / held-reply construction: `syfthubapi/agent_executor.go`
