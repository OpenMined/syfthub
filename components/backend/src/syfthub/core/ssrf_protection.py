"""SSRF (Server-Side Request Forgery) protection utilities.

This module provides functions to validate domains and IP addresses
to prevent SSRF attacks where an attacker could force the server to
make requests to internal services, cloud metadata endpoints, or
other sensitive resources.
"""

from __future__ import annotations

import ipaddress
import socket
from typing import Union

from fastapi import HTTPException, status

from syfthub.observability import get_logger

logger = get_logger(__name__)

# Blocked IP networks - these should never be accessed by the server
# when proxying requests to user-specified domains
BLOCKED_IP_NETWORKS: tuple[Union[ipaddress.IPv4Network, ipaddress.IPv6Network], ...] = (
    # IPv4 private and special ranges
    ipaddress.ip_network("0.0.0.0/8"),  # "This" network (current network)
    ipaddress.ip_network("10.0.0.0/8"),  # Private (Class A)
    ipaddress.ip_network("100.64.0.0/10"),  # Carrier-grade NAT
    ipaddress.ip_network("127.0.0.0/8"),  # Loopback (localhost)
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local (includes AWS metadata)
    ipaddress.ip_network("172.16.0.0/12"),  # Private (Class B)
    ipaddress.ip_network("192.0.0.0/24"),  # IETF Protocol Assignments
    ipaddress.ip_network("192.0.2.0/24"),  # TEST-NET-1
    ipaddress.ip_network("192.88.99.0/24"),  # 6to4 Relay Anycast
    ipaddress.ip_network("192.168.0.0/16"),  # Private (Class C)
    ipaddress.ip_network("198.18.0.0/15"),  # Benchmark testing
    ipaddress.ip_network("198.51.100.0/24"),  # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),  # TEST-NET-3
    ipaddress.ip_network("224.0.0.0/4"),  # Multicast
    ipaddress.ip_network("240.0.0.0/4"),  # Reserved for future use
    ipaddress.ip_network("255.255.255.255/32"),  # Broadcast
    # IPv6 private and special ranges
    ipaddress.ip_network("::1/128"),  # Loopback
    ipaddress.ip_network("::/128"),  # Unspecified
    ipaddress.ip_network("::ffff:0:0/96"),  # IPv4-mapped IPv6
    ipaddress.ip_network("64:ff9b::/96"),  # IPv4/IPv6 translation
    ipaddress.ip_network("100::/64"),  # Discard prefix
    ipaddress.ip_network("2001::/32"),  # Teredo tunneling
    ipaddress.ip_network("2001:10::/28"),  # ORCHID
    ipaddress.ip_network("2001:20::/28"),  # ORCHIDv2
    ipaddress.ip_network("2001:db8::/32"),  # Documentation
    ipaddress.ip_network("2002::/16"),  # 6to4
    ipaddress.ip_network("fc00::/7"),  # Unique local addresses (ULA)
    ipaddress.ip_network("fe80::/10"),  # Link-local
    ipaddress.ip_network("ff00::/8"),  # Multicast
)

# Cloud metadata service IPs (explicitly listed for clarity)
# These are already covered by the ranges above, but listed for documentation
CLOUD_METADATA_IPS: frozenset[str] = frozenset(
    [
        "169.254.169.254",  # AWS, GCP, Azure, DigitalOcean
        "169.254.170.2",  # AWS ECS task metadata
        "fd00:ec2::254",  # AWS IPv6 metadata
    ]
)


def is_ip_blocked(
    ip_address: Union[ipaddress.IPv4Address, ipaddress.IPv6Address],
) -> bool:
    """Check if an IP address is in a blocked range.

    Args:
        ip_address: The IP address to check

    Returns:
        True if the IP is blocked, False if it's safe to access
    """
    return any(ip_address in network for network in BLOCKED_IP_NETWORKS)


def resolve_domain_to_ip(domain: str) -> str:
    """Resolve a domain name to its IP address.

    Args:
        domain: The domain name to resolve (without protocol)

    Returns:
        The resolved IP address as a string

    Raises:
        HTTPException: If the domain cannot be resolved
    """
    # Strip port if present (e.g., "example.com:8080" -> "example.com")
    hostname = domain.split(":")[0] if ":" in domain else domain

    try:
        # Use getaddrinfo for both IPv4 and IPv6 support
        # This returns the first available address
        addr_info = socket.getaddrinfo(
            hostname,
            None,
            socket.AF_UNSPEC,  # Allow both IPv4 and IPv6
            socket.SOCK_STREAM,
        )
        if not addr_info:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Could not resolve domain: {hostname}",
            )
        # addr_info[0][4][0] is the IP address from the first result
        # Cast to str since socket.getaddrinfo returns the IP as a string
        ip_result = addr_info[0][4][0]
        return str(ip_result)
    except socket.gaierror as e:
        logger.warning(
            "ssrf.domain_resolution_failed",
            domain=hostname,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not resolve domain: {hostname}",
        ) from e


def validate_domain_for_ssrf(domain: str) -> None:
    """Validate that a domain does not resolve to a blocked IP address.

    This function performs DNS resolution and checks if the resolved IP
    is in any of the blocked ranges (private networks, localhost, cloud
    metadata services, etc.).

    Args:
        domain: The domain to validate (without protocol)

    Raises:
        HTTPException: If the domain resolves to a blocked IP or cannot be resolved

    Example:
        >>> validate_domain_for_ssrf("api.example.com")  # OK
        >>> validate_domain_for_ssrf("localhost")  # Raises HTTPException
        >>> validate_domain_for_ssrf("169.254.169.254")  # Raises HTTPException
    """
    if not domain:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Domain is required for endpoint invocation",
        )

    # Strip any accidental protocol prefix
    clean_domain = domain.strip()
    for prefix in ("https://", "http://", "wss://", "ws://"):
        if clean_domain.lower().startswith(prefix):
            clean_domain = clean_domain[len(prefix) :]
            break

    # Check if the domain is directly an IP address
    hostname = clean_domain.split(":")[0] if ":" in clean_domain else clean_domain

    try:
        # Try to parse as IP address directly
        ip = ipaddress.ip_address(hostname)
        if is_ip_blocked(ip):
            logger.warning(
                "ssrf.blocked_ip_direct",
                domain=domain,
                ip=str(ip),
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access to internal or private IP addresses is not allowed",
            )
        return  # IP is safe
    except ValueError:
        # Not an IP address, need to resolve the domain
        pass

    # Resolve the domain to an IP
    resolved_ip_str = resolve_domain_to_ip(clean_domain)

    try:
        resolved_ip = ipaddress.ip_address(resolved_ip_str)
    except ValueError:
        logger.error(
            "ssrf.invalid_resolved_ip",
            domain=domain,
            resolved_ip=resolved_ip_str,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid IP address resolved for domain: {domain}",
        ) from None

    if is_ip_blocked(resolved_ip):
        logger.warning(
            "ssrf.blocked_ip_resolved",
            domain=domain,
            resolved_ip=str(resolved_ip),
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to internal or private IP addresses is not allowed",
        )

    logger.debug(
        "ssrf.domain_validated",
        domain=domain,
        resolved_ip=str(resolved_ip),
    )
