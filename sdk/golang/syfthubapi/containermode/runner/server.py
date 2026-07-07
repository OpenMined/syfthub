"""Stdlib HTTP server for container-based endpoint execution."""
import json
import sys
import os
import importlib.util
import traceback
import logging
import inspect
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from functools import partial

from .session import SessionManager
from .policy import check_policies

logger = logging.getLogger("container_runner")


def load_handler(handler_path: str):
    """Dynamically import runner.py and return the handler function."""
    if not os.path.isfile(handler_path):
        raise FileNotFoundError(f"Handler not found: {handler_path}")

    spec = importlib.util.spec_from_file_location("runner", handler_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module from {handler_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules["runner"] = module
    spec.loader.exec_module(module)

    # Look for 'handler' function (convention from file-based endpoints)
    if hasattr(module, "handler"):
        return module.handler
    # Also try 'query' for data sources, 'complete' for models
    for name in ("query", "complete", "run"):
        if hasattr(module, name):
            return getattr(module, name)
    raise RuntimeError(f"No handler function found in {handler_path}")


def _call_handler(handler, endpoint_type: str, executor_input: dict):
    """Call the handler with the appropriate signature based on endpoint type.

    Tries multiple call signatures to be flexible with user code.
    """
    context = executor_input.get("context", {})
    messages = executor_input.get("messages", [])
    query = executor_input.get("query", "")

    if endpoint_type == "model":
        # Try handler(context, messages) first, then handler(messages)
        try:
            sig = inspect.signature(handler)
            param_count = len(sig.parameters)
        except (ValueError, TypeError):
            param_count = -1

        if param_count >= 2:
            return handler(context, messages)
        return handler(messages)

    elif endpoint_type == "data_source":
        # Try handler(context, query) first, then handler(query)
        try:
            sig = inspect.signature(handler)
            param_count = len(sig.parameters)
        except (ValueError, TypeError):
            param_count = -1

        if param_count >= 2:
            return handler(context, query)
        return handler(query)

    else:
        # Generic: pass the full input
        return handler(executor_input)


class RequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the container runner."""

    def __init__(self, *args, handler=None, session_manager=None, **kwargs):
        self._handler = handler
        self._session_manager = session_manager
        super().__init__(*args, **kwargs)

    def log_message(self, format, *args):
        """Route access logs through the logging module."""
        logger.debug(format, *args)

    def _send_json(self, status_code: int, data: dict):
        """Send a JSON response."""
        body = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        """Read and parse JSON from request body."""
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            return {}
        raw = self.rfile.read(content_length)
        return json.loads(raw)

    def _parse_path(self):
        """Parse the request path into components."""
        # Strip query string
        path = self.path.split("?")[0]
        # Split and filter empty segments
        return [s for s in path.split("/") if s]

    def do_GET(self):
        """Handle GET requests."""
        parts = self._parse_path()

        # GET /health
        if parts == ["health"]:
            self._handle_health()
            return

        # GET /session/{id}/events
        if (
            len(parts) == 3
            and parts[0] == "session"
            and parts[2] == "events"
        ):
            self._handle_session_events(parts[1])
            return

        self._send_json(404, {"error": "not found"})

    def do_POST(self):
        """Handle POST requests."""
        parts = self._parse_path()

        # POST /execute
        if parts == ["execute"]:
            self._handle_execute()
            return

        # POST /session/start
        if parts == ["session", "start"]:
            self._handle_session_start()
            return

        # POST /session/{id}/message
        if (
            len(parts) == 3
            and parts[0] == "session"
            and parts[2] == "message"
        ):
            self._handle_session_message(parts[1])
            return

        self._send_json(404, {"error": "not found"})

    def do_DELETE(self):
        """Handle DELETE requests."""
        parts = self._parse_path()

        # DELETE /session/{id}
        if len(parts) == 2 and parts[0] == "session":
            self._handle_session_cancel(parts[1])
            return

        self._send_json(404, {"error": "not found"})

    # ---- Route handlers ----

    def _handle_health(self):
        """GET /health - always returns 200."""
        self._send_json(200, {"status": "ok"})

    def _handle_execute(self):
        """POST /execute - execute handler (one-shot for model/data_source)."""
        try:
            executor_input = self._read_json()
        except (json.JSONDecodeError, ValueError) as e:
            self._send_json(400, {"success": False, "error": str(e)})
            return

        # Policy check
        policy_result = check_policies(executor_input)
        if policy_result and not policy_result.get("allowed", True):
            self._send_json(
                200,
                {
                    "success": False,
                    "policy_result": policy_result,
                },
            )
            return

        # Execute handler
        endpoint_type = executor_input.get("type", "model")
        try:
            result = _call_handler(
                self._handler, endpoint_type, executor_input
            )
            self._send_json(
                200,
                {
                    "success": True,
                    "result": result,
                    "policy_result": policy_result,
                },
            )
        except Exception as e:
            logger.error(
                "Handler execution failed: %s", traceback.format_exc()
            )
            self._send_json(
                200,
                {
                    "success": False,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )

    def _handle_session_start(self):
        """POST /session/start - start an agent session."""
        try:
            body = self._read_json()
        except (json.JSONDecodeError, ValueError) as e:
            self._send_json(400, {"success": False, "error": str(e)})
            return

        session_id = body.get("session_id", "")
        if not session_id:
            self._send_json(
                400,
                {"success": False, "error": "session_id is required"},
            )
            return

        prompt = body.get("prompt", "")
        messages = body.get("messages", [])
        config = body.get("config", {})

        try:
            session = self._session_manager.start_session(
                session_id, prompt, messages, config
            )
            self._send_json(
                200,
                {"success": True, "session_id": session.id},
            )
        except Exception as e:
            logger.error(
                "Failed to start session: %s", traceback.format_exc()
            )
            self._send_json(
                500,
                {"success": False, "error": str(e)},
            )

    def _handle_session_events(self, session_id: str):
        """GET /session/{id}/events - SSE stream of agent events."""
        session = self._session_manager.get_session(session_id)
        if session is None:
            self._send_json(
                404, {"error": f"session {session_id} not found"}
            )
            return

        # Set SSE headers
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        try:
            while True:
                # Block waiting for events with a timeout so we can
                # detect closed connections
                try:
                    event = session.event_queue.get(timeout=1.0)
                except Exception:
                    # queue.Empty — just loop and check again
                    if session.is_done():
                        break
                    continue

                # Sentinel value signals end of stream
                if event is None:
                    break

                # Format as SSE
                event_type = event.get("type", "message")
                event_data = json.dumps(event.get("data", {}))
                event_id = event.get("id", 0)

                sse_message = (
                    f"event: {event_type}\n"
                    f"data: {event_data}\n"
                    f"id: {event_id}\n"
                    f"\n"
                )
                self.wfile.write(sse_message.encode("utf-8"))
                self.wfile.flush()

        except (BrokenPipeError, ConnectionResetError):
            logger.info(
                "SSE connection closed for session %s", session_id
            )
        except Exception:
            logger.error(
                "SSE stream error for session %s: %s",
                session_id,
                traceback.format_exc(),
            )

    def _handle_session_message(self, session_id: str):
        """POST /session/{id}/message - deliver message to agent session."""
        try:
            body = self._read_json()
        except (json.JSONDecodeError, ValueError) as e:
            self._send_json(400, {"success": False, "error": str(e)})
            return

        delivered = self._session_manager.deliver_message(
            session_id, body
        )
        if delivered:
            self._send_json(200, {"success": True})
        else:
            self._send_json(
                404,
                {
                    "success": False,
                    "error": f"session {session_id} not found or queue full",
                },
            )

    def _handle_session_cancel(self, session_id: str):
        """DELETE /session/{id} - cancel an agent session."""
        cancelled = self._session_manager.cancel_session(session_id)
        if cancelled:
            self._send_json(200, {"success": True})
        else:
            self._send_json(
                404,
                {
                    "success": False,
                    "error": f"session {session_id} not found",
                },
            )


class ContainerRunnerServer:
    """Main server that loads the handler and runs the HTTP server."""

    def __init__(self, handler_path: str, host: str, port: int):
        self.handler = load_handler(handler_path)
        self.session_manager = SessionManager(self.handler)
        self.host = host
        self.port = port

    def run(self):
        handler_class = partial(
            RequestHandler,
            handler=self.handler,
            session_manager=self.session_manager,
        )
        class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
            daemon_threads = True

        server = ThreadedHTTPServer((self.host, self.port), handler_class)
        logger.info(
            "Container runner listening on %s:%d", self.host, self.port
        )
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            logger.info("Shutting down container runner...")
            self.session_manager.cancel_all()
            server.shutdown()
