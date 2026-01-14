#!/usr/bin/env python3
"""Simple SyftHub SDK example - minimal code to demonstrate the workflow.

Set environment variables before running:
    export SYFTHUB_URL="https://syfthub.openmined.org"
    export SYFTHUB_ACCOUNTING_URL="https://syftaccounting.centralus.cloudapp.azure.com"
    export SYFTHUB_ACCOUNTING_EMAIL="your@email.com"
    export SYFTHUB_ACCOUNTING_PASSWORD="your-password"
"""

from syfthub_sdk import SyftHubClient

# Configuration - replace with your values
USERNAME = "ionesiotest"
PASSWORD = "password123"
MODEL = "ionesiotest/free-legal-assistant"  # owner/slug format
DATA_SOURCES = ["ionesiotest/general-knowledge"]  # owner/slug format
PROMPT = "How to train a neural network?"


def main() -> None:
    # Initialize client (uses SYFTHUB_URL env var)
    with SyftHubClient() as client:
        # =====================================================================
        # Step 1: Login
        # =====================================================================
        print("Logging in...")
        user = client.auth.login(username=USERNAME, password=PASSWORD)
        print(f"Logged in as: {user.username} ({user.email})")

        # =====================================================================
        # Step 2: RAG Chat Query (using Aggregator)
        # =====================================================================
        print(f"\nQuerying model: {MODEL}")
        print(f"With data sources: {DATA_SOURCES}")
        print(f"Prompt: {PROMPT}\n")

        # The SDK handles resolving owner/slug paths internally
        response = client.chat.complete(
            prompt=PROMPT,
            model=MODEL,
            data_sources=DATA_SOURCES,
            top_k=5,
            max_tokens=1024,
            temperature=0.7,
        )

        print("Response:")
        print("-" * 40)
        print(response.response)
        print("-" * 40)
        print(f"\nSources: {[s.path for s in response.sources]}")
        print(f"Total time: {response.metadata.total_time_ms}ms")

        # Option B: Streaming response (uncomment to use)
        # print("Streaming response:")
        # for event in client.chat.stream(
        #     prompt=PROMPT,
        #     model=MODEL,
        #     data_sources=DATA_SOURCES,
        # ):
        #     if event.type == "token":
        #         print(event.content, end="", flush=True)
        #     elif event.type == "done":
        #         print(f"\n\nTotal time: {event.metadata.total_time_ms}ms")

        # =====================================================================
        # Step 3: Check Accounting Balance
        # =====================================================================
        if client.accounting.is_configured:
            print("\nChecking accounting balance...")
            account = client.accounting.get_user()
            print(f"Balance: {account.balance:.2f} credits")
        else:
            print("\nAccounting not configured (set SYFTHUB_ACCOUNTING_* env vars)")


if __name__ == "__main__":
    main()
