"""Integration tests for MQResource.

These tests require a running backend with Redis.
Run with: uv run pytest tests/integration/test_mq.py -v
"""

from __future__ import annotations

import json

import pytest

from syfthub_sdk import SyftHubClient
from syfthub_sdk.mq import (
    ConsumeResponse,
    PublishResponse,
    QueueStatusResponse,
    ReleaseQueueResponse,
    ReserveQueueResponse,
)


@pytest.fixture
def authenticated_client(test_client: SyftHubClient) -> SyftHubClient:
    """Return an authenticated client."""
    return test_client


# =============================================================================
# Basic MQ Operations Tests
# =============================================================================


@pytest.mark.integration
class TestMQBasicOperations:
    """Test basic MQ operations."""

    def test_publish_and_consume_roundtrip(self, authenticated_client: SyftHubClient):
        """Test publishing a message and consuming it."""
        client = authenticated_client
        username = client.users.me().username

        # Clear any existing messages first
        client.mq.clear()

        # Publish a message to ourselves
        test_message = json.dumps({"type": "test", "data": "hello"})
        publish_result = client.mq.publish(
            target_username=username,
            message=test_message,
        )

        assert isinstance(publish_result, PublishResponse)
        assert publish_result.status == "ok"
        assert publish_result.target_username == username
        assert publish_result.queue_length >= 1

        # Consume the message
        consume_result = client.mq.consume(limit=10)

        assert isinstance(consume_result, ConsumeResponse)
        assert len(consume_result.messages) >= 1

        # Find our message
        found = False
        for msg in consume_result.messages:
            if msg.message == test_message:
                found = True
                assert msg.from_username == username
                break

        assert found, "Published message not found in consumed messages"

    def test_queue_status(self, authenticated_client: SyftHubClient):
        """Test getting queue status."""
        client = authenticated_client

        result = client.mq.status()

        assert isinstance(result, QueueStatusResponse)
        assert result.queue_length >= 0
        assert result.username == client.users.me().username

    def test_peek_messages(self, authenticated_client: SyftHubClient):
        """Test peeking at messages without consuming."""
        client = authenticated_client
        username = client.users.me().username

        # Clear and add a message
        client.mq.clear()
        client.mq.publish(target_username=username, message="peek test")

        # Peek at messages
        peek_result = client.mq.peek(limit=5)
        initial_total = peek_result.total

        # Peek again - count should be same (messages not consumed)
        peek_result2 = client.mq.peek(limit=5)

        assert peek_result2.total == initial_total

        # Clean up
        client.mq.clear()

    def test_clear_queue(self, authenticated_client: SyftHubClient):
        """Test clearing the queue."""
        client = authenticated_client
        username = client.users.me().username

        # Add some messages
        for i in range(3):
            client.mq.publish(target_username=username, message=f"clear test {i}")

        # Verify we have messages
        status = client.mq.status()
        assert status.queue_length >= 3

        # Clear the queue
        clear_result = client.mq.clear()
        assert clear_result.status == "ok"
        assert clear_result.cleared >= 3

        # Verify queue is empty
        status = client.mq.status()
        assert status.queue_length == 0


# =============================================================================
# Reserved Queue Tests
# =============================================================================


@pytest.mark.integration
class TestReservedQueues:
    """Test reserved queue operations."""

    def test_reserve_queue(self, authenticated_client: SyftHubClient):
        """Test reserving an ephemeral queue."""
        client = authenticated_client

        result = client.mq.reserve_queue(ttl=60)

        assert isinstance(result, ReserveQueueResponse)
        assert result.queue_id.startswith("rq_")
        assert len(result.token) > 0
        assert result.ttl == 60

        # Clean up
        client.mq.release_queue(queue_id=result.queue_id, token=result.token)

    def test_reserve_queue_default_ttl(self, authenticated_client: SyftHubClient):
        """Test reserving a queue with default TTL."""
        client = authenticated_client

        result = client.mq.reserve_queue()

        assert result.ttl == 300  # Default TTL

        # Clean up
        client.mq.release_queue(queue_id=result.queue_id, token=result.token)

    def test_publish_to_reserved_queue(self, authenticated_client: SyftHubClient):
        """Test publishing to a reserved queue using rq_ prefix."""
        client = authenticated_client

        # Reserve a queue
        queue = client.mq.reserve_queue(ttl=60)

        # Publish to the reserved queue (auto-detected by rq_ prefix)
        publish_result = client.mq.publish(
            target_username=queue.queue_id,  # Uses queue_id as target
            message='{"type": "response", "data": "test"}',
        )

        assert publish_result.status == "ok"
        assert publish_result.target_username == queue.queue_id

        # Clean up
        client.mq.release_queue(queue_id=queue.queue_id, token=queue.token)

    def test_consume_from_reserved_queue(self, authenticated_client: SyftHubClient):
        """Test consuming from a reserved queue."""
        client = authenticated_client

        # Reserve a queue
        queue = client.mq.reserve_queue(ttl=60)

        # Publish to the reserved queue
        test_message = '{"type": "test_response"}'
        client.mq.publish(
            target_username=queue.queue_id,
            message=test_message,
        )

        # Consume from the reserved queue using queue_id and token
        consume_result = client.mq.consume(
            queue_id=queue.queue_id,
            token=queue.token,
            limit=10,
        )

        assert isinstance(consume_result, ConsumeResponse)
        assert len(consume_result.messages) == 1
        assert consume_result.messages[0].message == test_message

        # Clean up
        client.mq.release_queue(queue_id=queue.queue_id, token=queue.token)

    def test_release_queue(self, authenticated_client: SyftHubClient):
        """Test releasing a reserved queue."""
        client = authenticated_client

        # Reserve a queue
        queue = client.mq.reserve_queue(ttl=60)

        # Add a message
        client.mq.publish(
            target_username=queue.queue_id,
            message="to be cleared",
        )

        # Release the queue
        release_result = client.mq.release_queue(
            queue_id=queue.queue_id,
            token=queue.token,
        )

        assert isinstance(release_result, ReleaseQueueResponse)
        assert release_result.queue_id == queue.queue_id
        assert release_result.messages_cleared == 1

    def test_consume_reserved_queue_wrong_token(
        self, authenticated_client: SyftHubClient
    ):
        """Test that consuming with wrong token fails."""
        from syfthub_sdk.exceptions import AuthorizationError

        client = authenticated_client

        # Reserve a queue
        queue = client.mq.reserve_queue(ttl=60)

        try:
            # Try to consume with wrong token
            with pytest.raises(AuthorizationError):
                client.mq.consume(
                    queue_id=queue.queue_id,
                    token="wrong_token",
                    limit=10,
                )
        finally:
            # Clean up
            client.mq.release_queue(queue_id=queue.queue_id, token=queue.token)

    def test_release_queue_wrong_token(self, authenticated_client: SyftHubClient):
        """Test that releasing with wrong token fails."""
        from syfthub_sdk.exceptions import AuthorizationError

        client = authenticated_client

        # Reserve a queue
        queue = client.mq.reserve_queue(ttl=60)

        try:
            # Try to release with wrong token
            with pytest.raises(AuthorizationError):
                client.mq.release_queue(
                    queue_id=queue.queue_id,
                    token="wrong_token",
                )
        finally:
            # Clean up with correct token
            client.mq.release_queue(queue_id=queue.queue_id, token=queue.token)


# =============================================================================
# Tunneling Workflow Simulation Tests
# =============================================================================


@pytest.mark.integration
class TestTunnelingWorkflow:
    """Test the full tunneling workflow."""

    def test_tunneling_simulation(self, authenticated_client: SyftHubClient):
        """Simulate a tunneling request/response workflow.

        This simulates what happens when:
        1. Client (aggregator) reserves a response queue
        2. Client publishes request to endpoint owner's queue
        3. Endpoint owner consumes request
        4. Endpoint owner publishes response to the reserved queue
        5. Client consumes response from reserved queue
        """
        client = authenticated_client
        owner_username = client.users.me().username

        # Step 1: Client reserves a response queue
        response_queue = client.mq.reserve_queue(ttl=60)

        # Step 2: Client publishes request to endpoint owner's queue
        request_message = json.dumps(
            {
                "protocol": "syfthub-tunnel/v1",
                "type": "endpoint_request",
                "correlation_id": "test-correlation-123",
                "reply_to": response_queue.queue_id,
                "endpoint": {"slug": "test-endpoint", "type": "data_source"},
                "payload": {"query": "What is the answer?"},
            }
        )

        # Clear owner's queue first
        client.mq.clear()

        # Publish to owner's queue
        client.mq.publish(
            target_username=owner_username,
            message=request_message,
        )

        # Step 3: Endpoint owner consumes request from their queue
        request_response = client.mq.consume(limit=10)
        assert len(request_response.messages) >= 1

        # Find the request
        request_data = None
        for msg in request_response.messages:
            try:
                data = json.loads(msg.message)
                if data.get("correlation_id") == "test-correlation-123":
                    request_data = data
                    break
            except json.JSONDecodeError:
                continue

        assert request_data is not None
        assert request_data["type"] == "endpoint_request"
        reply_to_queue = request_data["reply_to"]

        # Step 4: Endpoint owner publishes response to the reserved queue
        response_message = json.dumps(
            {
                "protocol": "syfthub-tunnel/v1",
                "type": "endpoint_response",
                "correlation_id": "test-correlation-123",
                "status": "success",
                "payload": {
                    "references": {
                        "documents": [
                            {"content": "The answer is 42", "similarity_score": 0.95}
                        ]
                    }
                },
            }
        )

        client.mq.publish(
            target_username=reply_to_queue,  # rq_ prefix auto-detected
            message=response_message,
        )

        # Step 5: Client consumes response from reserved queue
        response_result = client.mq.consume(
            queue_id=response_queue.queue_id,
            token=response_queue.token,
            limit=10,
        )

        assert len(response_result.messages) == 1
        response_data = json.loads(response_result.messages[0].message)
        assert response_data["type"] == "endpoint_response"
        assert response_data["correlation_id"] == "test-correlation-123"
        assert response_data["status"] == "success"

        # Clean up
        client.mq.release_queue(
            queue_id=response_queue.queue_id,
            token=response_queue.token,
        )
