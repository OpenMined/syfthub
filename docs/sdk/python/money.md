# Money

[← Python SDK guide](README.md)

Publishers bill in their own currencies and the SDK never converts money. Three things meet here:
a session budget you set, the prepaid wallets some publishers run, and metered sources that charge
per request.

## Session budget

A budget belongs to the session, not to a plan: it caps what every search on this `hub` may spend
together. There is no budget until you set one. A budget is one cap per currency, and a currency
with no cap is not budgeted at all.

```python
hub = syfthub.AsyncHub(budget=1.00)                         # shorthand for {"USD": 1.00}
hub = syfthub.AsyncHub(budget={"USD": 1.00, "IDR": 50000})  # one cap per currency
hub = syfthub.AsyncHub(budget=syfthub.Money.of(5, "EUR"))   # a cap in another currency
```

A number or string caps USD. A `Money` caps its own currency. A mapping caps several currencies
at once; its values may be numbers or `Money`, and a `Money` whose currency differs from its key
raises `ConfigurationError`.

The caps can change at any point in the session. Spend is kept across changes and only a new
`hub` starts from zero.

```python
hub.set_budget({"USD": 2.00})   # replace the caps; what was spent stays
hub.set_budget(None)            # no caps; spend is still recorded

hub.budget.limits               # {"USD": Money(2.00)}
hub.budget.remaining            # per capped currency: cap minus spend
hub.budget.remaining_in("USD")  # one currency; None when it has no cap
hub.spent                       # {"USD": Money(...), "IDR": Money(...)}: every charge, capped or not
```

Pre-flight judges each currency on its own, in plan order: the first paid row whose estimate would
cross its currency's cap, and every paid row in that currency after it, are held behind one
`OverBudget` action per crossed currency. A row billed in a currency with no cap is sent, and its
note says so. Execute records what each Space actually charged, per currency, whether or not that
currency is capped; a metered (MPP) charge counts as soon as it is paid.

## Prepaid wallets

Publishers who bill by prepaid credits (Stripe, Xendit, a managed wallet) expose a wallet per
publisher, rail and currency. Balances and top-ups go straight to the publisher's Space.

```python
wallets = await hub.wallets.list()                       # across the sources seen this session
wallet = await hub.wallets.for_source("erin/trials")      # Wallet | None
await wallet.refresh()                                   # balance, refreshed_at
wallet.bundles, wallet.suggest(shortfall)                # Bundle(name, amount, credits)

invoice = await wallet.top_up("starter")                 # Invoice: id, amount, status, checkout_url
await invoice.refresh()                                  # or
await invoice.wait_paid(timeout=600, poll=5)             # PaymentTimeout if it does not settle
await wallet.invoices()                                  # history
```

A `TopUp` action wraps the same calls: `await action.top_up()` picks the suggested bundle. Nothing
is charged until the user completes the checkout; then pre-flight passes.

`wallet.id` is the publisher's wallet id and the key that groups sources on one wallet; `wallet.key`
is the readable `owner/rail/currency` label. A policy that publishes only its URLs gets the UUID
from them as its id. `list()` and `for_source()` read every balance they return, in parallel, and
stamp `refreshed_at`. Those reads go straight to each wallet's host and are not retried, so a
dead Space costs one connect timeout, a slow one at most `Timeout.lookup` seconds, and leaves
`balance=None`; `wallet.refresh()` keeps the retry policy. `hub.wallets.get(key)` is a lookup of a
wallet already seen, with no request, so its balance is as of `refreshed_at`.

## Metered sources (MPP)

Sources on the `mpp` rail are charged per request through the Machine Payments Protocol. The Space
answers with a 402 challenge; the SDK asks the Hub to sign a credential with the wallet you created
on the Hub, retries with it, and records the charge in `results.cost` and `hub.spent`. Pre-flight
shows these rows as `WILL_ASK_TO_PAY` and counts their price against the cap for their currency.

The Hub wallet itself is created and funded on the Hub, not through the SDK. Without one, or when
it cannot cover the charge, the row comes back `PAYMENT_REQUIRED` with the Hub's code in `error`
(`WALLET_NOT_CONFIGURED`, `INSUFFICIENT_BALANCE`, ...) and `charge` holding the challenge.
