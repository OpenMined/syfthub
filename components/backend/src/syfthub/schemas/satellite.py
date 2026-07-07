"""Pydantic schemas for Identity Provider (IdP) satellite token system.

These schemas define the request/response formats for:
- JWKS (JSON Web Key Set) endpoint
- Satellite token minting endpoint

Based on OpenAPI 3.0 specification for SyftHub Identity & Trust API.
"""

from __future__ import annotations

from typing import List, Literal, Union

from pydantic import BaseModel, Field


class JSONWebKey(BaseModel):
    """JSON Web Key (JWK) representing an RSA public key.

    Used by satellite services to verify tokens locally without
    calling SyftHub for every request.

    Attributes:
        kty: Key Type - always "RSA" for RSA keys
        kid: Key ID - matches the 'kid' header in issued JWTs
        use: Intended use - "sig" for signature verification
        alg: Algorithm - "RS256" for RSA with SHA-256
        n: RSA Modulus (Base64URL encoded, no padding)
        e: RSA Exponent (Base64URL encoded, no padding)
    """

    kty: str = Field(
        default="RSA",
        description="Key Type",
        examples=["RSA"],
    )
    kid: str = Field(
        ...,
        description="Key ID - matches the 'kid' header in issued JWTs",
        examples=["hub-key-2024-a"],
    )
    use: str = Field(
        default="sig",
        description="Intended use (Signature)",
        examples=["sig"],
    )
    alg: str = Field(
        default="RS256",
        description="Algorithm used",
        examples=["RS256"],
    )
    n: str = Field(
        ...,
        description="RSA Modulus (Base64URL encoded)",
    )
    e: str = Field(
        ...,
        description="RSA Exponent (Base64URL encoded)",
        examples=["AQAB"],
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "kty": "RSA",
                "kid": "hub-key-2024-a",
                "use": "sig",
                "alg": "RS256",
                "n": "0vx7agoebGcQSuuPiLJXZpt...",
                "e": "AQAB",
            }
        }
    }


class JSONWebKeySet(BaseModel):
    """JSON Web Key Set (JWKS) containing public RSA keys.

    Satellite services fetch this once and cache it for local
    token verification. The JWKS contains all active public keys
    to support key rotation.

    Attributes:
        keys: List of JSON Web Keys
    """

    keys: List[JSONWebKey] = Field(
        ...,
        description="Array of JSON Web Keys",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "keys": [
                    {
                        "kty": "RSA",
                        "kid": "hub-key-2024-a",
                        "use": "sig",
                        "alg": "RS256",
                        "n": "0vx7agoebGcQSuuPiLJXZpt...",
                        "e": "AQAB",
                    }
                ]
            }
        }
    }


class SatelliteTokenResponse(BaseModel):
    """Response containing an audience-bound satellite token.

    The target_token is a short-lived (e.g., 60s), RS256-signed JWT
    that can be verified by satellite services using the Hub's
    public keys from the JWKS endpoint.

    Attributes:
        target_token: RS256 signed JWT for the target service
        expires_in: Seconds until the token expires
    """

    target_token: str = Field(
        ...,
        description=(
            "A short-lived, RS256 signed JWT. "
            "Claims include: sub (user), aud (requested service), role (user role)."
        ),
        examples=["eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6Imh1Yi1rZXktMSJ9..."],
    )
    expires_in: int = Field(
        ...,
        description="Seconds until the token expires",
        examples=[60],
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "target_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6Imh1Yi1rZXktMSJ9.eyJzdWIiOiIxMjMiLCJpc3MiOiJodHRwczovL2h1Yi5zeWZ0LmNvbSIsImF1ZCI6InN5ZnRhaS1zcGFjZSIsImV4cCI6MTY5OTk5OTk5OSwicm9sZSI6InVzZXIifQ.signature",
                "expires_in": 60,
            }
        }
    }


class SatelliteTokenErrorResponse(BaseModel):
    """Error response for satellite token requests.

    Returned when token generation fails due to invalid audience
    or other validation errors.

    Attributes:
        error: Error code (e.g., "invalid_audience")
        message: Human-readable error message
    """

    error: str = Field(
        ...,
        description="Error code",
        examples=["invalid_audience"],
    )
    message: str = Field(
        ...,
        description="Human-readable error message",
        examples=["The requested audience 'syft-mars' is not a registered service."],
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "error": "invalid_audience",
                "message": "The requested audience 'syft-mars' is not a registered service.",
            }
        }
    }


# ===========================================
# TOKEN VERIFICATION SCHEMAS
# ===========================================


class TokenVerifyRequest(BaseModel):
    """Request to verify a satellite token.

    Satellite services call the /verify endpoint with a token
    to validate it and retrieve user context.

    Attributes:
        token: The satellite token to verify
    """

    token: str = Field(
        ...,
        description="The satellite token to verify",
        examples=["eyJhbGciOiJSUzI1NiIsImtpZCI6Imh1Yi1rZXktMSJ9..."],
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "token": "eyJhbGciOiJSUzI1NiIsImtpZCI6Imh1Yi1rZXktMSJ9.eyJzdWIiOiIxMjMiLCJhdWQiOiJzeWZ0YWktc3BhY2UifQ.signature"
            }
        }
    }


class TokenVerifySuccessResponse(BaseModel):
    """Successful token verification response.

    Returned when a satellite token is valid. Contains the decoded
    token claims plus additional user context from the database.

    Attributes:
        valid: Always True for success responses
        sub: User's unique ID (from token)
        email: User's email address (from database)
        username: User's username (from database)
        role: User's role (from token)
        aud: Token audience (the target service)
        exp: Token expiry timestamp (Unix epoch)
        iat: Token issued-at timestamp (Unix epoch)
    """

    valid: Literal[True] = Field(
        default=True,
        description="Indicates the token is valid",
    )
    sub: str = Field(
        ...,
        description="User's unique ID",
        examples=["123"],
    )
    email: str = Field(
        ...,
        description="User's email address",
        examples=["alice@om.org"],
    )
    username: str = Field(
        ...,
        description="User's username",
        examples=["alice"],
    )
    role: str = Field(
        ...,
        description="User's role",
        examples=["admin", "user"],
    )
    aud: str = Field(
        ...,
        description="Token audience (target service identifier)",
        examples=["syftai-space"],
    )
    exp: int = Field(
        ...,
        description="Token expiry timestamp (Unix epoch seconds)",
        examples=[1699999999],
    )
    iat: int = Field(
        ...,
        description="Token issued-at timestamp (Unix epoch seconds)",
        examples=[1699999939],
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "valid": True,
                "sub": "123",
                "email": "alice@om.org",
                "username": "alice",
                "role": "admin",
                "aud": "syftai-space",
                "exp": 1699999999,
                "iat": 1699999939,
            }
        }
    }


class TokenVerifyErrorResponse(BaseModel):
    """Failed token verification response.

    Returned when a satellite token is invalid, expired, or
    the calling service is not authorized for the token's audience.

    Attributes:
        valid: Always False for error responses
        error: Error code identifying the failure type
        message: Human-readable error description
    """

    valid: Literal[False] = Field(
        default=False,
        description="Indicates the token is invalid",
    )
    error: str = Field(
        ...,
        description="Error code",
        examples=["token_expired", "invalid_signature", "audience_mismatch"],
    )
    message: str = Field(
        ...,
        description="Human-readable error message",
        examples=["The token has expired."],
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "valid": False,
                "error": "token_expired",
                "message": "The token has expired.",
            }
        }
    }


# Union type for verify endpoint response
TokenVerifyResponse = Union[TokenVerifySuccessResponse, TokenVerifyErrorResponse]
