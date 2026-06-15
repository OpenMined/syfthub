"""Unit tests for the stdlib MCP client (_mcp.py).

Stubs the broker endpoint with a tiny http.server returning canned JSON-RPC, so
this verifies the client's discovery/dispatch/result-flattening logic. The wire
contract (that the real bridge answers bare JSON-RPC POSTs in this shape) is
verified Go-side in mcpbridge/rawhttp_test.go.

Run: python3 -m unittest _mcp_test
"""

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

import _mcp


class _StubHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # silence
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        req = json.loads(self.rfile.read(length))
        method = req.get("method")
        # Path is /<server>; route per server name to prove namespacing.
        if method == "tools/list":
            result = {"tools": [{
                "name": "search",
                "description": "Search the issue tracker.",
                "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}}},
            }]}
        elif method == "tools/call":
            args = req["params"]["arguments"]
            result = {"content": [{"type": "text", "text": f"found: {args.get('q')}"}]}
        else:
            result = {}
        body = json.dumps({"jsonrpc": "2.0", "id": req.get("id"), "result": result}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class MCPClientTest(unittest.TestCase):
    def setUp(self):
        self.srv = HTTPServer(("127.0.0.1", 0), _StubHandler)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def test_discover_and_dispatch(self):
        import os
        os.environ["SYFT_MCP_BASE_URL"] = f"http://127.0.0.1:{self.port}"
        os.environ["SYFT_MCP_SERVERS"] = "linear,github"
        try:
            defs, dispatch = _mcp.discover()
        finally:
            del os.environ["SYFT_MCP_BASE_URL"]
            del os.environ["SYFT_MCP_SERVERS"]

        names = sorted(d["function"]["name"] for d in defs)
        self.assertEqual(names, ["mcp__github__search", "mcp__linear__search"])
        # Schema is passed through verbatim.
        self.assertEqual(
            defs[0]["function"]["parameters"]["properties"]["q"]["type"], "string"
        )
        # Dispatch routes to the namespaced server and flattens text content.
        out = dispatch["mcp__linear__search"]({"q": "bug"})
        self.assertEqual(out, "found: bug")

    def test_no_config_returns_empty(self):
        import os
        os.environ.pop("SYFT_MCP_BASE_URL", None)
        os.environ.pop("SYFT_MCP_SERVERS", None)
        defs, dispatch = _mcp.discover()
        self.assertEqual(defs, [])
        self.assertEqual(dispatch, {})

    def test_result_flattening_marks_errors(self):
        self.assertEqual(
            _mcp._result_to_text({"content": [{"type": "text", "text": "x"}]}), "x"
        )
        self.assertTrue(
            _mcp._result_to_text(
                {"isError": True, "content": [{"type": "text", "text": "boom"}]}
            ).startswith("(tool error)")
        )
        self.assertEqual(_mcp._result_to_text({"content": []}), "(no output)")


if __name__ == "__main__":
    unittest.main()
