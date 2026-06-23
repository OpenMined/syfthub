"""Unit tests for AgentResource and AgentSessionClient."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest
import respx

from syfthub_sdk import SyftHubClient
from syfthub_sdk.agent import (
    AgentConfig,
    AgentHistoryMessage,
    AgentResource,
    AgentSessionClient,
    AgentSessionError,
    AgentSessionOptions,
)
from syfthub_sdk.aggregators import AggregatorsResource
from syfthub_sdk.exceptions import AuthenticationError, SyftHubError
from syfthub_sdk.models import AuthTokens, PeerTokenResponse, SatelliteTokenResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ws(*messages: dict[str, Any]) -> MagicMock:
    ws = MagicMock()
    ws.recv.side_effect = [json.dumps(m) for m in messages]
    return ws


def _sat_resp() -> SatelliteTokenResponse:
    return SatelliteTokenResponse(target_token="sat-tok", expires_in=3600)


def _peer_resp() -> PeerTokenResponse:
    return PeerTokenResponse(
        peer_token="peer-tok",
        peer_channel="channel-abc",
        expires_in=3600,
        nats_url="nats://localhost:4222",
    )


def _make_auth() -> MagicMock:
    auth = MagicMock()
    auth.get_satellite_token.return_value = _sat_resp()
    auth.get_peer_token.return_value = _peer_resp()
    return auth


def _make_resource(aggregator_url: str = "http://agg.example.com/api/v1") -> AgentResource:
    return AgentResource(auth=_make_auth(), aggregator_url=aggregator_url)


def _started_ws(session_id: str = "sess-42") -> MagicMock:
    ws = MagicMock()
    ws.recv.return_value = json.dumps({"type": "session.created", "session_id": session_id})
    return ws


# ---------------------------------------------------------------------------
# AgentSessionError
# ---------------------------------------------------------------------------


class TestAgentSessionError:
    def test_is_syft_hub_error(self) -> None:
        err = AgentSessionError("something went wrong")
        assert isinstance(err, SyftHubError)

    def test_code_stored(self) -> None:
        err = AgentSessionError("msg", code="E42")
        assert err.code == "E42"

    def test_code_defaults_to_none(self) -> None:
        err = AgentSessionError("msg")
        assert err.code is None

    def test_message_preserved(self) -> None:
        err = AgentSessionError("detail here")
        assert "detail here" in str(err)


# ---------------------------------------------------------------------------
# AgentSessionClient — state transitions
# ---------------------------------------------------------------------------


class TestAgentSessionClientState:
    def _session(self, *messages: dict[str, Any]) -> AgentSessionClient:
        return AgentSessionClient(_make_ws(*messages), session_id="sess-1")

    def test_initial_state_is_running(self) -> None:
        session = AgentSessionClient(MagicMock(), session_id="s")
        assert session.state == "running"

    def test_session_id_stored(self) -> None:
        session = AgentSessionClient(MagicMock(), session_id="my-id")
        assert session.session_id == "my-id"

    def test_completed_sets_state_and_stops(self) -> None:
        session = self._session({"type": "session.completed"})
        events = list(session.events())
        assert len(events) == 1
        assert session.state == "completed"

    def test_failed_sets_state_and_stops(self) -> None:
        session = self._session({"type": "session.failed", "payload": {"reason": "boom"}})
        events = list(session.events())
        assert len(events) == 1
        assert session.state == "failed"

    def test_request_input_sets_awaiting_input(self) -> None:
        ws = MagicMock()
        ws.recv.side_effect = [
            json.dumps({"type": "agent.request_input", "payload": {"question": "proceed?"}}),
            json.dumps({"type": "session.completed"}),
        ]
        session = AgentSessionClient(ws, session_id="s")
        events = list(session.events())
        # After agent.request_input the state transitions to awaiting_input,
        # then session.completed drives it to completed.
        assert events[0]["type"] == "agent.request_input"
        assert session.state == "completed"

    def test_nonrecoverable_error_sets_error_state_then_completed(self) -> None:
        session = self._session(
            {"type": "agent.error", "payload": {"recoverable": False, "message": "fatal"}},
            {"type": "session.completed"},
        )
        events = list(session.events())
        assert events[0]["type"] == "agent.error"
        assert session.state == "completed"

    def test_recoverable_error_does_not_set_error_state(self) -> None:
        ws = MagicMock()
        ws.recv.side_effect = [
            json.dumps({"type": "agent.error", "payload": {"recoverable": True}}),
            json.dumps({"type": "session.completed"}),
        ]
        session = AgentSessionClient(ws, session_id="s")
        list(session.events())
        assert session.state == "completed"

    def test_events_yields_all_events_before_terminal(self) -> None:
        session = self._session(
            {"type": "agent.message", "payload": {"content": "Hello"}},
            {"type": "agent.message", "payload": {"content": "World"}},
            {"type": "session.completed"},
        )
        events = list(session.events())
        assert len(events) == 3

    def test_events_skips_invalid_json(self) -> None:
        ws = MagicMock()
        ws.recv.side_effect = ["not-json", json.dumps({"type": "session.completed"})]
        session = AgentSessionClient(ws, session_id="s")
        events = list(session.events())
        assert len(events) == 1
        assert events[0]["type"] == "session.completed"

    def test_events_stops_on_recv_exception(self) -> None:
        ws = MagicMock()
        ws.recv.side_effect = ConnectionError("closed")
        session = AgentSessionClient(ws, session_id="s")
        assert list(session.events()) == []

    def test_events_stops_on_empty_recv(self) -> None:
        ws = MagicMock()
        ws.recv.return_value = ""
        session = AgentSessionClient(ws, session_id="s")
        assert list(session.events()) == []


# ---------------------------------------------------------------------------
# AgentSessionClient — control messages
# ---------------------------------------------------------------------------


class TestAgentSessionClientControls:
    def _session(self) -> tuple[AgentSessionClient, MagicMock]:
        ws = MagicMock()
        return AgentSessionClient(ws, session_id="s"), ws

    def test_send_message(self) -> None:
        session, ws = self._session()
        session.send_message("hello")
        ws.send.assert_called_once_with(
            json.dumps({"type": "user.message", "payload": {"content": "hello"}})
        )

    def test_confirm(self) -> None:
        session, ws = self._session()
        session.confirm("tool-123")
        ws.send.assert_called_once_with(
            json.dumps({"type": "user.confirm", "payload": {"tool_call_id": "tool-123"}})
        )

    def test_deny_without_reason(self) -> None:
        session, ws = self._session()
        session.deny("tool-123")
        sent = json.loads(ws.send.call_args[0][0])
        assert sent["type"] == "user.deny"
        assert sent["payload"]["tool_call_id"] == "tool-123"
        assert "reason" not in sent["payload"]

    def test_deny_with_reason(self) -> None:
        session, ws = self._session()
        session.deny("tool-123", reason="not safe")
        sent = json.loads(ws.send.call_args[0][0])
        assert sent["payload"]["reason"] == "not safe"

    def test_cancel_sets_state_and_sends(self) -> None:
        session, ws = self._session()
        session.cancel()
        assert session.state == "cancelled"
        ws.send.assert_called_once_with(json.dumps({"type": "user.cancel"}))

    def test_close_sends_close_then_closes_ws(self) -> None:
        session, ws = self._session()
        session.close()
        ws.send.assert_called_once_with(json.dumps({"type": "session.close"}))
        ws.close.assert_called_once()

    def test_close_ignores_send_exception(self) -> None:
        session, ws = self._session()
        ws.send.side_effect = OSError("broken pipe")
        session.close()
        ws.close.assert_called_once()

    def test_close_ignores_ws_close_exception(self) -> None:
        session, ws = self._session()
        ws.close.side_effect = OSError("already closed")
        session.close()  # must not raise


# ---------------------------------------------------------------------------
# AgentResource.start_session
# ---------------------------------------------------------------------------


class TestAgentResourceStartSession:
    def test_invalid_endpoint_no_slash_raises(self) -> None:
        resource = _make_resource()
        with patch("syfthub_sdk.agent._ws.create_connection"):
            with pytest.raises(ValueError, match="owner/slug"):
                resource.start_session(AgentSessionOptions(prompt="hi", endpoint="no-slash"))

    def test_returns_agent_session_client(self) -> None:
        resource = _make_resource()
        ws = _started_ws("sess-42")
        with patch("syfthub_sdk.agent._ws.create_connection", return_value=ws):
            session = resource.start_session(
                AgentSessionOptions(prompt="hello", endpoint="alice/bot")
            )
        assert isinstance(session, AgentSessionClient)
        assert session.session_id == "sess-42"

    def test_session_id_from_nested_payload(self) -> None:
        resource = _make_resource()
        ws = MagicMock()
        ws.recv.return_value = json.dumps(
            {"type": "session.created", "payload": {"session_id": "nested-id"}}
        )
        with patch("syfthub_sdk.agent._ws.create_connection", return_value=ws):
            session = resource.start_session(
                AgentSessionOptions(prompt="hi", endpoint="alice/bot")
            )
        assert session.session_id == "nested-id"

    def test_agent_error_response_raises_with_code(self) -> None:
        resource = _make_resource()
        ws = MagicMock()
        ws.recv.return_value = json.dumps(
            {"type": "agent.error", "payload": {"message": "auth failed", "code": "E001"}}
        )
        with patch("syfthub_sdk.agent._ws.create_connection", return_value=ws):
            with pytest.raises(AgentSessionError, match="auth failed") as exc_info:
                resource.start_session(AgentSessionOptions(prompt="hi", endpoint="alice/bot"))
        assert exc_info.value.code == "E001"
        ws.close.assert_called_once()

    def test_agent_error_closes_ws(self) -> None:
        resource = _make_resource()
        ws = MagicMock()
        ws.recv.return_value = json.dumps({"type": "agent.error", "payload": {}})
        with patch("syfthub_sdk.agent._ws.create_connection", return_value=ws):
            with pytest.raises(AgentSessionError):
                resource.start_session(AgentSessionOptions(prompt="hi", endpoint="alice/bot"))
        ws.close.assert_called_once()

    def test_ws_url_converts_http_to_ws(self) -> None:
        resource = _make_resource("http://agg.example.com/api/v1")
        ws = _started_ws()
        with patch("syfthub_sdk.agent._ws.create_connection", return_value=ws) as mock_cc:
            resource.start_session(AgentSessionOptions(prompt="hi", endpoint="alice/bot"))
        mock_cc.assert_called_once_with("ws://agg.example.com/api/v1/agent/session")

    def test_ws_url_converts_https_to_wss(self) -> None:
        resource = _make_resource("https://agg.example.com/api/v1")
        ws = _started_ws()
        with patch("syfthub_sdk.agent._ws.create_connection", return_value=ws) as mock_cc:
            resource.start_session(AgentSessionOptions(prompt="hi", endpoint="alice/bot"))
        mock_cc.assert_called_once_with("wss://agg.example.com/api/v1/agent/session")

    def test_ws_url_uses_override_aggregator_url(self) -> None:
        resource = _make_resource("http://default.example.com/api/v1")
        ws = _started_ws()
        with patch("syfthub_sdk.agent._ws.create_connection", return_value=ws) as mock_cc:
            resource.start_session(
                AgentSessionOptions(
                    prompt="hi",
                    endpoint="alice/bot",
                    aggregator_url="https://custom-agg.example.com/api/v1",
                )
            )
        mock_cc.assert_called_once_with("wss://custom-agg.example.com/api/v1/agent/session")

    def test_session_start_payload_contains_tokens(self) -> None:
        resource = _make_resource()
        ws = _started_ws()
        with patch("syfthub_sdk.agent._ws.create_connection", return_value=ws):
            resource.start_session(AgentSessionOptions(prompt="test prompt", endpoint="alice/bot"))
        sent = json.loads(ws.send.call_args[0][0])
        assert sent["type"] == "session.start"
        payload = sent["payload"]
        assert payload["prompt"] == "test prompt"
        assert payload["satellite_token"] == "sat-tok"
        assert payload["peer_token"] == "peer-tok"
        assert payload["peer_channel"] == "channel-abc"
        assert payload["endpoint"] == {"owner": "alice", "slug": "bot"}

    def test_config_included_when_provided(self) -> None:
        resource = _make_resource()
        ws = _started_ws()
        config = AgentConfig(max_tokens=100, temperature=0.7, system_prompt="Be concise.")
        with patch("syfthub_sdk.agent._ws.create_connection", return_value=ws):
            resource.start_session(
                AgentSessionOptions(prompt="hi", endpoint="alice/bot", config=config)
            )
        payload = json.loads(ws.send.call_args[0][0])["payload"]
        assert payload["config"]["max_tokens"] == 100
        assert payload["config"]["temperature"] == 0.7
        assert payload["config"]["system_prompt"] == "Be concise."

    def test_empty_config_not_included_in_payload(self) -> None:
        resource = _make_resource()
        ws = _started_ws()
        with patch("syfthub_sdk.agent._ws.create_connection", return_value=ws):
            resource.start_session(
                AgentSessionOptions(prompt="hi", endpoint="alice/bot", config=AgentConfig())
            )
        payload = json.loads(ws.send.call_args[0][0])["payload"]
        assert "config" not in payload

    def test_metadata_only_config_included(self) -> None:
        resource = _make_resource()
        ws = _started_ws()
        config = AgentConfig(metadata={"key": "val"})
        with patch("syfthub_sdk.agent._ws.create_connection", return_value=ws):
            resource.start_session(
                AgentSessionOptions(prompt="hi", endpoint="alice/bot", config=config)
            )
        payload = json.loads(ws.send.call_args[0][0])["payload"]
        assert payload["config"]["metadata"] == {"key": "val"}

    def test_history_messages_included(self) -> None:
        resource = _make_resource()
        ws = _started_ws()
        history = [
            AgentHistoryMessage(role="user", content="prev msg"),
            AgentHistoryMessage(role="assistant", content="prev reply"),
        ]
        with patch("syfthub_sdk.agent._ws.create_connection", return_value=ws):
            resource.start_session(
                AgentSessionOptions(prompt="hi", endpoint="alice/bot", messages=history)
            )
        payload = json.loads(ws.send.call_args[0][0])["payload"]
        assert payload["messages"] == [
            {"role": "user", "content": "prev msg"},
            {"role": "assistant", "content": "prev reply"},
        ]

    def test_bad_json_from_server_raises_and_closes(self) -> None:
        resource = _make_resource()
        ws = MagicMock()
        ws.recv.return_value = "not-json"
        with patch("syfthub_sdk.agent._ws.create_connection", return_value=ws):
            with pytest.raises(AgentSessionError, match="parse"):
                resource.start_session(AgentSessionOptions(prompt="hi", endpoint="alice/bot"))
        ws.close.assert_called_once()

    def test_fetches_satellite_token_for_endpoint_owner(self) -> None:
        auth = _make_auth()
        resource = AgentResource(auth=auth, aggregator_url="http://agg.example.com/api/v1")
        ws = _started_ws()
        with patch("syfthub_sdk.agent._ws.create_connection", return_value=ws):
            resource.start_session(AgentSessionOptions(prompt="hi", endpoint="bob/my-bot"))
        auth.get_satellite_token.assert_called_once_with("bob")
        auth.get_peer_token.assert_called_once_with(["bob"])


# ---------------------------------------------------------------------------
# Client properties: agent and aggregators
# ---------------------------------------------------------------------------


class TestClientAgentProperty:
    def test_agent_is_agent_resource(self) -> None:
        client = SyftHubClient(base_url="https://test.syfthub.com")
        assert isinstance(client.agent, AgentResource)

    def test_agent_is_cached(self) -> None:
        client = SyftHubClient(base_url="https://test.syfthub.com")
        assert client.agent is client.agent


class TestClientAggregatorsProperty:
    def test_aggregators_is_aggregators_resource(self) -> None:
        client = SyftHubClient(base_url="https://test.syfthub.com")
        assert isinstance(client.aggregators, AggregatorsResource)

    def test_aggregators_is_cached(self) -> None:
        client = SyftHubClient(base_url="https://test.syfthub.com")
        assert client.aggregators is client.aggregators


# ---------------------------------------------------------------------------
# Client property: accounting auto-init
# ---------------------------------------------------------------------------


class TestClientAccountingAutoInit:
    def test_raises_when_not_authenticated(self) -> None:
        client = SyftHubClient(base_url="https://test.syfthub.com")
        with pytest.raises(AuthenticationError, match="login"):
            _ = client.accounting

    @respx.mock
    def test_auto_inits_when_authenticated(self) -> None:
        base_url = "https://test.syfthub.com"
        respx.get(f"{base_url}/api/v1/users/me/accounting").mock(
            return_value=httpx.Response(
                200,
                json={
                    "email": "alice@example.com",
                    "url": "https://accounting.example.com",
                    "password": "secret",
                },
            )
        )
        client = SyftHubClient(base_url=base_url)
        client._http.set_tokens(AuthTokens(access_token="tok", refresh_token="r"))
        from syfthub_sdk.accounting import AccountingResource

        acct = client.accounting
        assert isinstance(acct, AccountingResource)

    @respx.mock
    def test_accounting_is_cached(self) -> None:
        base_url = "https://test.syfthub.com"
        respx.get(f"{base_url}/api/v1/users/me/accounting").mock(
            return_value=httpx.Response(
                200,
                json={
                    "email": "alice@example.com",
                    "url": "https://accounting.example.com",
                    "password": "secret",
                },
            )
        )
        client = SyftHubClient(base_url=base_url)
        client._http.set_tokens(AuthTokens(access_token="tok", refresh_token="r"))
        assert client.accounting is client.accounting
