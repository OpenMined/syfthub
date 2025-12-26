# FastMCP Server with SyftBox Integration

A comprehensive FastMCP server implementation featuring integrated OAuth 2.1 authentication and SyftBox API integration.

## 🚀 Features

- **Consolidated Architecture**: Single-server deployment combining MCP protocol and OAuth 2.1 authentication
- **SyftBox Integration**: Built-in OTP authentication flow with automatic token management
- **Secure Token Storage**: Automatic capture and storage of SyftBox access/refresh tokens
- **Seamless API Access**: Existing tools automatically use stored tokens for SyftBox API calls
- **Real-time Authentication**: Complete OAuth 2.1 with PKCE flow implementation

## 📁 Project Structure

```
├── echo.py              # Main FastMCP server with integrated OAuth & SyftBox
├── syftbox_client.py    # SyftBox API client for OTP authentication
├── fastmcp.json         # Server configuration
├── pyproject.toml       # Dependencies
└── README_OAuth.md      # Legacy OAuth documentation
```

## 🔧 Quick Start

1. **Install Dependencies**:
   ```bash
   uv sync
   ```

2. **Start Server**:
   ```bash
   uv run fastmcp run
   ```

3. **Access Server**:
   - **MCP Endpoint**: `http://localhost:8004/mcp`
   - **OAuth Flow**: `http://localhost:8004/oauth/authorize`
   - **JWKS**: `http://localhost:8004/.well-known/jwks.json`

## 🔐 Authentication Flow

1. **OAuth 2.1 Authorization**: Client initiates OAuth flow with PKCE
2. **SyftBox OTP**: User enters email and receives OTP from SyftBox
3. **Token Capture**: Server automatically stores SyftBox access/refresh tokens
4. **Seamless Integration**: Tools automatically use stored tokens for API calls

## 🛠️ Available Tools

### Core Tools
- `echo_tool` - Echo input text
- `list_data_sources` - List available data sources (includes SyftBox sources)
- `build_context` - Build context from data sources with SyftBox integration

### SyftBox Data Sources
- `syftbox_profile` - Fetch user profile using stored tokens
- `syftbox_api:/endpoint` - Access any SyftBox API endpoint

## 📊 Usage Examples

```bash
# List all data sources (includes SyftBox integration)
list_data_sources()

# Fetch SyftBox user profile (uses stored tokens automatically)
build_context(["syftbox_profile"])

# Custom SyftBox API call (uses stored tokens automatically)
build_context(["syftbox_api:/api/datasets"])
```

## 🔑 Environment Variables

```bash
OAUTH_ISSUER=http://localhost:8004
OAUTH_AUDIENCE=fastmcp-api
API_BASE_URL=http://localhost:8004
```

## 🏗️ Architecture

- **FastMCP Framework**: Modern MCP server implementation
- **OAuth 2.1 + PKCE**: Secure authorization with proof key
- **JWT Tokens**: RS256 signed tokens with JWKS endpoint
- **SyftBox Client**: OTP authentication integration
- **Token Management**: Automatic storage and refresh handling

## 📖 Learn More

- [FastMCP Documentation](https://gofastmcp.com/)
- [MCP Protocol](https://modelcontextprotocol.io/)
- [OAuth 2.1 Specification](https://datatracker.ietf.org/doc/html/draft-ietf-oauth-v2-1)

---
*Enhanced FastMCP server with integrated SyftBox authentication and API access.*
