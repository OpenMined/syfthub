"""
FastMCP MCP Server with Integrated OAuth 2.1 Authorization Server and SyftHub Integration

A comprehensive FastMCP server implementation featuring:
- Consolidated OAuth 2.1 authorization server with PKCE support
- SyftHub authentication integration (username/password)
- Automatic token storage and session management
- Complete MCP protocol implementation

This module provides OAuth 2.1 authorization for MCP clients, using SyftHub
as the identity provider for user authentication.
"""

import os
import logging
import base64
import uuid
import time
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Annotated
from urllib.parse import urlencode
from fastmcp import FastMCP
from fastmcp.server.auth import RemoteAuthProvider
from fastmcp.server.auth.providers.jwt import JWTVerifier
from pydantic import BaseModel, AnyHttpUrl, Field
from starlette.routing import Route
from starlette.responses import JSONResponse, HTMLResponse
from starlette.requests import Request
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
import jwt
from syfthub_client import SyftHubClient, AuthenticationError, SyftHubError

# Import SyftHub SDK for endpoint discovery and chat
try:
    from syfthub_sdk import SyftHubClient as SyftHubSDKClient
    from syfthub_sdk.models import AuthTokens, EndpointType, EndpointRef
    from syfthub_sdk.exceptions import (
        SyftHubError as SDKError,
        AggregatorError,
        EndpointResolutionError,
        AuthenticationError as SDKAuthError,
    )
    SDK_AVAILABLE = True
except ImportError as e:
    SDK_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning(f"SyftHub SDK not available: {e}. Some tools will be disabled.")


# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("echo_server_consolidated")
logging.getLogger("fastmcp.server.auth").setLevel(logging.DEBUG)
logging.getLogger("mcp.server.auth").setLevel(logging.DEBUG)
logging.getLogger("fastmcp.server.auth.providers.jwt").setLevel(logging.DEBUG)

# OAuth Server Configuration (proxy-aware URLs)
OAUTH_ISSUER = os.getenv("OAUTH_ISSUER", "http://localhost:8080/mcp")
OAUTH_AUDIENCE = os.getenv("OAUTH_AUDIENCE", "mcp-server")
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8080/mcp")
# Internal JWKS URI for token verification (inside container, use localhost:MCP_PORT)
MCP_PORT = os.getenv("MCP_PORT", "8002")
INTERNAL_JWKS_URI = os.getenv("INTERNAL_JWKS_URI", f"http://localhost:{MCP_PORT}/.well-known/jwks.json")
JWKS_KID = "mcp-key-1"

# SyftHub Configuration
SYFTHUB_URL = os.getenv("SYFTHUB_URL", "http://localhost:8000")
SYFTHUB_PUBLIC_URL = os.getenv("SYFTHUB_PUBLIC_URL", "http://localhost:8080")
AGGREGATOR_URL = os.getenv("AGGREGATOR_URL", "http://localhost:8001")

logger.info(f"OAuth Issuer: {OAUTH_ISSUER}")
logger.info(f"OAuth Audience: {OAUTH_AUDIENCE}")
logger.info(f"API Base URL: {API_BASE_URL}")

# RSA Key Configuration for JWT Signing
# In multi-worker deployments, all workers must share the same RSA key pair.
# Set RSA_PRIVATE_KEY environment variable with base64-encoded PEM private key.
# Generate with: python -c "from cryptography.hazmat.primitives.asymmetric import rsa; from cryptography.hazmat.primitives import serialization; import base64; k=rsa.generate_private_key(65537,2048); print(base64.b64encode(k.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())).decode())"

# Support both RSA_PRIVATE_KEY and RSA_PRIVATE_KEY_PEM for backwards compatibility
RSA_PRIVATE_KEY_ENV = os.getenv("RSA_PRIVATE_KEY") or os.getenv("RSA_PRIVATE_KEY_PEM")

if RSA_PRIVATE_KEY_ENV:
    # Load shared RSA key from environment variable (base64-encoded PEM)
    logger.info("Loading RSA private key from RSA_PRIVATE_KEY environment variable...")
    try:
        private_pem = base64.b64decode(RSA_PRIVATE_KEY_ENV)
        private_key = serialization.load_pem_private_key(
            private_pem,
            password=None,
            backend=default_backend()
        )
        public_key = private_key.public_key()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        logger.info("RSA key pair loaded successfully from environment")
    except Exception as e:
        logger.error(f"Failed to load RSA key from environment: {e}")
        raise RuntimeError(
            "Invalid RSA_PRIVATE_KEY environment variable. "
            "Ensure it contains a valid base64-encoded PEM private key."
        ) from e
else:
    # Generate new RSA key pair (for development or single-worker deployments)
    environment = os.getenv("ENVIRONMENT", "development")
    if environment == "production":
        logger.warning(
            "⚠️  RSA_PRIVATE_KEY not set in production! Generating ephemeral key pair. "
            "This will cause JWT validation failures in multi-worker deployments. "
            "Set RSA_PRIVATE_KEY environment variable for production use."
        )
    else:
        logger.info("Generating RSA key pair for JWT signing (development mode)...")

    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )
    public_key = private_key.public_key()

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )

    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )

    logger.info("RSA key pair generated successfully")

# In-memory storage for OAuth server
# TODO: Replace in-memory storage with Redis-backed storage to support multiple workers.
# Currently limited to single worker (--workers 1) because OAuth client registrations,
# authorization codes, and access tokens are stored in-memory per process.
# With multiple workers, a client registered on Worker A won't exist on Worker B,
# causing "invalid_client" errors. Redis is already available in the stack and can be
# used to share OAuth state across workers. See: https://redis.io/docs/data-types/hashes/
oauth_clients: Dict[str, dict] = {}
oauth_authorization_codes: Dict[str, dict] = {}
oauth_access_tokens: Dict[str, dict] = {}

# In-memory storage for SyftHub user sessions (mapped by user email)
# Contains: {tokens, user_info, accounting_credentials, stored_at}
syfthub_sessions: Dict[str, dict] = {}

# Initialize SyftHub client for authentication
syfthub = SyftHubClient(base_url=SYFTHUB_URL)
logger.info(f"SyftHub client initialized with URL: {SYFTHUB_URL}")

# Deprecated SyftBox variables (kept for backward compatibility)
# These were used by the now-deprecated SyftBox distributed query features
syftbox_router_paths: Dict[str, str] = {}
syftbox_user_tokens: Dict[str, dict] = {}


# Deprecated SyftBox functions (stubs to prevent import errors)
# The SyftBox distributed query features are no longer maintained
async def scrape_syftbox_datasites() -> Dict[str, Any]:
    """Deprecated: SyftBox functionality has been removed."""
    logger.warning("scrape_syftbox_datasites called but SyftBox is deprecated")
    return {}


def transform_syftbox_to_table_format(syftbox_data: Dict) -> List[Dict]:
    """Deprecated: SyftBox functionality has been removed."""
    return []


async def build_context_request(**kwargs) -> Dict[str, Any]:
    """Deprecated: SyftBox functionality has been removed."""
    logger.warning("build_context_request called but SyftBox is deprecated")
    return {"success": False, "error": "SyftBox functionality has been deprecated"}


def get_syftbox_tokens(email: str) -> Optional[Dict[str, Any]]:
    """Deprecated: SyftBox functionality has been removed."""
    return None


def get_sdk_client_for_user(user_email: str) -> Optional["SyftHubSDKClient"]:
    """
    Create a SyftHub SDK client configured with the user's tokens.

    Args:
        user_email: Email of the authenticated user

    Returns:
        SyftHubSDKClient configured with user tokens, or None if not available
    """
    if not SDK_AVAILABLE:
        logger.warning("SDK not available - cannot create SDK client")
        return None

    session = syfthub_sessions.get(user_email)
    if not session or not session.get("tokens"):
        logger.warning(f"No session or tokens found for user: {user_email}")
        return None

    tokens = session["tokens"]

    try:
        # Use internal URLs for container-to-container communication
        client = SyftHubSDKClient(
            base_url=SYFTHUB_URL,  # Internal backend URL (http://backend:8000)
            aggregator_url=AGGREGATOR_URL,  # Internal aggregator URL (http://aggregator:8001)
            timeout=60.0
        )
        client.set_tokens(AuthTokens(
            access_token=tokens.get("access_token", ""),
            refresh_token=tokens.get("refresh_token", ""),
            token_type=tokens.get("token_type", "bearer")
        ))
        return client
    except Exception as e:
        logger.error(f"Failed to create SDK client: {e}")
        return None


# OAuth Data Models
class ClientRegistrationRequest(BaseModel):
    client_name: str = "FastMCP Client"
    redirect_uris: List[str]
    grant_types: List[str] = ["authorization_code"]
    response_types: List[str] = ["code"]
    scope: str = "openid profile"
    token_endpoint_auth_method: str = "client_secret_basic"

class TokenRequest(BaseModel):
    grant_type: str
    code: Optional[str] = None
    redirect_uri: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    code_verifier: Optional[str] = None

# Utility functions for OAuth
def generate_jwt_token(claims: Dict[str, Any], expires_in: int = 3600) -> str:
    """
    Generate a signed JWT token with RS256 algorithm.

    Creates a JWT token with standard claims (iss, aud, iat, exp) and custom
    claims, signed with the server's private key for OAuth 2.1 compliance.

    Args:
        claims: Dictionary of custom claims to include in the token
        expires_in: Token expiration time in seconds (default: 3600)

    Returns:
        str: Base64-encoded JWT token string

    Note:
        Uses RS256 signature algorithm with server's private key and includes
        Key ID (kid) header for JWKS verification.
    """
    now = datetime.utcnow()
    payload = {
        "iss": OAUTH_ISSUER,
        "aud": OAUTH_AUDIENCE,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in)).timestamp()),
        **claims
    }

    return jwt.encode(payload, private_pem, algorithm="RS256", headers={"kid": JWKS_KID})

def int_to_base64url(val: int) -> str:
    """
    Convert integer to base64url encoding for JSON Web Key (JWK) format.

    Args:
        val: Integer value to encode

    Returns:
        str: Base64url-encoded string representation

    Note:
        Used for encoding RSA key components (n, e) in JWKS endpoint.
    """
    byte_length = (val.bit_length() + 7) // 8
    return base64.urlsafe_b64encode(val.to_bytes(byte_length, 'big')).decode('ascii').rstrip('=')

def verify_pkce(code_verifier: str, code_challenge: str, method: str = "S256") -> bool:
    """
    Verify PKCE (Proof Key for Code Exchange) code challenge.

    Validates that the code verifier matches the previously submitted
    code challenge using the specified method for OAuth 2.1 security.

    Args:
        code_verifier: Original random string from client
        code_challenge: Previously submitted challenge derived from verifier
        method: Challenge method - "S256" (SHA256) or "plain" (default: "S256")

    Returns:
        bool: True if verifier matches challenge, False otherwise

    Note:
        S256 method applies SHA256 hash and base64url encoding to verifier.
        Plain method compares verifier and challenge directly.
    """
    if method == "S256":
        digest = hashlib.sha256(code_verifier.encode('utf-8')).digest()
        challenge = base64.urlsafe_b64encode(digest).decode('utf-8').rstrip('=')
        return challenge == code_challenge
    elif method == "plain":
        return code_verifier == code_challenge
    return False

# SyftHub session management functions

def get_current_user_email() -> Optional[str]:
    """Get the current authenticated user's email from auth context"""
    try:
        from fastmcp.server.dependencies import get_access_token

        access_token = get_access_token()

        if access_token and access_token.claims:
            user_email = (
                access_token.claims.get('email') or
                access_token.claims.get('sub') or
                access_token.client_id or
                None
            )
            return user_email
        else:
            return None

    except RuntimeError:
        # No authentication context available
        return None
    except Exception:
        return None

def get_syfthub_session(email: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve stored SyftHub session for a specific user email.

    Args:
        email: User's email address used as storage key

    Returns:
        Optional[Dict[str, Any]]: Session dictionary if found, None otherwise
        Session contains: tokens, user_info, accounting, stored_at
    """
    return syfthub_sessions.get(email)


class SelfHostedAuthProvider(RemoteAuthProvider):
    """OAuth provider that handles both authorization server and resource server roles"""

    def __init__(self, token_verifier: JWTVerifier, base_url: str = None):
        # Configure for self-hosted OAuth (authorization_servers points to self)
        super().__init__(
            token_verifier=token_verifier,
            authorization_servers=[AnyHttpUrl(OAUTH_ISSUER)],
            base_url=base_url or API_BASE_URL
        )

    def get_routes(self, *args, **kwargs):
        """Override to provide OAuth server routes + standard auth routes"""
        routes = super().get_routes(*args, **kwargs)

        # OAuth Server Discovery Routes
        async def oauth_protected_resource_metadata(request):
            return JSONResponse({
                "resource": API_BASE_URL,
                "authorization_servers": [OAUTH_ISSUER],
                "scopes_supported": ["openid", "profile", "email"],
                "bearer_methods_supported": ["header"],
                "resource_documentation": f"{API_BASE_URL}/docs",
                "mcp_protocol_version": "2025-06-18",
                "resource_type": "mcp-server"
            })

        async def oauth_authorization_server_metadata(request):
            return JSONResponse({
                "issuer": OAUTH_ISSUER,
                "authorization_endpoint": f"{OAUTH_ISSUER}/oauth/authorize",
                "token_endpoint": f"{OAUTH_ISSUER}/oauth/token",
                "jwks_uri": f"{OAUTH_ISSUER}/.well-known/jwks.json",
                "registration_endpoint": f"{OAUTH_ISSUER}/oauth/register",
                "userinfo_endpoint": f"{OAUTH_ISSUER}/oauth/userinfo",
                "scopes_supported": ["openid", "profile", "email"],
                "response_types_supported": ["code"],
                "grant_types_supported": ["authorization_code", "client_credentials"],
                "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post"],
                "code_challenge_methods_supported": ["S256"],
                "subject_types_supported": ["public"],
                "id_token_signing_alg_values_supported": ["RS256"]
            })

        # OpenID Connect Discovery
        async def openid_configuration(request):
            return JSONResponse({
                "issuer": OAUTH_ISSUER,
                "authorization_endpoint": f"{OAUTH_ISSUER}/oauth/authorize",
                "token_endpoint": f"{OAUTH_ISSUER}/oauth/token",
                "jwks_uri": f"{OAUTH_ISSUER}/.well-known/jwks.json",
                "registration_endpoint": f"{OAUTH_ISSUER}/oauth/register",
                "userinfo_endpoint": f"{OAUTH_ISSUER}/oauth/userinfo",
                "scopes_supported": ["openid", "profile", "email"],
                "response_types_supported": ["code"],
                "grant_types_supported": ["authorization_code", "client_credentials"],
                "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post"],
                "claims_supported": ["sub", "iss", "aud", "exp", "iat", "email", "name"],
                "code_challenge_methods_supported": ["S256"],
                "subject_types_supported": ["public"],
                "id_token_signing_alg_values_supported": ["RS256"]
            })

        # JWKS endpoint
        async def jwks_endpoint(request):
            public_numbers = public_key.public_numbers()
            jwk = {
                "kty": "RSA",
                "kid": JWKS_KID,
                "use": "sig",
                "alg": "RS256",
                "n": int_to_base64url(public_numbers.n),
                "e": int_to_base64url(public_numbers.e)
            }
            return JSONResponse({"keys": [jwk]})

        oauth_routes = [
            Route("/.well-known/oauth-protected-resource", oauth_protected_resource_metadata),
            Route("/.well-known/oauth-authorization-server", oauth_authorization_server_metadata),
            Route("/.well-known/openid-configuration", openid_configuration),
            Route("/.well-known/jwks.json", jwks_endpoint),
        ]

        return routes + oauth_routes

# Configure JWT verification to point to self-hosted server
# Use internal JWKS URI for container-to-container verification
jwt_verifier = JWTVerifier(
    issuer=OAUTH_ISSUER,
    audience=OAUTH_AUDIENCE,
    jwks_uri=INTERNAL_JWKS_URI
)
logger.info(f"JWT Verifier using JWKS URI: {INTERNAL_JWKS_URI}")

# Create self-hosted auth provider
auth_provider = SelfHostedAuthProvider(
    token_verifier=jwt_verifier,
    base_url=API_BASE_URL
)

logger.info(f"Self-hosted OAuth configured with issuer: {OAUTH_ISSUER}")
logger.info(f"JWT audience: {OAUTH_AUDIENCE}")
logger.info(f"JWKS URI: {OAUTH_ISSUER}/.well-known/jwks.json")

# Create server with self-hosted authentication
mcp = FastMCP("SyftHub MCP Server", auth=auth_provider)

# OAuth Server Endpoints using FastMCP custom routes
@mcp.custom_route("/oauth/register", ["POST"])
async def oauth_register(request: Request):
    """Dynamic Client Registration endpoint"""
    try:
        body = await request.json()
        req = ClientRegistrationRequest(**body)

        client_id = f"client_{uuid.uuid4().hex[:8]}"
        client_secret = f"secret_{uuid.uuid4().hex}"

        client_info = {
            "client_id": client_id,
            "client_secret": client_secret,
            "client_name": req.client_name,
            "redirect_uris": req.redirect_uris,
            "grant_types": req.grant_types,
            "response_types": req.response_types,
            "scope": req.scope,
            "token_endpoint_auth_method": req.token_endpoint_auth_method,
            "created_at": datetime.utcnow().isoformat()
        }

        oauth_clients[client_id] = client_info
        logger.info(f"Registered new client: {client_id}")

        return JSONResponse({
            "client_id": client_id,
            "client_secret": client_secret,
            "client_id_issued_at": int(time.time()),
            "client_secret_expires_at": 0,  # Never expires
            **client_info
        })

    except Exception as e:
        logger.error(f"Client registration error: {e}")
        return JSONResponse({"error": "invalid_request", "error_description": str(e)}, status_code=400)

@mcp.custom_route("/oauth/authorize", ["GET"])
async def oauth_authorize(request: Request):
    """Authorization endpoint with SyftHub email/password authentication"""
    query_params = request.query_params

    response_type = query_params.get("response_type")
    client_id = query_params.get("client_id")
    redirect_uri = query_params.get("redirect_uri")
    scope = query_params.get("scope", "openid")
    state = query_params.get("state")
    code_challenge = query_params.get("code_challenge")
    code_challenge_method = query_params.get("code_challenge_method")

    if not all([response_type, client_id, redirect_uri]):
        return JSONResponse({"error": "invalid_request"}, status_code=400)

    if client_id not in oauth_clients:
        return JSONResponse({"error": "invalid_client"}, status_code=400)

    client = oauth_clients[client_id]
    if redirect_uri not in client["redirect_uris"]:
        return JSONResponse({"error": "invalid_request"}, status_code=400)

    # Return SyftHub authentication form (email + password)
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>SyftHub Authentication</title>
            <style>
                * {{
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }}

                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                    background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
                    min-height: 100vh;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    padding: 20px;
                    color: #333;
                }}

                .auth-container {{
                    background: rgba(255, 255, 255, 0.95);
                    backdrop-filter: blur(10px);
                    border-radius: 16px;
                    box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
                    padding: 40px;
                    width: 100%;
                    max-width: 440px;
                    border: 1px solid rgba(255, 255, 255, 0.2);
                }}

                .logo {{
                    text-align: center;
                    margin-bottom: 32px;
                }}

                .logo-icon {{
                    width: 64px;
                    height: 64px;
                    background: linear-gradient(135deg, #2d3748, #1a202c);
                    border-radius: 16px;
                    display: inline-flex;
                    align-items: center;
                    justify-content: center;
                    font-size: 28px;
                    margin-bottom: 16px;
                    box-shadow: 0 8px 20px rgba(45, 55, 72, 0.3);
                }}

                .title {{
                    font-size: 24px;
                    font-weight: 600;
                    color: #1a202c;
                    margin-bottom: 8px;
                    text-align: center;
                }}

                .subtitle {{
                    color: #718096;
                    text-align: center;
                    font-size: 15px;
                    line-height: 1.5;
                }}

                .form-group {{
                    margin-bottom: 20px;
                }}

                .input-label {{
                    display: block;
                    font-size: 14px;
                    font-weight: 500;
                    color: #4a5568;
                    margin-bottom: 8px;
                }}

                .input-wrapper {{
                    position: relative;
                }}

                input {{
                    width: 100%;
                    padding: 16px 20px;
                    border: 2px solid #e2e8f0;
                    border-radius: 12px;
                    font-size: 16px;
                    transition: all 0.2s ease;
                    background: #ffffff;
                    color: #2d3748;
                }}

                input:focus {{
                    outline: none;
                    border-color: #667eea;
                    box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
                    transform: translateY(-1px);
                }}

                input::placeholder {{
                    color: #a0aec0;
                }}

                .btn {{
                    width: 100%;
                    padding: 16px 20px;
                    background: linear-gradient(135deg, #2d3748, #1a202c);
                    color: white;
                    border: none;
                    border-radius: 12px;
                    font-size: 16px;
                    font-weight: 600;
                    cursor: pointer;
                    transition: all 0.2s ease;
                    text-transform: none;
                    letter-spacing: 0.025em;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    gap: 8px;
                }}

                .btn:hover {{
                    transform: translateY(-2px);
                    box-shadow: 0 10px 25px rgba(45, 55, 72, 0.3);
                }}

                .btn:active {{
                    transform: translateY(0);
                }}

                .btn:disabled {{
                    opacity: 0.6;
                    cursor: not-allowed;
                    transform: none;
                }}

                .btn .spinner {{
                    display: none;
                    width: 16px;
                    height: 16px;
                    border: 2px solid #ffffff;
                    border-radius: 50%;
                    border-top-color: transparent;
                    animation: spin 1s ease-in-out infinite;
                }}

                .btn.loading .spinner {{
                    display: inline-block;
                }}

                .btn.loading .btn-text {{
                    display: none;
                }}

                .btn .loading-text {{
                    display: none;
                }}

                .btn.loading .loading-text {{
                    display: inline;
                }}

                .status {{
                    margin: 16px 0;
                    padding: 12px 16px;
                    border-radius: 8px;
                    font-size: 14px;
                    font-weight: 500;
                    text-align: center;
                    opacity: 0;
                    transform: translateY(-10px);
                    transition: all 0.3s ease;
                }}

                .status.show {{
                    opacity: 1;
                    transform: translateY(0);
                }}

                .status.error {{
                    background: #fed7d7;
                    color: #c53030;
                    border: 1px solid #feb2b2;
                }}

                .status.success {{
                    background: #c6f6d5;
                    color: #2f855a;
                    border: 1px solid #9ae6b4;
                }}

                @keyframes spin {{
                    to {{ transform: rotate(360deg); }}
                }}

                .register-link {{
                    text-align: center;
                    margin-top: 24px;
                    padding-top: 24px;
                    border-top: 1px solid #e2e8f0;
                }}

                .register-link p {{
                    color: #718096;
                    font-size: 14px;
                }}

                .register-link a {{
                    color: #667eea;
                    text-decoration: none;
                    font-weight: 500;
                    transition: color 0.2s ease;
                }}

                .register-link a:hover {{
                    color: #5a67d8;
                    text-decoration: underline;
                }}

                @media (max-width: 480px) {{
                    .auth-container {{
                        padding: 24px;
                        margin: 10px;
                    }}

                    .title {{
                        font-size: 20px;
                    }}

                    input, .btn {{
                        padding: 14px 16px;
                        font-size: 15px;
                    }}
                }}
            </style>
        </head>
        <body>
            <div class="auth-container">
                <div class="logo">
                    <div class="logo-icon">&#128274;</div>
                    <h1 class="title">SyftHub Authentication</h1>
                    <p class="subtitle">Sign in with your SyftHub account</p>
                </div>

                <form id="loginForm" onsubmit="return false;">
                    <div class="form-group">
                        <label class="input-label" for="email">Email</label>
                        <div class="input-wrapper">
                            <input type="email" id="email" placeholder="your-email@example.com" autocomplete="email" required>
                        </div>
                    </div>

                    <div class="form-group">
                        <label class="input-label" for="password">Password</label>
                        <div class="input-wrapper">
                            <input type="password" id="password" placeholder="Enter your password" autocomplete="current-password" required>
                        </div>
                    </div>

                    <button class="btn" id="loginBtn" type="button">
                        <span class="spinner"></span>
                        <span class="btn-text">Sign In</span>
                        <span class="loading-text">Signing in...</span>
                    </button>

                    <div id="status" class="status"></div>
                </form>

                <div class="register-link">
                    <p>Don't have an account? <a href="{SYFTHUB_PUBLIC_URL}" target="_blank">Register on SyftHub</a></p>
                </div>
            </div>

            <script>
                // Email validation function
                function isValidEmail(email) {{
                    const emailRegex = /^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$/;
                    return emailRegex.test(email);
                }}

                // Button state management using CSS classes (no innerHTML)
                function setButtonLoading(loading) {{
                    const button = document.getElementById('loginBtn');
                    if (loading) {{
                        button.disabled = true;
                        button.classList.add('loading');
                    }} else {{
                        button.disabled = false;
                        button.classList.remove('loading');
                    }}
                }}

                // Status display using textContent (safe)
                function showStatus(message, type) {{
                    const el = document.getElementById('status');
                    el.textContent = message;
                    el.className = 'status ' + type + ' show';
                }}

                function hideStatus() {{
                    const el = document.getElementById('status');
                    el.className = 'status';
                }}

                // Login function
                async function login() {{
                    const email = document.getElementById('email').value.trim();
                    const password = document.getElementById('password').value;

                    // Validation
                    if (!email) {{
                        showStatus('Please enter your email address', 'error');
                        document.getElementById('email').focus();
                        return;
                    }}

                    if (!isValidEmail(email)) {{
                        showStatus('Please enter a valid email address', 'error');
                        document.getElementById('email').focus();
                        return;
                    }}

                    if (!password) {{
                        showStatus('Please enter your password', 'error');
                        document.getElementById('password').focus();
                        return;
                    }}

                    hideStatus();
                    setButtonLoading(true);

                    try {{
                        const response = await fetch('/mcp/auth/syfthub/login', {{
                            method: 'POST',
                            headers: {{'Content-Type': 'application/json'}},
                            body: JSON.stringify({{
                                email: email,
                                password: password,
                                client_id: '{client_id}',
                                redirect_uri: '{redirect_uri}',
                                scope: '{scope}',
                                state: '{state or ""}',
                                code_challenge: '{code_challenge or ""}',
                                code_challenge_method: '{code_challenge_method or ""}'
                            }})
                        }});

                        if (response.ok) {{
                            const result = await response.json();
                            showStatus('Authentication successful! Redirecting...', 'success');
                            setButtonLoading(false);
                            setTimeout(() => {{
                                window.location.href = result.redirect_url;
                            }}, 1000);
                        }} else {{
                            let errorMessage = 'Invalid email or password';
                            try {{
                                const errorData = await response.json();
                                if (errorData.detail) {{
                                    errorMessage = errorData.detail;
                                }}
                            }} catch (e) {{
                                // Use default error message
                            }}
                            showStatus(errorMessage, 'error');
                            setButtonLoading(false);
                        }}
                    }} catch (err) {{
                        showStatus('Network error. Please check your connection and try again.', 'error');
                        setButtonLoading(false);
                    }}
                }}

                // Keyboard navigation and button click handler
                document.addEventListener('DOMContentLoaded', function() {{
                    // Button click handler
                    document.getElementById('loginBtn').addEventListener('click', function(e) {{
                        e.preventDefault();
                        login();
                    }});

                    // Enter key on email -> focus password
                    document.getElementById('email').addEventListener('keypress', function(e) {{
                        if (e.key === 'Enter') {{
                            e.preventDefault();
                            document.getElementById('password').focus();
                        }}
                    }});

                    // Enter key on password -> submit
                    document.getElementById('password').addEventListener('keypress', function(e) {{
                        if (e.key === 'Enter') {{
                            e.preventDefault();
                            login();
                        }}
                    }});

                    // Focus email input on page load
                    document.getElementById('email').focus();
                }});
            </script>
        </body>
    </html>
    """)

@mcp.custom_route("/auth/syfthub/login", ["POST"])
async def syfthub_login(request: Request) -> JSONResponse:
    """
    Authenticate user via SyftHub and complete OAuth authorization flow.

    Validates credentials with SyftHub, retrieves user info and accounting
    credentials, stores the session, and generates OAuth authorization code.

    Args:
        request: FastAPI Request object containing JSON payload with:
                - email: User's email address (or username)
                - password: User's password
                - client_id: OAuth client identifier
                - redirect_uri: Client redirect URL
                - scope: Requested OAuth scopes (default: 'openid')
                - state: OAuth state parameter for CSRF protection
                - code_challenge: PKCE code challenge
                - code_challenge_method: PKCE challenge method

    Returns:
        JSONResponse: Authorization code and redirect URL if successful,
                     error message with appropriate status code if validation fails
    """
    try:
        data = await request.json()
        email = data.get("email", "").strip()
        password = data.get("password", "")
        client_id = data.get("client_id")
        redirect_uri = data.get("redirect_uri")
        scope = data.get("scope", "openid")
        state = data.get("state")
        code_challenge = data.get("code_challenge")
        code_challenge_method = data.get("code_challenge_method")

        # Validate required fields
        if not email or not password:
            return JSONResponse(
                {"error": "Email and password are required"},
                status_code=400
            )

        if not client_id or not redirect_uri:
            return JSONResponse(
                {"error": "Missing OAuth parameters"},
                status_code=400
            )

        logger.info(f"SyftHub login attempt for: {email} (password length: {len(password)})")

        try:
            # 1. Authenticate with SyftHub
            tokens = await syfthub.login(email, password)
            logger.info(f"SyftHub login successful for: {email}")

            # 2. Get user info from SyftHub
            user_info = await syfthub.get_user_info(tokens["access_token"])
            logger.info(f"Retrieved user info for: {user_info.get('email', email)}")

            # Use email from user_info if available (more reliable)
            user_email = user_info.get("email", email)

            # 3. Get accounting credentials from SyftHub
            accounting = await syfthub.get_accounting_credentials(tokens["access_token"])
            if accounting:
                logger.info(f"Retrieved accounting credentials for: {user_email}")
            else:
                logger.info(f"No accounting credentials found for: {user_email}")
                accounting = {}

            # 4. Store session
            syfthub_sessions[user_email] = {
                "tokens": tokens,
                "user_info": user_info,
                "accounting": accounting,
                "stored_at": datetime.utcnow()
            }
            logger.info(f"Stored SyftHub session for: {user_email}")

        except AuthenticationError as e:
            logger.warning(f"SyftHub authentication failed for {email}: {e}")
            return JSONResponse(
                {"error": "Invalid email or password"},
                status_code=401
            )
        except SyftHubError as e:
            logger.error(f"SyftHub error for {email}: {e}")
            return JSONResponse(
                {"error": "Authentication service error. Please try again."},
                status_code=503
            )

        # 5. Generate OAuth authorization code
        auth_code = f"code_{uuid.uuid4().hex}"

        auth_data = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "email": user_email,
            "code_challenge": code_challenge,
            "code_challenge_method": code_challenge_method,
            "expires_at": datetime.utcnow() + timedelta(minutes=10),
            "created_at": datetime.utcnow()
        }

        oauth_authorization_codes[auth_code] = auth_data
        logger.info(f"Generated authorization code for {user_email}: {auth_code[:8]}...")

        # 6. Build redirect URL
        params = {"code": auth_code}
        if state:
            params["state"] = state

        redirect_url = f"{redirect_uri}?{urlencode(params)}"
        return JSONResponse({"redirect_url": redirect_url})

    except Exception as e:
        logger.error(f"SyftHub login error: {e}")
        return JSONResponse({"error": "server_error"}, status_code=500)


@mcp.custom_route("/health", ["GET"])
async def health_check(request: Request) -> JSONResponse:
    """
    Health check endpoint for container orchestration.

    Returns the health status of the MCP server and its dependencies.
    """
    # Check SyftHub connectivity
    syfthub_healthy = await syfthub.check_health()

    return JSONResponse({
        "status": "healthy",
        "service": "mcp-server",
        "timestamp": datetime.utcnow().isoformat(),
        "dependencies": {
            "syfthub": "healthy" if syfthub_healthy else "unhealthy"
        }
    })

@mcp.custom_route("/oauth/token", ["POST"])
async def oauth_token(request: Request) -> JSONResponse:
    """
    OAuth 2.1 token exchange endpoint.

    Handles authorization code exchange for access tokens using PKCE verification.
    Generates JWT access tokens signed with RS256 algorithm.

    Args:
        request: FastAPI Request object containing form data with:
                - grant_type: Must be 'authorization_code'
                - code: Authorization code from /auth/otp/verify
                - redirect_uri: Must match original redirect URI
                - client_id: OAuth client identifier
                - code_verifier: PKCE code verifier for security

    Returns:
        JSONResponse: JWT access token, token type, and expiration if successful,
                     error message with appropriate status code if validation fails

    Note:
        Validates PKCE code challenge/verifier pair and generates signed JWT
        containing user email and OAuth claims.
    """
    try:
        form_data = await request.form()

        grant_type = form_data.get("grant_type")
        code = form_data.get("code")
        redirect_uri = form_data.get("redirect_uri")
        client_id = form_data.get("client_id")
        client_secret = form_data.get("client_secret")
        code_verifier = form_data.get("code_verifier")

        # Handle HTTP Basic Auth for client credentials
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Basic "):
            try:
                credentials = base64.b64decode(auth_header[6:]).decode('utf-8')
                basic_client_id, basic_client_secret = credentials.split(':', 1)
                if not client_id:
                    client_id = basic_client_id
                if not client_secret:
                    client_secret = basic_client_secret
            except Exception:
                pass

        if grant_type == "authorization_code":
            if not code or code not in oauth_authorization_codes:
                return JSONResponse({"error": "invalid_grant"}, status_code=400)

            auth_data = oauth_authorization_codes[code]

            # Check expiration
            if datetime.utcnow() > auth_data["expires_at"]:
                del oauth_authorization_codes[code]
                return JSONResponse({"error": "invalid_grant"}, status_code=400)

            # Validate client
            if client_id != auth_data["client_id"]:
                return JSONResponse({"error": "invalid_client"}, status_code=400)

            if client_id not in oauth_clients:
                return JSONResponse({"error": "invalid_client"}, status_code=400)

            client = oauth_clients[client_id]
            if client_secret != client["client_secret"]:
                return JSONResponse({"error": "invalid_client"}, status_code=400)

            # Validate PKCE if present
            if auth_data.get("code_challenge") and code_verifier:
                if not verify_pkce(code_verifier, auth_data["code_challenge"], auth_data.get("code_challenge_method", "S256")):
                    return JSONResponse({"error": "invalid_grant"}, status_code=400)

            # Generate tokens
            user_email = auth_data["email"]
            user_id = user_email  # Use email as user ID for simplicity

            # Access token claims
            access_token_claims = {
                "sub": user_id,
                "email": user_email,
                "scope": auth_data["scope"],
                "client_id": client_id
            }

            access_token = generate_jwt_token(access_token_claims, expires_in=3600)

            # ID token (for OpenID Connect)
            id_token_claims = {
                "sub": user_id,
                "email": user_email,
                "name": user_email,
                "aud": client_id
            }

            id_token = generate_jwt_token(id_token_claims, expires_in=3600)

            # Store access token
            token_data = {
                "access_token": access_token,
                "token_type": "Bearer",
                "expires_in": 3600,
                "scope": auth_data["scope"],
                "client_id": client_id,
                "user_email": user_email,
                "created_at": datetime.utcnow()
            }

            oauth_access_tokens[access_token] = token_data

            # Clean up authorization code
            del oauth_authorization_codes[code]

            logger.info(f"Issued access token for {user_email}")

            response = {
                "access_token": access_token,
                "token_type": "Bearer",
                "expires_in": 3600,
                "scope": auth_data["scope"]
            }

            # Include ID token for OpenID Connect
            if "openid" in auth_data["scope"]:
                response["id_token"] = id_token

            return JSONResponse(response)

        else:
            return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)

    except Exception as e:
        logger.error(f"Token endpoint error: {e}")
        return JSONResponse({"error": "server_error"}, status_code=500)

@mcp.custom_route("/oauth/userinfo", ["GET"])
async def oauth_userinfo(request: Request) -> JSONResponse:
    """
    OAuth 2.0 UserInfo endpoint for retrieving authenticated user information.

    Returns user profile data for valid access tokens following OAuth 2.0 specification.

    Args:
        request: FastAPI Request object with Authorization header containing
                'Bearer {access_token}'

    Returns:
        JSONResponse: User profile data including sub, email, name, and email_verified
                     if token is valid, error message with appropriate status code otherwise

    Note:
        Validates access token against oauth_access_tokens storage and returns
        standardized user claims for OpenID Connect compatibility.
    """
    try:
        auth_header = request.headers.get("authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse({"error": "invalid_token"}, status_code=401)

        access_token = auth_header[7:]  # Remove "Bearer " prefix

        if access_token not in oauth_access_tokens:
            return JSONResponse({"error": "invalid_token"}, status_code=401)

        token_data = oauth_access_tokens[access_token]

        return JSONResponse({
            "sub": token_data["user_email"],
            "email": token_data["user_email"],
            "name": token_data["user_email"],
            "email_verified": True
        })

    except Exception as e:
        logger.error(f"UserInfo endpoint error: {e}")
        return JSONResponse({"error": "server_error"}, status_code=500)

# User authentication helper functions
def get_user_info() -> Dict[str, Any]:
    """
    Extract user information from the current FastMCP authentication context.

    Retrieves user details from the active OAuth access token including email,
    user ID, client ID, scopes, and authentication metadata.

    Returns:
        Dict[str, Any]: Dictionary containing user information with keys:
                       - email: User's email address
                       - user_id: Unique user identifier
                       - client_id: OAuth client identifier
                       - scopes: List of authorized OAuth scopes
                       - timestamp: Current timestamp in ISO format
                       - source: Authentication source identifier
                       - authenticated: Boolean authentication status

    Note:
        Returns default values with authenticated=False if no valid token context
        is available or token extraction fails.
    """
    try:
        from fastmcp.server.dependencies import get_access_token

        access_token = get_access_token()

        if access_token and access_token.claims:
            user_email = (
                access_token.claims.get('email') or
                access_token.claims.get('sub') or
                access_token.client_id or
                'unknown'
            )
            user_id = access_token.claims.get('sub', access_token.client_id)

            return {
                "email": user_email,
                "user_id": user_id,
                "client_id": access_token.client_id,
                "scopes": access_token.scopes,
                "timestamp": datetime.now().isoformat(),
                "source": "self_hosted_oauth",
                "jwt_claims": access_token.claims
            }
        else:
            logger.warning("AccessToken found but no claims available")
            return {
                "email": "no_claims@fastmcp.dev",
                "user_id": "no_claims",
                "timestamp": datetime.now().isoformat(),
                "source": "no_claims"
            }

    except RuntimeError as e:
        logger.warning(f"No authentication context available: {e}")
        return {
            "email": "no_auth_context@fastmcp.dev",
            "user_id": "no_auth_context",
            "timestamp": datetime.now().isoformat(),
            "source": "no_context"
        }
    except Exception as e:
        logger.error(f"Error accessing authentication: {e}")
        return {
            "email": "auth_error@fastmcp.dev",
            "user_id": "auth_error",
            "timestamp": datetime.now().isoformat(),
            "source": "error",
            "error": str(e)
        }

def log_tool_usage(tool_name: str, params: Optional[Dict[str, Any]] = None, user_info: Optional[Dict[str, Any]] = None) -> None:
    """
    Log tool usage with comprehensive user and parameter information.

    Records tool invocation events with user context, parameters, and timestamps
    for audit and analytics purposes.

    Args:
        tool_name: Name of the MCP tool being invoked
        params: Optional dictionary of tool parameters passed by the client
        user_info: Optional user information dictionary; if None, will be
                  retrieved from current authentication context

    Note:
        Logs are written at INFO level and include event type, tool name,
        user identification, timestamp, and sanitized parameters.
    """
    if user_info is None:
        user_info = get_user_info()

    log_entry = {
        "event": "tool_used",
        "tool": tool_name,
        "user_email": user_info.get("email", "unknown"),
        "user_id": user_info.get("user_id", "unknown"),
        "source": user_info.get("source", "unknown"),
        "timestamp": user_info.get("timestamp", datetime.now().isoformat()),
        "parameters": params or {}
    }

    param_str = f" with params: {params}" if params else ""
    logger.info(f"🔧 TOOL_USAGE | User: {log_entry['user_email']} | Tool: '{tool_name}'{param_str}")
    logger.info(f"STRUCTURED_LOG: {log_entry}")

# ENHANCED MCP TOOLS WITH COMPREHENSIVE DESCRIPTIONS

def update_router_paths(syftbox_data: Dict[str, Dict[str, Dict]]) -> None:
    """
    Update the global router paths mapping with discovered routers.

    Builds RPC paths for each router based on their metadata, determining
    the appropriate service endpoint (search, chat, etc.) from enabled services.

    Args:
        syftbox_data: Nested dict {datasite: {router: metadata}}

    Note:
        Updates the global syftbox_router_paths dictionary in-place.
        Path format: datasite@email.com/app_data/router-name/rpc/{service_type}
    """
    global syftbox_router_paths

    for datasite_email, routers in syftbox_data.items():
        for router_name, router_metadata in routers.items():
            # Create the key: datasite/router
            router_key = f"{datasite_email}/{router_name}"

            # Extract enabled services to determine the RPC endpoint
            services = router_metadata.get('services', [])
            enabled_services = [s for s in services if s.get('enabled', False)]

            # Determine the primary service type (prefer search, then chat, then any)
            service_endpoint = 'search'  # Default to search
            for service in enabled_services:
                service_type = service.get('type', '').lower()
                if service_type == 'search':
                    service_endpoint = 'search'
                    break  # Prefer search if available
                elif service_type == 'chat':
                    service_endpoint = 'chat'
                elif service_type and not service_endpoint:
                    service_endpoint = service_type

            # Build the RPC path
            # Format: datasite@email.com/app_data/router-name/rpc/{service_endpoint}
            rpc_path = f"{datasite_email}/app_data/{router_name}/rpc/{service_endpoint}"

            # Update the global mapping
            syftbox_router_paths[router_key] = rpc_path

            logger.debug(f"Mapped router: {router_key} -> {rpc_path}")

    logger.info(f"Updated router paths mapping with {len(syftbox_router_paths)} entries")

# DISCOVERY & NETWORK TOOLS

@mcp.tool(
    name="discover_syfthub_endpoints",
    description="""
    Discover all available endpoints (models and data sources) in SyftHub.

    This tool queries the SyftHub Hub to find all publicly available endpoints:

    **Models (AI/ML Endpoints):**
    - Language models for text generation
    - Embedding models for semantic search
    - Specialized AI services

    **Data Sources (RAG Endpoints):**
    - Document collections for retrieval
    - Knowledge bases and datasets
    - Indexed content sources

    **Output includes:**
    - Endpoint path (owner/slug format, e.g., "alice/my-model")
    - Name and description
    - Type (MODEL or DATA_SOURCE)
    - Owner information
    - Connection status (URL configured or not)

    Use the discovered endpoints with the `chat_with_syfthub` tool to:
    - Query data sources for relevant information
    - Generate responses using models
    - Combine multiple sources in RAG queries
    """,
    tags={"discovery", "syfthub", "endpoints", "hub"},
    annotations={
        "title": "Discover SyftHub Endpoints",
        "readOnlyHint": True,
        "idempotentHint": True
    }
)
def discover_syfthub_endpoints() -> Dict[str, Any]:
    """
    List all available endpoints from SyftHub Hub.

    Uses the SyftHub SDK to browse public endpoints and returns
    structured information about available models and data sources.

    Returns:
        Dict with success status and lists of models and data sources
    """
    log_tool_usage("discover_syfthub_endpoints")

    if not SDK_AVAILABLE:
        return {
            "success": False,
            "error": "SyftHub SDK is not available. Please check the server configuration.",
            "models": [],
            "data_sources": [],
            "timestamp": datetime.now().isoformat()
        }

    user_email = get_current_user_email()
    if not user_email:
        return {
            "success": False,
            "error": "No authenticated user found. Please authenticate first.",
            "models": [],
            "data_sources": [],
            "timestamp": datetime.now().isoformat()
        }

    client = get_sdk_client_for_user(user_email)
    if not client:
        return {
            "success": False,
            "error": "Could not create SDK client. Please re-authenticate.",
            "models": [],
            "data_sources": [],
            "timestamp": datetime.now().isoformat()
        }

    try:
        models = []
        data_sources = []

        # Browse all public endpoints
        logger.info("Browsing SyftHub Hub for endpoints...")
        for endpoint in client.hub.browse():
            # Check if endpoint has a configured URL
            has_url = False
            endpoint_url = None
            for conn in endpoint.connect or []:
                if conn.enabled and conn.config and conn.config.get("url"):
                    has_url = True
                    endpoint_url = conn.config.get("url")
                    break

            entry = {
                "path": endpoint.path,
                "name": endpoint.name,
                "description": endpoint.description[:200] if endpoint.description else "",
                "owner": endpoint.owner_username or "unknown",
                "has_url": has_url,
                "url": endpoint_url,
                "slug": endpoint.slug,
                "tenant_name": endpoint.owner_username,
            }

            if endpoint.type == EndpointType.MODEL:
                models.append(entry)
            elif endpoint.type == EndpointType.DATA_SOURCE:
                data_sources.append(entry)

        # Format output as markdown
        output_lines = ["## Available SyftHub Endpoints\n"]

        if models:
            output_lines.append("### Models (AI/ML)\n")
            output_lines.append("| Path | Name | Description | Status |")
            output_lines.append("|------|------|-------------|--------|")
            for m in models:
                status = "✅ Ready" if m["has_url"] else "⚠️ No URL"
                desc = m["description"][:50] + "..." if len(m["description"]) > 50 else m["description"]
                output_lines.append(f"| `{m['path']}` | {m['name']} | {desc} | {status} |")
            output_lines.append("")

        if data_sources:
            output_lines.append("### Data Sources (RAG)\n")
            output_lines.append("| Path | Name | Description | Status |")
            output_lines.append("|------|------|-------------|--------|")
            for ds in data_sources:
                status = "✅ Ready" if ds["has_url"] else "⚠️ No URL"
                desc = ds["description"][:50] + "..." if len(ds["description"]) > 50 else ds["description"]
                output_lines.append(f"| `{ds['path']}` | {ds['name']} | {desc} | {status} |")
            output_lines.append("")

        if not models and not data_sources:
            output_lines.append("No endpoints found in SyftHub Hub.\n")

        summary = f"\n**Summary:** Found {len(models)} models and {len(data_sources)} data sources."
        output_lines.append(summary)

        logger.info(f"Discovered {len(models)} models and {len(data_sources)} data sources")

        return {
            "success": True,
            "formatted_output": "\n".join(output_lines),
            "models": models,
            "data_sources": data_sources,
            "total_endpoints": len(models) + len(data_sources),
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error discovering endpoints: {e}")
        return {
            "success": False,
            "error": f"Error discovering endpoints: {str(e)}",
            "models": [],
            "data_sources": [],
            "timestamp": datetime.now().isoformat()
        }

# DISTRIBUTED QUERY TOOLS

@mcp.tool(
    name="chat_with_syfthub",
    description="""
    Execute RAG (Retrieval-Augmented Generation) queries using SyftHub endpoints.

    This is the core tool for AI-powered conversations with SyftHub. It allows you to:

    **Query Capabilities:**
    - Send prompts to AI models with optional data source context
    - Retrieve relevant documents from data sources
    - Generate AI responses augmented with retrieved information
    - Combine multiple data sources for comprehensive answers

    **Required Parameters:**
    - `prompt`: Your question or instruction
    - `model`: Path to a model endpoint (e.g., "alice/gpt-model")

    **Optional Parameters:**
    - `data_sources`: List of data source paths for RAG (e.g., ["bob/docs", "carol/knowledge-base"])

    **How it works:**
    1. Retrieves relevant documents from specified data sources
    2. Sends your prompt + retrieved context to the model
    3. Returns the model's response with source attribution

    **Prerequisites:**
    1. Run `discover_syfthub_endpoints` to find available models and data sources
    2. Ensure selected endpoints have URLs configured (✅ Ready status)

    **Example Usage:**
    ```
    chat_with_syfthub(
        prompt="What are the latest trends in machine learning?",
        model="openai/gpt-4",
        data_sources=["research/arxiv-papers", "tech/github-trending"]
    )
    ```
    """,
    tags={"query", "syfthub", "rag", "chat", "ai"},
    annotations={
        "title": "Chat with SyftHub",
        "readOnlyHint": True,
        "idempotentHint": False
    }
)
def chat_with_syfthub(
    prompt: Annotated[str, Field(
        description="""
        Your question or instruction for the AI model.

        The prompt will be processed along with any retrieved context from data sources.
        Be specific and descriptive for best results.
        """,
        min_length=1,
        max_length=4000,
        examples=[
            "What are the latest developments in machine learning?",
            "Summarize the key findings from recent research papers",
            "Explain the concept of transformer architectures"
        ]
    )],
    model: Annotated[str, Field(
        description="""
        Path to the model endpoint in 'owner/slug' format.

        Examples:
        - 'alice/gpt-model' - A GPT-based language model
        - 'openai/gpt-4' - OpenAI's GPT-4 model
        - 'anthropic/claude' - Anthropic's Claude model

        Use discover_syfthub_endpoints to find available models.
        """,
        min_length=1,
        max_length=200,
        examples=["openai/gpt-4", "alice/my-model"]
    )],
    data_sources: Annotated[Optional[List[str]], Field(
        description="""
        Optional list of data source paths for RAG retrieval.

        Each path should be in 'owner/slug' format.

        Examples:
        - ['alice/documents'] - Single data source
        - ['alice/docs', 'bob/knowledge-base'] - Multiple sources

        Leave empty for pure generation without retrieval.
        """,
        default=None,
        max_length=10,
        examples=[
            ["alice/documents"],
            ["research/arxiv", "tech/github"]
        ]
    )] = None
) -> Dict[str, Any]:
    """
    Execute a RAG query using SyftHub's chat API via the Aggregator.

    Args:
        prompt: The user's question or instruction
        model: Path to the model endpoint (owner/slug format)
        data_sources: Optional list of data source paths for retrieval

    Returns:
        Dict containing the response, sources, and metadata
    """
    log_tool_usage("chat_with_syfthub", {
        "prompt_length": len(prompt),
        "model": model,
        "data_sources_count": len(data_sources) if data_sources else 0
    })

    if not SDK_AVAILABLE:
        return {
            "success": False,
            "error": "SyftHub SDK is not available. Please check the server configuration.",
            "prompt": prompt,
            "model": model,
            "timestamp": datetime.now().isoformat()
        }

    user_email = get_current_user_email()
    if not user_email:
        return {
            "success": False,
            "error": "No authenticated user found. Please authenticate first.",
            "prompt": prompt,
            "model": model,
            "timestamp": datetime.now().isoformat()
        }

    client = get_sdk_client_for_user(user_email)
    if not client:
        return {
            "success": False,
            "error": "Could not create SDK client. Please re-authenticate.",
            "prompt": prompt,
            "model": model,
            "timestamp": datetime.now().isoformat()
        }

    try:
        logger.info(f"Executing chat query with model={model}, data_sources={data_sources}")

        # Execute the chat completion via SDK
        response = client.chat.complete(
            prompt=prompt,
            model=model,
            data_sources=data_sources or []
        )

        # Format sources for output
        sources_info = []
        if response.sources:
            for source in response.sources:
                source_entry = {
                    "path": source.path,
                    "status": source.status.value if hasattr(source.status, 'value') else str(source.status),
                    "documents_retrieved": source.documents_retrieved,
                }
                if source.error_message:
                    source_entry["error_message"] = source.error_message
                sources_info.append(source_entry)

        # Format metadata
        metadata_info = {}
        if response.metadata:
            metadata_info = {
                "retrieval_time_ms": response.metadata.retrieval_time_ms,
                "generation_time_ms": response.metadata.generation_time_ms,
                "total_time_ms": response.metadata.total_time_ms,
            }

        logger.info(f"Chat query successful. Response length: {len(response.response)}")

        return {
            "success": True,
            "response": response.response,
            "sources": sources_info,
            "metadata": metadata_info,
            "prompt": prompt,
            "model": model,
            "data_sources_used": data_sources or [],
            "user": user_email,
            "timestamp": datetime.now().isoformat()
        }

    except AggregatorError as e:
        logger.error(f"Aggregator error in chat: {e}")
        return {
            "success": False,
            "error": f"Chat service error: {str(e)}",
            "prompt": prompt,
            "model": model,
            "timestamp": datetime.now().isoformat()
        }
    except EndpointResolutionError as e:
        logger.error(f"Endpoint resolution error: {e}")
        return {
            "success": False,
            "error": f"Could not resolve endpoint: {str(e)}. Please check that the model/data source paths are correct.",
            "prompt": prompt,
            "model": model,
            "timestamp": datetime.now().isoformat()
        }
    except SDKAuthError as e:
        logger.error(f"Authentication error in chat: {e}")
        return {
            "success": False,
            "error": "Authentication failed. Please re-authenticate with SyftHub.",
            "prompt": prompt,
            "model": model,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Unexpected error in chat: {e}")
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}",
            "prompt": prompt,
            "model": model,
            "timestamp": datetime.now().isoformat()
        }


# INTELLIGENT RAG WORKFLOW PROMPT

@mcp.prompt(
    name="ask",
    description="""
    Ask any question and get AI-powered answers using SyftHub's RAG capabilities.

    This prompt orchestrates a complete autonomous workflow:
    1. Discovers all available models and data sources using discover_syfthub_endpoints
    2. Selects the most appropriate model and data sources for your query
    3. Executes a RAG query using chat_with_syfthub
    4. Synthesizes results into a comprehensive response

    Simply ask your question - the AI handles everything else automatically.
    """,
    tags={"ask", "research", "autonomous", "rag"}
)
def ask(
    query: Annotated[str, Field(
        description="The user's question or query to research across data sources",
        examples=[
            "What are the latest developments in machine learning?",
            "Tell me about climate change research trends",
            "What are the most popular Python libraries this year?"
        ]
    )]
) -> str:
    """
    Autonomous RAG workflow prompt that guides the LLM through the complete process.

    This prompt template instructs the LLM to:
    1. First call discover_syfthub_endpoints to get available models and data sources
    2. Select the most relevant model and data sources for the query
    3. Call chat_with_syfthub with selected endpoints
    4. Provide a comprehensive response

    Args:
        query: The user's research question

    Returns:
        str: Prompt template for autonomous workflow execution
    """
    return f"""
You are an intelligent research assistant with access to SyftHub's AI models and data sources. Your task is to autonomously answer the following query using RAG (Retrieval-Augmented Generation).

**User Query:** "{query}"

**Autonomous Workflow Instructions:**

1. **DISCOVER AVAILABLE ENDPOINTS**
   - First, call the `discover_syfthub_endpoints` tool
   - This will show you available models (for generation) and data sources (for retrieval)
   - Note which endpoints have "Ready" status (URL configured)

2. **SELECT MODEL AND DATA SOURCES**
   - Choose a model with "Ready" status for response generation
   - Select 1-3 relevant data sources based on:
     - Topical relevance to the query
     - "Ready" status (must have URL configured)
     - Description matching the query domain

3. **EXECUTE RAG QUERY**
   - Call `chat_with_syfthub` with:
     - `prompt`: The user's query
     - `model`: The selected model path (e.g., "alice/gpt-model")
     - `data_sources`: List of selected data source paths (optional)
   - This will retrieve relevant documents and generate an AI response

4. **PRESENT RESULTS**
   - Share the AI-generated response with the user
   - Include information about which sources were used
   - Note any retrieval statistics if available

**IMPORTANT GUIDELINES:**
- Be autonomous: Don't ask the user for additional input during this process
- Handle missing endpoints: If no suitable model/data sources are available, explain this clearly
- Be transparent: Tell the user which model and sources you're using
- Handle errors gracefully: If an endpoint fails, explain what happened

Begin the workflow now by calling `discover_syfthub_endpoints`.
"""

logger.info("SyftHub MCP Server with Integrated OAuth 2.1 Server initialized")
logger.info(f"Server will be available at: {API_BASE_URL}")
logger.info(f"OAuth endpoints available at: {OAUTH_ISSUER}/oauth/*")
logger.info(f"JWKS available at: {OAUTH_ISSUER}/.well-known/jwks.json")


# Factory function for uvicorn
def create_app():
    """
    Factory function to create the ASGI application.
    Used by uvicorn with --factory flag.
    """
    return mcp.http_app()


# Entry point for direct execution
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("MCP_PORT", "8002"))
    uvicorn.run(
        create_app(),
        host="0.0.0.0",
        port=port,
        log_level=os.getenv("LOG_LEVEL", "info").lower()
    )
