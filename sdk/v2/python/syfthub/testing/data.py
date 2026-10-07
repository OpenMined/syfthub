"""The fake world's data. Endpoint records use the Hub's public shape; policies are exactly what a
Space's publish handler writes. Names, prices and documents are invented; response bodies are not."""
from __future__ import annotations

from ..models import Connection, Endpoint, EndpointType, Health, Policy, PolicyType

BUNDLES = ({"name": "starter", "amount": 5.0}, {"name": "pro", "amount": 20.0})
IDR_BUNDLES = ({"name": "starter", "amount": 75000.0}, {"name": "pro", "amount": 300000.0})


def _conn(url: str) -> tuple[Connection, ...]:
    return (Connection(type="https", config={"url": url, "path": "/api/v1/endpoints/{slug}/query"}),)


def _prepaid(rail: str, price: float, unit: str, wallet_id: str, base: str, *, owner: str | None = None,
             currency: str = "USD") -> Policy:
    cfg = {"price": price, "unit_type": unit, "currency": currency, "wallet_id": wallet_id,
           "bundles": list(IDR_BUNDLES if currency == "IDR" else BUNDLES), "applied_to": ["*"],
           "payment_url": f"{base}/{wallet_id}/invoices", "invoices_url": f"{base}/{wallet_id}/invoices/me",
           "credits_url": f"{base}/{wallet_id}/balance"}
    if owner:
        cfg["wallet_owner"] = owner
    return Policy(type=PolicyType(rail), config=cfg, description=f"{rail}_per_{unit}")


def _ep(name, slug, type_, owner, description, **kw) -> Endpoint:
    return Endpoint(name=name, slug=slug, type=EndpointType(type_), owner_username=owner, description=description, **kw)


def endpoints() -> list[Endpoint]:
    gw = lambda u: f"{u}/api/v1/payments/gateway/wallets"
    return [
        _ep("Oncology Trial Papers", "papers", "data_source", "carol",
            "Indexed phase 2/3 oncology publications, 2018-2026, with adverse-event tables.", tags=("oncology", "trials"),
            stars_count=42, connect=_conn("https://carol.spaces.example"), filterable=("published", "author", "journal"),
            health=Health.HEALTHY),
        _ep("Clinician Notes (de-identified)", "notes", "data_source", "dave",
            "De-identified progress notes from two teaching hospitals.", tags=("clinical",), stars_count=17,
            policies=(_prepaid("xendit", 0.02, "document", "w-dave-xendit-usd", gw("https://dave.spaces.example")),
                      Policy(type=PolicyType.RATE_LIMIT, config={"limit": "60/m", "scope": "per_user", "applied_to": ["*"]})),
            connect=_conn("https://dave.spaces.example"), health=Health.HEALTHY),
        _ep("Radiology Reports (de-identified)", "imaging", "data_source", "dave",
            "Same wallet as dave/notes: one top-up funds both.", tags=("clinical", "imaging"), stars_count=9,
            policies=(_prepaid("xendit", 0.03, "request", "w-dave-xendit-usd", gw("https://dave.spaces.example")),),
            connect=_conn("https://dave.spaces.example"), health=Health.HEALTHY),
        _ep("Indonesian Trial Registry", "id-registry", "data_source", "lena",
            "Billed in IDR: a separate wallet even though the rail is xendit too.", stars_count=6,
            policies=(_prepaid("xendit", 300.0, "request", "w-lena-xendit-idr", gw("https://lena.spaces.example"), currency="IDR"),),
            connect=_conn("https://lena.spaces.example"), health=Health.HEALTHY),
        _ep("Trial Registry Mirror", "trials", "data_source", "erin",
            "Structured registry records with adverse-event tables.", tags=("registry",), stars_count=31,
            policies=(_prepaid("stripe", 0.05, "request", "w-erin-stripe-usd", gw("https://erin.spaces.example")),),
            connect=_conn("https://erin.spaces.example"), filterable=("published",), health=Health.HEALTHY),
        _ep("Consortium Corpus", "shared-corpus", "data_source", "heidi",
            "Shared corpus billed through the consortium's managed wallet.", tags=("consortium",), stars_count=12,
            policies=(_prepaid("cluster", 0.01, "request", "w-consortium-cluster-usd",
                               "https://station.example/api/v1/credits", owner="consortium"),),
            connect=_conn("https://heidi.spaces.example"), health=Health.HEALTHY),
        _ep("Pharmacovigilance Feed", "registry", "data_source", "frank",
            "Adverse-event signal reports; heavily rate limited.", stars_count=5,
            policies=(Policy(type=PolicyType.RATE_LIMIT, config={"limit": "2/m", "scope": "per_user", "applied_to": ["*"]}),),
            connect=_conn("https://frank.spaces.example"), health=Health.HEALTHY),
        _ep("Grace's Archive", "archive", "data_source", "grace",
            "Historical archive. Frequently offline.", stars_count=2,
            connect=_conn("https://grace.spaces.example"), health=Health.UNHEALTHY),
        _ep("Judy's Private Set", "private-set", "data_source", "judy",
            "Allow-listed collaborators only.",
            policies=(Policy(type=PolicyType.ACCESS, config={"allowed_users": ["*@judy-lab.org"], "denied_users": []}),),
            connect=_conn("https://judy.spaces.example"), health=Health.HEALTHY),
        _ep("On-chain Ledger Extracts", "ledger", "data_source", "kim",
            "Pay-per-query over MPP. Experimental rail.", stars_count=3,
            policies=(Policy(type=PolicyType.MPP, config={"price": 0.05, "unit_type": "request", "currency": "USD", "applied_to": ["*"]}),),
            connect=_conn("https://kim.spaces.example"), health=Health.HEALTHY),
        _ep("Trials Assistant", "trials-assistant", "model_data_source", "olga",
            "Answers over Olga's curated trial corpus and returns the passages it used.", tags=("oncology",),
            stars_count=27, connect=_conn("https://olga.spaces.example"), health=Health.HEALTHY),
        _ep("Llama 3 70B", "llama-3", "model", "bob",
            "General model, hosted by Bob. Free.", stars_count=88,
            connect=_conn("https://bob.spaces.example"), health=Health.HEALTHY),
        _ep("Sahabat-AI 8B", "sahabat-ai", "model", "lena",
            "Small bilingual model, hosted by Lena. Billed in IDR from the same wallet as her registry.", stars_count=23,
            policies=(_prepaid("xendit", 300.0, "request", "w-lena-xendit-idr", gw("https://lena.spaces.example"), currency="IDR"),),
            connect=_conn("https://lena.spaces.example"), health=Health.HEALTHY),
        _ep("GPT Mini (metered)", "gpt-mini", "model", "ivan",
            "Small fast model, prepaid per message.", stars_count=23,
            policies=(_prepaid("stripe", 0.02, "request", "w-ivan-stripe-usd", gw("https://ivan.spaces.example")),),
            connect=_conn("https://ivan.spaces.example"), health=Health.HEALTHY),
    ]


COLLECTIVES = {"oncology": ["carol/papers", "erin/trials", "dave/notes"]}

CORPUS = {
    "carol/papers": [
        ("Grade 3+ neutropenia occurred in 41% of the treatment arm versus 18% of controls (phase 3, n=812).", 0.91,
         {"published": "2025-03-14", "author": "R. Chitrakoot", "journal": "Lancet Oncol"}),
        ("Serious adverse events were reported in 23% of patients; most common were febrile neutropenia and diarrhoea.", 0.87,
         {"published": "2024-11-02", "author": "M. Okafor", "journal": "JCO"}),
        ("Treatment discontinuation due to adverse events: 12.4% vs 6.1% (placebo).", 0.80,
         {"published": "2023-06-21", "author": "R. Chitrakoot", "journal": "NEJM"}),
        ("Hepatotoxicity was infrequent (<2%) and reversible on interruption.", 0.62,
         {"published": "2021-09-09", "author": "L. Haddad", "journal": "Ann Oncol"}),
        ("No treatment-related deaths were observed in the phase 3 extension.", 0.55,
         {"published": "2026-01-30", "author": "R. Chitrakoot", "journal": "Lancet Oncol"}),
    ],
    "dave/notes": [
        ("Pt reports persistent nausea since cycle 2; antiemetic switched; tolerating.", 0.78, {"published": "2025-08-01", "ward": "onc-3"}),
        ("Grade 3 diarrhoea day 4 of cycle 1; loperamide started; resolved by day 7.", 0.76, {"published": "2023-11-15", "ward": "onc-2"}),
        ("Neuropathy grade 2 hands/feet, dose reduced 20% per protocol.", 0.74, {"published": "2025-07-19", "ward": "onc-3"}),
        ("Admitted for febrile neutropenia day 9; cultures negative; discharged day 12.", 0.71, {"published": "2024-12-05", "ward": "onc-1"}),
    ],
    "erin/trials": [
        ("NCT0480xxxx: SAE rate 21.7% (drug) vs 14.2% (comparator); 3 deaths adjudicated unrelated.", 0.89,
         {"published": "2025-05-10", "registry": "ClinicalTrials.gov"}),
        ("NCT0512xxxx: dose-limiting toxicities: thrombocytopenia (n=4), rash (n=2).", 0.77,
         {"published": "2024-02-28", "registry": "ClinicalTrials.gov"}),
        ("Registry note: adverse-event coding per MedDRA 24.0.", 0.51, {"published": "2022-10-12", "registry": "EU CTR"}),
    ],
    "olga/trials-assistant": [
        ("Pooled across 9 phase 3 trials, grade ≥3 neutropenia ranged 28-41%; febrile neutropenia 6-12%.", 0.88,
         {"published": "2025-10-01", "author": "O. Lindqvist"}),
        ("Hepatic SAEs were under 2% in all pooled trials.", 0.64, {"published": "2025-10-01", "author": "O. Lindqvist"}),
    ],
    "frank/registry": [
        ("Signal: disproportionate reporting of interstitial lung disease (PRR 3.4) in Q2 2026.", 0.72),
    ],
    "heidi/shared-corpus": [
        ("Consortium pooled analysis: infection-related SAEs 9.8% across 6 phase 3 trials.", 0.83),
        ("Cardiac events were rare (1.1%) but concentrated in patients over 70.", 0.69),
    ],
    "dave/imaging": [
        ("CT chest: new ground-glass opacities bilaterally, c/w drug-induced pneumonitis; oncology informed.", 0.76),
    ],
    "lena/id-registry": [
        ("INA-TR-2031: efek samping serius 19%; neutropenia paling sering.", 0.70),
    ],
    "kim/ledger": [
        ("Ledger extract: 14 settlement events for trial-data access in Q1.", 0.60),
    ],
}

USER = {
    "username": "alice", "email": "alice@example.com",
    "hub_wallet": 1.50,
    "pat": "syft_pat_alice",
    # prepaid balances the user holds, keyed by wallet id (held by each Space / the station)
    "prepaid": {"w-dave-xendit-usd": 0.00, "w-erin-stripe-usd": 1.00, "w-consortium-cluster-usd": 3.00, "w-ivan-stripe-usd": 0.00,
                "w-lena-xendit-idr": 5000.0},
}
