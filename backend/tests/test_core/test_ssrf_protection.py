"""Tests for the SSRF protection module."""

import ipaddress
from unittest.mock import patch, MagicMock
import socket

import pytest
from fastapi import HTTPException

from syfthub.core.ssrf_protection import (
    BLOCKED_IP_NETWORKS,
    CLOUD_METADATA_IPS,
    is_ip_blocked,
    resolve_domain_to_ip,
    validate_domain_for_ssrf,
)


class TestIsIpBlocked:
    """Tests for is_ip_blocked function."""

    def test_loopback_ipv4_blocked(self):
        """Test that IPv4 loopback addresses are blocked."""
        assert is_ip_blocked(ipaddress.ip_address("127.0.0.1")) is True
        assert is_ip_blocked(ipaddress.ip_address("127.255.255.255")) is True

    def test_loopback_ipv6_blocked(self):
        """Test that IPv6 loopback address is blocked."""
        assert is_ip_blocked(ipaddress.ip_address("::1")) is True

    def test_private_class_a_blocked(self):
        """Test that Class A private addresses are blocked."""
        assert is_ip_blocked(ipaddress.ip_address("10.0.0.1")) is True
        assert is_ip_blocked(ipaddress.ip_address("10.255.255.255")) is True

    def test_private_class_b_blocked(self):
        """Test that Class B private addresses are blocked."""
        assert is_ip_blocked(ipaddress.ip_address("172.16.0.1")) is True
        assert is_ip_blocked(ipaddress.ip_address("172.31.255.255")) is True

    def test_private_class_c_blocked(self):
        """Test that Class C private addresses are blocked."""
        assert is_ip_blocked(ipaddress.ip_address("192.168.0.1")) is True
        assert is_ip_blocked(ipaddress.ip_address("192.168.255.255")) is True

    def test_link_local_blocked(self):
        """Test that link-local addresses are blocked (includes AWS metadata)."""
        assert is_ip_blocked(ipaddress.ip_address("169.254.0.1")) is True
        assert is_ip_blocked(ipaddress.ip_address("169.254.169.254")) is True

    def test_aws_metadata_ip_blocked(self):
        """Test that AWS metadata IP is blocked."""
        assert is_ip_blocked(ipaddress.ip_address("169.254.169.254")) is True

    def test_carrier_grade_nat_blocked(self):
        """Test that carrier-grade NAT addresses are blocked."""
        assert is_ip_blocked(ipaddress.ip_address("100.64.0.1")) is True
        assert is_ip_blocked(ipaddress.ip_address("100.127.255.255")) is True

    def test_this_network_blocked(self):
        """Test that 'this' network addresses are blocked."""
        assert is_ip_blocked(ipaddress.ip_address("0.0.0.1")) is True

    def test_multicast_blocked(self):
        """Test that multicast addresses are blocked."""
        assert is_ip_blocked(ipaddress.ip_address("224.0.0.1")) is True
        assert is_ip_blocked(ipaddress.ip_address("239.255.255.255")) is True

    def test_broadcast_blocked(self):
        """Test that broadcast address is blocked."""
        assert is_ip_blocked(ipaddress.ip_address("255.255.255.255")) is True

    def test_ipv6_ula_blocked(self):
        """Test that IPv6 ULA addresses are blocked."""
        assert is_ip_blocked(ipaddress.ip_address("fc00::1")) is True
        assert is_ip_blocked(ipaddress.ip_address("fd00::1")) is True

    def test_ipv6_link_local_blocked(self):
        """Test that IPv6 link-local addresses are blocked."""
        assert is_ip_blocked(ipaddress.ip_address("fe80::1")) is True

    def test_public_ipv4_allowed(self):
        """Test that public IPv4 addresses are allowed."""
        assert is_ip_blocked(ipaddress.ip_address("8.8.8.8")) is False
        assert is_ip_blocked(ipaddress.ip_address("1.1.1.1")) is False
        assert is_ip_blocked(ipaddress.ip_address("93.184.216.34")) is False

    def test_public_ipv6_allowed(self):
        """Test that public IPv6 addresses are allowed."""
        assert is_ip_blocked(ipaddress.ip_address("2606:4700:4700::1111")) is False


class TestResolveDomainToIp:
    """Tests for resolve_domain_to_ip function."""

    def test_resolve_domain_with_port(self):
        """Test that port is stripped from domain."""
        with patch("socket.getaddrinfo") as mock_getaddrinfo:
            mock_getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0))
            ]
            result = resolve_domain_to_ip("example.com:8080")
            assert result == "93.184.216.34"
            mock_getaddrinfo.assert_called_once_with(
                "example.com", None, socket.AF_UNSPEC, socket.SOCK_STREAM
            )

    def test_resolve_domain_without_port(self):
        """Test resolving domain without port."""
        with patch("socket.getaddrinfo") as mock_getaddrinfo:
            mock_getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0))
            ]
            result = resolve_domain_to_ip("example.com")
            assert result == "93.184.216.34"

    def test_resolve_domain_empty_result(self):
        """Test that empty resolution result raises HTTPException."""
        with patch("socket.getaddrinfo") as mock_getaddrinfo:
            mock_getaddrinfo.return_value = []
            with pytest.raises(HTTPException) as exc_info:
                resolve_domain_to_ip("invalid-domain.test")
            assert exc_info.value.status_code == 400
            assert "Could not resolve domain" in exc_info.value.detail

    def test_resolve_domain_gaierror(self):
        """Test that socket.gaierror raises HTTPException."""
        with patch("socket.getaddrinfo") as mock_getaddrinfo:
            mock_getaddrinfo.side_effect = socket.gaierror("DNS lookup failed")
            with pytest.raises(HTTPException) as exc_info:
                resolve_domain_to_ip("nonexistent-domain.test")
            assert exc_info.value.status_code == 400
            assert "Could not resolve domain" in exc_info.value.detail


class TestValidateDomainForSsrf:
    """Tests for validate_domain_for_ssrf function."""

    def test_empty_domain_raises_error(self):
        """Test that empty domain raises HTTPException."""
        with pytest.raises(HTTPException) as exc_info:
            validate_domain_for_ssrf("")
        assert exc_info.value.status_code == 400
        assert "Domain is required" in exc_info.value.detail

    def test_direct_localhost_ip_blocked(self):
        """Test that direct localhost IP is blocked."""
        with pytest.raises(HTTPException) as exc_info:
            validate_domain_for_ssrf("127.0.0.1")
        assert exc_info.value.status_code == 403
        assert "internal or private IP" in exc_info.value.detail

    def test_direct_private_ip_blocked(self):
        """Test that direct private IP is blocked."""
        with pytest.raises(HTTPException) as exc_info:
            validate_domain_for_ssrf("10.0.0.1")
        assert exc_info.value.status_code == 403

    def test_direct_public_ip_allowed(self):
        """Test that direct public IP is allowed."""
        # This should not raise an exception
        validate_domain_for_ssrf("8.8.8.8")

    def test_protocol_stripped_https(self):
        """Test that https:// protocol is stripped."""
        with pytest.raises(HTTPException) as exc_info:
            validate_domain_for_ssrf("https://127.0.0.1")
        assert exc_info.value.status_code == 403

    def test_protocol_stripped_http(self):
        """Test that http:// protocol is stripped."""
        with pytest.raises(HTTPException) as exc_info:
            validate_domain_for_ssrf("http://192.168.1.1")
        assert exc_info.value.status_code == 403

    def test_protocol_stripped_wss(self):
        """Test that wss:// protocol is stripped."""
        with pytest.raises(HTTPException) as exc_info:
            validate_domain_for_ssrf("wss://10.0.0.1")
        assert exc_info.value.status_code == 403

    def test_protocol_stripped_ws(self):
        """Test that ws:// protocol is stripped."""
        with pytest.raises(HTTPException) as exc_info:
            validate_domain_for_ssrf("ws://172.16.0.1")
        assert exc_info.value.status_code == 403

    def test_domain_resolving_to_blocked_ip(self):
        """Test that domain resolving to blocked IP is rejected."""
        with patch(
            "syfthub.core.ssrf_protection.resolve_domain_to_ip"
        ) as mock_resolve:
            mock_resolve.return_value = "127.0.0.1"
            with pytest.raises(HTTPException) as exc_info:
                validate_domain_for_ssrf("malicious-domain.com")
            assert exc_info.value.status_code == 403

    def test_domain_resolving_to_public_ip_allowed(self):
        """Test that domain resolving to public IP is allowed."""
        with patch(
            "syfthub.core.ssrf_protection.resolve_domain_to_ip"
        ) as mock_resolve:
            mock_resolve.return_value = "93.184.216.34"
            # Should not raise
            validate_domain_for_ssrf("example.com")

    def test_ip_with_port_blocked(self):
        """Test that IP with port is correctly parsed and blocked."""
        with pytest.raises(HTTPException) as exc_info:
            validate_domain_for_ssrf("127.0.0.1:8080")
        assert exc_info.value.status_code == 403

    def test_whitespace_stripped(self):
        """Test that whitespace is stripped from domain."""
        with pytest.raises(HTTPException) as exc_info:
            validate_domain_for_ssrf("  127.0.0.1  ")
        assert exc_info.value.status_code == 403

    def test_invalid_resolved_ip_raises_error(self):
        """Test that invalid resolved IP raises HTTPException."""
        with patch(
            "syfthub.core.ssrf_protection.resolve_domain_to_ip"
        ) as mock_resolve:
            mock_resolve.return_value = "invalid-ip"
            with pytest.raises(HTTPException) as exc_info:
                validate_domain_for_ssrf("example.com")
            assert exc_info.value.status_code == 400
            assert "Invalid IP address resolved" in exc_info.value.detail


class TestBlockedNetworksConstant:
    """Tests for BLOCKED_IP_NETWORKS constant."""

    def test_blocked_networks_not_empty(self):
        """Test that blocked networks list is not empty."""
        assert len(BLOCKED_IP_NETWORKS) > 0

    def test_blocked_networks_contains_localhost(self):
        """Test that localhost network is in blocked list."""
        localhost = ipaddress.ip_network("127.0.0.0/8")
        assert localhost in BLOCKED_IP_NETWORKS

    def test_blocked_networks_contains_private_ranges(self):
        """Test that private network ranges are in blocked list."""
        private_a = ipaddress.ip_network("10.0.0.0/8")
        private_b = ipaddress.ip_network("172.16.0.0/12")
        private_c = ipaddress.ip_network("192.168.0.0/16")
        assert private_a in BLOCKED_IP_NETWORKS
        assert private_b in BLOCKED_IP_NETWORKS
        assert private_c in BLOCKED_IP_NETWORKS


class TestCloudMetadataIpsConstant:
    """Tests for CLOUD_METADATA_IPS constant."""

    def test_cloud_metadata_ips_not_empty(self):
        """Test that cloud metadata IPs set is not empty."""
        assert len(CLOUD_METADATA_IPS) > 0

    def test_aws_metadata_ip_in_set(self):
        """Test that AWS metadata IP is in the set."""
        assert "169.254.169.254" in CLOUD_METADATA_IPS

    def test_aws_ecs_metadata_ip_in_set(self):
        """Test that AWS ECS metadata IP is in the set."""
        assert "169.254.170.2" in CLOUD_METADATA_IPS
