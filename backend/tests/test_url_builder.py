"""Tests for URL builder utility."""

from syfthub.core.url_builder import (
    build_connection_url,
    get_first_enabled_connection,
    normalize_domain,
    transform_connection_urls,
)


class TestNormalizeDomain:
    """Tests for normalize_domain function."""

    def test_domain_with_https_preserved(self):
        """Test that domain with https protocol is preserved."""
        assert normalize_domain("https://api.example.com") == "https://api.example.com"

    def test_domain_with_http_preserved(self):
        """Test that domain with http protocol is preserved."""
        assert normalize_domain("http://api.example.com") == "http://api.example.com"

    def test_strips_trailing_slashes(self):
        """Test that trailing slashes are stripped."""
        assert normalize_domain("https://api.example.com/") == "https://api.example.com"
        assert (
            normalize_domain("https://api.example.com///") == "https://api.example.com"
        )

    def test_preserves_port(self):
        """Test that port number is preserved."""
        assert (
            normalize_domain("https://api.example.com:8080/")
            == "https://api.example.com:8080"
        )

    def test_handles_ngrok_url(self):
        """Test ngrok URL normalization."""
        domain = "https://tertius-unconstricted-jayceon.ngrok-free.dev/"
        assert (
            normalize_domain(domain)
            == "https://tertius-unconstricted-jayceon.ngrok-free.dev"
        )

    def test_strips_whitespace(self):
        """Test that leading/trailing whitespace is stripped."""
        assert (
            normalize_domain("  https://api.example.com  ") == "https://api.example.com"
        )
        assert (
            normalize_domain("  https://api.example.com/  ")
            == "https://api.example.com"
        )


class TestBuildConnectionUrl:
    """Tests for build_connection_url function."""

    def test_build_url_with_https_domain_and_path(self):
        """Test building URL with https domain and path."""
        result = build_connection_url(
            "https://api.example.com", "rest_api", "v1/endpoint"
        )
        assert result == "https://api.example.com/v1/endpoint"

    def test_build_url_preserves_http_protocol(self):
        """Test building URL preserves http:// protocol."""
        result = build_connection_url(
            "http://api.example.com", "rest_api", "v1/endpoint"
        )
        assert result == "http://api.example.com/v1/endpoint"

    def test_build_url_with_domain_only(self):
        """Test building URL with domain but no path."""
        result = build_connection_url("https://api.example.com", "rest_api", "")
        assert result == "https://api.example.com"

    def test_build_url_with_none_path(self):
        """Test building URL with None path."""
        result = build_connection_url("https://api.example.com", "rest_api", None)
        assert result == "https://api.example.com"

    def test_build_url_with_leading_slash_in_path(self):
        """Test that leading slashes are normalized."""
        result = build_connection_url(
            "https://api.example.com", "rest_api", "/v1/endpoint"
        )
        assert result == "https://api.example.com/v1/endpoint"

    def test_build_url_with_multiple_leading_slashes(self):
        """Test that multiple leading slashes are normalized."""
        result = build_connection_url(
            "https://api.example.com", "rest_api", "///v1/endpoint"
        )
        assert result == "https://api.example.com/v1/endpoint"

    def test_build_url_websocket_upgrades_https_to_wss(self):
        """Test building URL upgrades https to wss for websocket type."""
        result = build_connection_url("https://ws.example.com", "websocket", "socket")
        assert result == "wss://ws.example.com/socket"

    def test_build_url_websocket_upgrades_http_to_ws(self):
        """Test building URL upgrades http to ws for websocket type."""
        result = build_connection_url("http://ws.example.com", "websocket", "socket")
        assert result == "ws://ws.example.com/socket"

    def test_build_url_with_https_port(self):
        """Test building URL with port in domain."""
        result = build_connection_url("https://api.example.com:8080", "rest_api", "v1")
        assert result == "https://api.example.com:8080/v1"

    def test_build_url_with_http_port(self):
        """Test building URL with http and port."""
        result = build_connection_url("http://192.168.1.1:8080", "rest_api", "v1")
        assert result == "http://192.168.1.1:8080/v1"

    def test_build_url_returns_none_for_no_domain(self):
        """Test that None is returned when domain is None."""
        result = build_connection_url(None, "rest_api", "v1")
        assert result is None

    def test_build_url_returns_none_for_empty_domain(self):
        """Test that None is returned when domain is empty."""
        result = build_connection_url("", "rest_api", "v1")
        assert result is None

    def test_build_url_strips_trailing_slash_from_domain(self):
        """Test that trailing slash in domain is handled."""
        result = build_connection_url("https://api.example.com/", "rest_api", "v1")
        assert result == "https://api.example.com/v1"

    def test_build_url_handles_ngrok_url(self):
        """Test the ngrok URL case."""
        domain = "https://tertius-unconstricted-jayceon.ngrok-free.dev/"
        result = build_connection_url(domain, "https", "/api/v1/endpoints/test/query")
        expected = "https://tertius-unconstricted-jayceon.ngrok-free.dev/api/v1/endpoints/test/query"
        assert result == expected

    def test_build_url_ws_connection_type(self):
        """Test ws connection type upgrades http to ws."""
        result = build_connection_url("http://example.com", "ws", "path")
        assert result == "ws://example.com/path"

    def test_build_url_wss_connection_type(self):
        """Test wss connection type upgrades https to wss."""
        result = build_connection_url("https://example.com", "wss", "path")
        assert result == "wss://example.com/path"

    def test_build_url_defaults_to_https_when_no_protocol(self):
        """Test that bare domain defaults to https:// protocol."""
        result = build_connection_url("api.example.com", "rest_api", "v1")
        assert result == "https://api.example.com/v1"

    def test_build_url_bare_domain_with_port_defaults_to_https(self):
        """Test that bare domain with port defaults to https://."""
        result = build_connection_url("192.168.1.1:8080", "rest_api", "v1")
        assert result == "https://192.168.1.1:8080/v1"

    def test_build_url_bare_domain_websocket_defaults_to_wss(self):
        """Test that bare domain with websocket type gets wss://."""
        result = build_connection_url("ws.example.com", "websocket", "socket")
        assert result == "wss://ws.example.com/socket"


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
        result = transform_connection_urls("https://api.example.com", connections)
        assert len(result) == 1
        assert result[0]["config"]["url"] == "https://api.example.com/v1/api"

    def test_transform_multiple_connections(self):
        """Test transforming multiple connections."""
        connections = [
            {"type": "rest_api", "enabled": True, "config": {"url": "v1"}},
            {"type": "websocket", "enabled": True, "config": {"url": "ws"}},
        ]
        result = transform_connection_urls("https://api.example.com", connections)
        assert len(result) == 2
        assert result[0]["config"]["url"] == "https://api.example.com/v1"
        assert result[1]["config"]["url"] == "wss://api.example.com/ws"

    def test_transform_http_domain_with_websocket(self):
        """Test transforming http domain with websocket connection."""
        connections = [
            {"type": "rest_api", "enabled": True, "config": {"url": "v1"}},
            {"type": "websocket", "enabled": True, "config": {"url": "ws"}},
        ]
        result = transform_connection_urls("http://api.example.com", connections)
        assert result[0]["config"]["url"] == "http://api.example.com/v1"
        assert result[1]["config"]["url"] == "ws://api.example.com/ws"

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
        result = transform_connection_urls("https://api.example.com", connections)
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
        result = transform_connection_urls("https://api.example.com", connections)
        # Original should be unchanged
        assert connections[0]["config"]["url"] == "v1"
        # Result should have transformed URL
        assert result[0]["config"]["url"] == "https://api.example.com/v1"

    def test_transform_empty_connections(self):
        """Test transforming empty connections list."""
        result = transform_connection_urls("https://api.example.com", [])
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
