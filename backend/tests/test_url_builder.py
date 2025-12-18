"""Tests for URL builder utility."""

from syfthub.core.url_builder import (
    CONNECTION_PROTOCOL_MAP,
    build_connection_url,
    get_first_enabled_connection,
    get_protocol_for_connection_type,
    transform_connection_urls,
)


class TestGetProtocolForConnectionType:
    """Tests for get_protocol_for_connection_type function."""

    def test_rest_api_returns_https(self):
        """Test that rest_api connection type returns https."""
        assert get_protocol_for_connection_type("rest_api") == "https"

    def test_http_returns_https(self):
        """Test that http connection type returns https."""
        assert get_protocol_for_connection_type("http") == "https"

    def test_websocket_returns_wss(self):
        """Test that websocket connection type returns wss."""
        assert get_protocol_for_connection_type("websocket") == "wss"

    def test_ws_returns_ws(self):
        """Test that ws connection type returns ws."""
        assert get_protocol_for_connection_type("ws") == "ws"

    def test_graphql_returns_https(self):
        """Test that graphql connection type returns https."""
        assert get_protocol_for_connection_type("graphql") == "https"

    def test_grpc_returns_https(self):
        """Test that grpc connection type returns https."""
        assert get_protocol_for_connection_type("grpc") == "https"

    def test_unknown_type_defaults_to_https(self):
        """Test that unknown connection types default to https."""
        assert get_protocol_for_connection_type("unknown") == "https"

    def test_case_insensitive(self):
        """Test that connection type lookup is case insensitive."""
        assert get_protocol_for_connection_type("REST_API") == "https"
        assert get_protocol_for_connection_type("WebSocket") == "wss"


class TestBuildConnectionUrl:
    """Tests for build_connection_url function."""

    def test_build_url_with_domain_and_path(self):
        """Test building URL with domain and path."""
        result = build_connection_url("api.example.com", "rest_api", "v1/endpoint")
        assert result == "https://api.example.com/v1/endpoint"

    def test_build_url_with_domain_only(self):
        """Test building URL with domain but no path."""
        result = build_connection_url("api.example.com", "rest_api", "")
        assert result == "https://api.example.com"

    def test_build_url_with_none_path(self):
        """Test building URL with None path."""
        result = build_connection_url("api.example.com", "rest_api", None)
        assert result == "https://api.example.com"

    def test_build_url_with_leading_slash_in_path(self):
        """Test that leading slashes are normalized."""
        result = build_connection_url("api.example.com", "rest_api", "/v1/endpoint")
        assert result == "https://api.example.com/v1/endpoint"

    def test_build_url_with_multiple_leading_slashes(self):
        """Test that multiple leading slashes are normalized."""
        result = build_connection_url("api.example.com", "rest_api", "///v1/endpoint")
        assert result == "https://api.example.com/v1/endpoint"

    def test_build_url_with_websocket_protocol(self):
        """Test building URL with websocket protocol."""
        result = build_connection_url("ws.example.com", "websocket", "socket")
        assert result == "wss://ws.example.com/socket"

    def test_build_url_with_port(self):
        """Test building URL with port in domain."""
        result = build_connection_url("api.example.com:8080", "rest_api", "v1")
        assert result == "https://api.example.com:8080/v1"

    def test_build_url_returns_none_for_no_domain(self):
        """Test that None is returned when domain is None."""
        result = build_connection_url(None, "rest_api", "v1")
        assert result is None

    def test_build_url_returns_none_for_empty_domain(self):
        """Test that None is returned when domain is empty."""
        result = build_connection_url("", "rest_api", "v1")
        assert result is None


class TestTransformConnectionUrls:
    """Tests for transform_connection_urls function."""

    def test_transform_single_connection(self):
        """Test transforming a single connection."""
        connections = [
            {
                "type": "rest_api",
                "enabled": True,
                "config": {"url": "v1/api"},
            }
        ]
        result = transform_connection_urls("api.example.com", connections)
        assert len(result) == 1
        assert result[0]["config"]["url"] == "https://api.example.com/v1/api"

    def test_transform_multiple_connections(self):
        """Test transforming multiple connections."""
        connections = [
            {"type": "rest_api", "enabled": True, "config": {"url": "v1"}},
            {"type": "websocket", "enabled": True, "config": {"url": "ws"}},
        ]
        result = transform_connection_urls("api.example.com", connections)
        assert len(result) == 2
        assert result[0]["config"]["url"] == "https://api.example.com/v1"
        assert result[1]["config"]["url"] == "wss://api.example.com/ws"

    def test_transform_preserves_other_fields(self):
        """Test that transformation preserves other connection fields."""
        connections = [
            {
                "type": "rest_api",
                "enabled": True,
                "description": "Main API",
                "config": {"url": "v1", "timeout": 30},
            }
        ]
        result = transform_connection_urls("api.example.com", connections)
        assert result[0]["description"] == "Main API"
        assert result[0]["config"]["timeout"] == 30

    def test_transform_returns_original_when_no_domain(self):
        """Test that original connections are returned when no domain."""
        connections = [{"type": "rest_api", "enabled": True, "config": {"url": "v1"}}]
        result = transform_connection_urls(None, connections)
        assert result == connections
        assert result[0]["config"]["url"] == "v1"

    def test_transform_does_not_mutate_original(self):
        """Test that transformation does not mutate original connections."""
        connections = [{"type": "rest_api", "enabled": True, "config": {"url": "v1"}}]
        result = transform_connection_urls("api.example.com", connections)
        # Original should be unchanged
        assert connections[0]["config"]["url"] == "v1"
        # Result should have transformed URL
        assert result[0]["config"]["url"] == "https://api.example.com/v1"

    def test_transform_empty_connections(self):
        """Test transforming empty connections list."""
        result = transform_connection_urls("api.example.com", [])
        assert result == []


class TestGetFirstEnabledConnection:
    """Tests for get_first_enabled_connection function."""

    def test_returns_first_enabled(self):
        """Test that first enabled connection is returned."""
        connections = [
            {"type": "rest_api", "enabled": True, "config": {"url": "v1"}},
            {"type": "websocket", "enabled": True, "config": {"url": "ws"}},
        ]
        result = get_first_enabled_connection(connections)
        assert result["type"] == "rest_api"

    def test_skips_disabled_connections(self):
        """Test that disabled connections are skipped."""
        connections = [
            {"type": "rest_api", "enabled": False, "config": {"url": "v1"}},
            {"type": "websocket", "enabled": True, "config": {"url": "ws"}},
        ]
        result = get_first_enabled_connection(connections)
        assert result["type"] == "websocket"

    def test_defaults_to_enabled_when_not_specified(self):
        """Test that connections default to enabled when not specified."""
        connections = [
            {"type": "rest_api", "config": {"url": "v1"}},  # No enabled field
        ]
        result = get_first_enabled_connection(connections)
        assert result["type"] == "rest_api"

    def test_fallback_to_first_when_none_enabled(self):
        """Test fallback to first connection when none are enabled."""
        connections = [
            {"type": "rest_api", "enabled": False, "config": {"url": "v1"}},
            {"type": "websocket", "enabled": False, "config": {"url": "ws"}},
        ]
        result = get_first_enabled_connection(connections)
        assert result["type"] == "rest_api"

    def test_returns_none_for_empty_list(self):
        """Test that None is returned for empty list."""
        result = get_first_enabled_connection([])
        assert result is None


class TestConnectionProtocolMap:
    """Tests for CONNECTION_PROTOCOL_MAP constant."""

    def test_all_expected_types_present(self):
        """Test that all expected connection types are in the map."""
        expected_types = [
            "rest_api",
            "http",
            "https",
            "graphql",
            "websocket",
            "ws",
            "wss",
            "grpc",
            "database",
            "s3",
            "storage",
        ]
        for conn_type in expected_types:
            assert conn_type in CONNECTION_PROTOCOL_MAP

    def test_all_protocols_are_valid(self):
        """Test that all protocols in the map are valid schemes."""
        valid_protocols = {"http", "https", "ws", "wss"}
        for protocol in CONNECTION_PROTOCOL_MAP.values():
            assert protocol in valid_protocols
