#!/usr/bin/env python3
"""
Test querying both tunneled endpoints (sample-docs + echo-model)
via the NATS tunnel protocol using the SDK.
"""

import asyncio
import json
import random
import string
import uuid

import nats
from syfthub_sdk import SyftHubClient

# ── Config ────────────────────────────────────────────────────────────
SYFTHUB_URL = "https://syfthub-dev.openmined.org"
SERVER_USERNAME = "space_user_m5jlrz"  # our tunneled server

TUNNEL_PROTOCOL = "syfthub-tunnel/v1"


def random_suffix(n: int = 6) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


def tunnel_request(
    slug: str,
    ep_type: str,
    payload: dict,
    reply_to: str,
) -> dict:
    return {
        "protocol": TUNNEL_PROTOCOL,
        "type": "endpoint_request",
        "correlation_id": str(uuid.uuid4()),
        "reply_to": reply_to,
        "endpoint": {"slug": slug, "type": ep_type},
        "payload": payload,
        "timeout_ms": 30_000,
    }


async def main() -> None:
    # ── 1. Register a fresh client user ───────────────────────────────
    suffix = random_suffix()
    client_username = f"test_client_{suffix}"
    client_password = "SyftTest2025!"

    hub = SyftHubClient(base_url=SYFTHUB_URL)
    print(f"Registering client user: {client_username}")
    hub.auth.register(
        username=client_username,
        email=f"{client_username}@openmined.org",
        password=client_password,
        full_name="Test Client",
    )
    print(f"  Authenticated: {hub.is_authenticated}")

    # ── 2. Get NATS credentials + peer token ──────────────────────────
    nats_creds = hub.users.get_nats_credentials()
    print(f"  NATS auth token: {nats_creds.nats_auth_token[:12]}...")

    peer = hub.auth.get_peer_token([SERVER_USERNAME])
    print(f"  Peer channel: {peer.peer_channel}")
    print(f"  Peer token expires in: {peer.expires_in}s")
    print(f"  NATS URL: {peer.nats_url}")

    # ── 3. Connect to NATS via WebSocket ──────────────────────────────
    # Derive the WebSocket URL from the hub URL
    nats_ws_url = SYFTHUB_URL.replace("https://", "wss://").replace(
        "http://", "ws://"
    )
    nats_ws_url = f"{nats_ws_url.rstrip('/')}/nats"
    print(f"\nConnecting to NATS at {nats_ws_url}")

    nc = await nats.connect(
        nats_ws_url,
        token=nats_creds.nats_auth_token,
    )
    print("  Connected to NATS!")

    # ── 4. Subscribe to our peer reply channel ────────────────────────
    responses: dict[str, dict] = {}
    event = asyncio.Event()

    async def on_response(msg: nats.aio.client.Msg) -> None:
        data = json.loads(msg.data.decode())
        corr = data.get("correlation_id", "?")
        responses[corr] = data
        slug = data.get("endpoint_slug", "?")
        status = data.get("status", "?")
        print(f"\n  << Response for [{slug}]: status={status}")
        if len(responses) >= 2:
            event.set()

    reply_subject = f"syfthub.peer.{peer.peer_channel}"
    await nc.subscribe(reply_subject, cb=on_response)
    print(f"  Subscribed to {reply_subject}")

    # ── 5. Publish data source query ──────────────────────────────────
    ds_req = tunnel_request(
        slug="sample-docs",
        ep_type="data_source",
        payload={
            "messages": "What is machine learning?",
            "limit": 5,
            "similarity_threshold": 0.5,
            "include_metadata": True,
        },
        reply_to=peer.peer_channel,
    )
    target_subject = f"syfthub.spaces.{SERVER_USERNAME}"
    await nc.publish(target_subject, json.dumps(ds_req).encode())
    print(f"\n  >> Published DATA_SOURCE request to {target_subject}")
    print(f"     correlation_id: {ds_req['correlation_id'][:8]}...")

    # ── 6. Publish model query ────────────────────────────────────────
    model_req = tunnel_request(
        slug="echo-model",
        ep_type="model",
        payload={
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Hello from the test client!"},
            ],
            "max_tokens": 1024,
            "temperature": 0.7,
        },
        reply_to=peer.peer_channel,
    )
    await nc.publish(target_subject, json.dumps(model_req).encode())
    print(f"  >> Published MODEL request to {target_subject}")
    print(f"     correlation_id: {model_req['correlation_id'][:8]}...")

    # ── 7. Wait for both responses ────────────────────────────────────
    print("\nWaiting for responses (timeout 30s)...")
    try:
        await asyncio.wait_for(event.wait(), timeout=30)
    except asyncio.TimeoutError:
        print("  Timed out waiting for responses!")

    # ── 8. Print results ──────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)

    # Data source response
    ds_resp = responses.get(ds_req["correlation_id"])
    if ds_resp:
        print("\n[DATA SOURCE: sample-docs]")
        print(f"  Status:   {ds_resp.get('status')}")
        payload = ds_resp.get("payload", {})
        refs = payload.get("references", {})
        docs = refs.get("documents", []) if isinstance(refs, dict) else []
        print(f"  Documents returned: {len(docs)}")
        for doc in docs:
            print(f"    - {doc['document_id']}: {doc['content'][:60]}")
        timing = ds_resp.get("timing", {})
        if timing:
            print(f"  Duration: {timing.get('duration_ms')}ms")
    else:
        print("\n[DATA SOURCE: sample-docs] — NO RESPONSE")

    # Model response
    model_resp = responses.get(model_req["correlation_id"])
    if model_resp:
        print("\n[MODEL: echo-model]")
        print(f"  Status:   {model_resp.get('status')}")
        payload = model_resp.get("payload", {})
        summary = payload.get("summary", {})
        message = summary.get("message", {}) if isinstance(summary, dict) else {}
        content = message.get("content", "(empty)")
        print(f"  Response: {content}")
        timing = model_resp.get("timing", {})
        if timing:
            print(f"  Duration: {timing.get('duration_ms')}ms")
    else:
        print("\n[MODEL: echo-model] — NO RESPONSE")

    print("\n" + "=" * 60)
    total = len(responses)
    print(f"{'SUCCESS' if total == 2 else 'PARTIAL'}: {total}/2 responses received")
    print("=" * 60)

    # Cleanup
    await nc.close()
    hub.close()


if __name__ == "__main__":
    asyncio.run(main())
