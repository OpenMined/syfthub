#!/usr/bin/env python3
"""
Generate RSA private key for MCP server JWT signing.

This script generates a 2048-bit RSA private key and outputs it as a
base64-encoded PEM string suitable for use in the RSA_PRIVATE_KEY
environment variable.

Usage:
    python generate_rsa_key.py

    # Or to save directly to .env file:
    echo "RSA_PRIVATE_KEY=$(python generate_rsa_key.py)" >> .env

The generated key should be stored securely and passed to the MCP server
via environment variable in production deployments with multiple workers.
"""

import base64

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def generate_rsa_key() -> str:
    """
    Generate a new RSA private key and return it as base64-encoded PEM.

    Returns:
        str: Base64-encoded PEM private key
    """
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )

    return base64.b64encode(private_pem).decode('utf-8')


if __name__ == "__main__":
    key = generate_rsa_key()
    print(key)
