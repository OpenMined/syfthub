#!/usr/bin/env python3
"""
Run FastMCP server with HTTPS SSL configuration
"""
import uvicorn
from server import mcp

if __name__ == "__main__":
    # Create ASGI app from FastMCP
    app = mcp.http_app()

    # Run with SSL certificates
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=443,
        ssl_keyfile="/home/ubuntu/server.key",
        ssl_certfile="/home/ubuntu/server.crt",
        log_level="info"
    )
