#!/usr/bin/env python3
"""
Tunnel Client - Sends requests to a tunneled Space via MQ.

This script demonstrates how to send requests to a Space running
in tunneling mode by publishing messages to its queue.

Usage:
    python tunnel_client.py
"""

import json
import time
import uuid

from syfthub_sdk import SyftHubClient

# Configuration
SYFTHUB_URL = "https://syfthub-dev.openmined.org"

# User2 (the client/requester)
CLIENT_USERNAME = "tunnel_client_40enkq"
CLIENT_PASSWORD = "TestPass123!"

# User1 (the tunneled server we're calling)
SERVER_USERNAME = "tunnel_server_77xukh"

# Protocol constants
TUNNEL_PROTOCOL_VERSION = "syfthub-tunnel/v1"


def create_tunnel_request(
    endpoint_slug: str,
    endpoint_type: str,
    payload: dict,
    reply_to: str,
    correlation_id: str | None = None,
    timeout_ms: int = 30000
) -> str:
    """Create a tunnel protocol request message."""
    if correlation_id is None:
        correlation_id = str(uuid.uuid4())

    request = {
        "protocol": TUNNEL_PROTOCOL_VERSION,
        "type": "endpoint_request",
        "correlation_id": correlation_id,
        "reply_to": reply_to,
        "endpoint": {
            "slug": endpoint_slug,
            "type": endpoint_type
        },
        "payload": payload,
        "timeout_ms": timeout_ms
    }

    return json.dumps(request)


def main():
    print("\n" + "=" * 60)
    print("TUNNEL CLIENT - Sending requests to tunneled Space")
    print("=" * 60)

    # Authenticate as user2 (the client)
    print(f"\nAuthenticating as {CLIENT_USERNAME}...")
    client = SyftHubClient(base_url=SYFTHUB_URL)
    user = client.auth.login(username=CLIENT_USERNAME, password=CLIENT_PASSWORD)
    print(f"Authenticated as: {user.username} (id={user.id})")

    # First, clear any old messages from our queue
    print("\nClearing any old messages from our queue...")
    cleared = client.mq.clear()
    print(f"Cleared {cleared.cleared} messages")

    # Test 1: Send a DATA_SOURCE request
    print("\n" + "-" * 60)
    print("TEST 1: Sending DATA_SOURCE request to 'sample-docs' endpoint")
    print("-" * 60)

    ds_correlation_id = str(uuid.uuid4())
    ds_request = create_tunnel_request(
        endpoint_slug="sample-docs",
        endpoint_type="data_source",
        payload={
            "messages": "What is machine learning?",
            "limit": 5,
            "similarity_threshold": 0.5,
            "include_metadata": True
        },
        reply_to=CLIENT_USERNAME,
        correlation_id=ds_correlation_id
    )

    print(f"Publishing request to {SERVER_USERNAME}'s queue...")
    print(f"Correlation ID: {ds_correlation_id[:8]}...")
    result = client.mq.publish(target_username=SERVER_USERNAME, message=ds_request)
    print(f"Published! Queue length: {result.queue_length}")

    # Test 2: Send a MODEL request
    print("\n" + "-" * 60)
    print("TEST 2: Sending MODEL request to 'echo-model' endpoint")
    print("-" * 60)

    model_correlation_id = str(uuid.uuid4())
    model_request = create_tunnel_request(
        endpoint_slug="echo-model",
        endpoint_type="model",
        payload={
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Hello from the tunnel client!"}
            ],
            "max_tokens": 1024,
            "temperature": 0.7
        },
        reply_to=CLIENT_USERNAME,
        correlation_id=model_correlation_id
    )

    print(f"Publishing request to {SERVER_USERNAME}'s queue...")
    print(f"Correlation ID: {model_correlation_id[:8]}...")
    result = client.mq.publish(target_username=SERVER_USERNAME, message=model_request)
    print(f"Published! Queue length: {result.queue_length}")

    # Wait for responses
    print("\n" + "-" * 60)
    print("Waiting for responses...")
    print("-" * 60)

    expected_responses = {ds_correlation_id, model_correlation_id}
    received_responses = {}
    max_wait_seconds = 30
    poll_interval = 1

    start_time = time.time()
    while len(received_responses) < len(expected_responses):
        elapsed = time.time() - start_time
        if elapsed > max_wait_seconds:
            print(f"\nTimeout after {max_wait_seconds}s waiting for responses")
            break

        # Check queue status
        status = client.mq.status()
        print(f"\n[{elapsed:.1f}s] Queue has {status.queue_length} messages")

        if status.queue_length > 0:
            # Consume messages
            response = client.mq.consume(limit=10)
            print(f"Consumed {len(response.messages)} messages")

            for msg in response.messages:
                print(f"\n  Message from: {msg.from_username}")
                print(f"  Queued at: {msg.queued_at}")

                try:
                    data = json.loads(msg.message)
                    if data.get("type") == "endpoint_response":
                        corr_id = data.get("correlation_id")
                        print(f"  Type: endpoint_response")
                        print(f"  Correlation ID: {corr_id[:8]}...")
                        print(f"  Status: {data.get('status')}")
                        print(f"  Endpoint: {data.get('endpoint_slug')}")

                        if data.get("status") == "success":
                            payload = data.get("payload", {})
                            print(f"  Payload keys: {list(payload.keys())}")

                            # Show relevant data based on type
                            references = payload.get("references")
                            summary = payload.get("summary")

                            # Data source responses have references with documents
                            if references and isinstance(references, dict):
                                docs = references.get("documents", [])
                                print(f"  Documents returned: {len(docs)}")
                                for i, doc in enumerate(docs[:2]):  # Show first 2
                                    print(f"    [{i}] {doc.get('document_id')}: {doc.get('content', '')[:50]}...")

                            # Model responses have summary with message
                            if summary and isinstance(summary, dict):
                                message = summary.get("message") or {}
                                msg_content = message.get("content", "") or ""
                                print(f"  Model response: {msg_content[:100] if msg_content else '(empty)'}...")
                        else:
                            error = data.get("error", {})
                            print(f"  Error: {error.get('code')}: {error.get('message')}")

                        if data.get("timing"):
                            print(f"  Duration: {data['timing'].get('duration_ms')}ms")

                        received_responses[corr_id] = data
                    else:
                        print(f"  Unknown message type: {data.get('type')}")
                except json.JSONDecodeError:
                    print(f"  Non-JSON message: {msg.message[:50]}...")

        time.sleep(poll_interval)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Expected responses: {len(expected_responses)}")
    print(f"Received responses: {len(received_responses)}")

    for corr_id in expected_responses:
        if corr_id in received_responses:
            resp = received_responses[corr_id]
            print(f"  [{corr_id[:8]}...] {resp.get('endpoint_slug')}: {resp.get('status')}")
        else:
            print(f"  [{corr_id[:8]}...] NOT RECEIVED")

    if len(received_responses) == len(expected_responses):
        print("\nSUCCESS: All responses received!")
    else:
        print("\nWARNING: Some responses were not received")


if __name__ == "__main__":
    main()
