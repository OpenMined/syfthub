"""
Research Agent — LLM + tools, zero extra dependencies.

Configure via .env (two fields only):
  API_KEY      — leave empty for local Ollama; OpenAI: sk-…; Anthropic: sk-ant-…
  SYSTEM_PROMPT — optional custom instructions (falls back to built-in default)

Provider is detected automatically from the API key prefix:
  (empty)   → Ollama  at http://localhost:11434/v1, model llama3.2
  sk-ant-…  → Anthropic at https://api.anthropic.com/v1, model claude-3-5-haiku-20241022
  sk-…/any  → OpenAI  at https://api.openai.com/v1,    model gpt-4o-mini
"""

import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request

THIS_DIR = os.path.dirname(os.path.abspath(__file__))


# ── Provider auto-detection ────────────────────────────────────────────────────

def _detect_backend(key: str):
    """Return (base_url, bearer_token, default_model) from the API key prefix."""
    if not key:
        return "http://localhost:11434/v1", "", "llama3.2"
    if key.startswith("sk-ant-"):
        return "https://api.anthropic.com/v1", key, "claude-3-5-haiku-20241022"
    return "https://api.openai.com/v1", key, "gpt-4o-mini"


_RAW_KEY = os.environ.get("API_KEY", "")
_default_url, _default_token, _default_model = _detect_backend(_RAW_KEY)

API_TOKEN = _default_token
BASE_URL  = os.environ.get("OPENAI_BASE_URL", _default_url).rstrip("/")
MODEL     = os.environ.get("AGENT_MODEL", _default_model)


# ── Skills loader ──────────────────────────────────────────────────────────────

def load_skills(skills_dir: str) -> str:
    if not os.path.isdir(skills_dir):
        return ""
    contents = []
    for root, dirs, files in os.walk(skills_dir):
        dirs.sort()
        for fname in sorted(files):
            if fname.upper() == "SKILL.MD":
                path = os.path.join(root, fname)
                try:
                    with open(path) as f:
                        text = f.read().strip()
                    if text:
                        contents.append(text)
                except OSError:
                    pass
    return "\n\n---\n\n".join(contents)


_SKILLS = load_skills(os.path.join(THIS_DIR, "skills"))

_DEFAULT_SYSTEM = (
    "You are a helpful assistant with access to tools. "
    "Use them to answer questions accurately and thoroughly."
)

_BASE_SYSTEM = os.environ.get("SYSTEM_PROMPT") or _DEFAULT_SYSTEM

SYSTEM = (
    f"{_BASE_SYSTEM}\n\n# Skills & Knowledge\n\n{_SKILLS}"
    if _SKILLS else _BASE_SYSTEM
)


# ── Tools ──────────────────────────────────────────────────────────────────────

def run_command(command: str, timeout: int = 30) -> str:
    try:
        r = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=timeout)
        return (r.stdout + r.stderr).strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return f"Timed out after {timeout}s"
    except Exception as e:
        return f"Error: {e}"


def read_file(path: str) -> str:
    try:
        with open(os.path.expanduser(path)) as f:
            return f.read()
    except Exception as e:
        return f"Error: {e}"


def write_file(path: str, content: str) -> str:
    try:
        p = os.path.expanduser(path)
        os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
        with open(p, "w") as f:
            f.write(content)
        return f"Wrote {len(content)} chars to {p}"
    except Exception as e:
        return f"Error: {e}"


def fetch_url(url: str) -> str:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "agent/1.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read().decode("utf-8", errors="replace")
        body = re.sub(r"<[^>]+>", " ", body)
        return re.sub(r"\s+", " ", body).strip()[:4000]
    except Exception as e:
        return f"Error: {e}"


TOOLS = {
    "run_command": {
        "fn": run_command,
        "description": "Run a bash shell command and return its stdout/stderr.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute"},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default 30)"},
            },
            "required": ["command"],
        },
    },
    "read_file": {
        "fn": read_file,
        "description": "Read and return the contents of a file.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path (~ supported)"},
            },
            "required": ["path"],
        },
    },
    "write_file": {
        "fn": write_file,
        "description": "Write content to a file, creating parent directories if needed.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path (~ supported)"},
                "content": {"type": "string", "description": "Content to write"},
            },
            "required": ["path", "content"],
        },
    },
    "fetch_url": {
        "fn": fetch_url,
        "description": "Fetch a URL and return its text content (HTML tags stripped).",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to fetch"},
            },
            "required": ["url"],
        },
    },
}

TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": name,
            "description": spec["description"],
            "parameters": spec["parameters"],
        },
    }
    for name, spec in TOOLS.items()
]


def call_tool(name: str, arguments: dict) -> str:
    spec = TOOLS.get(name)
    if not spec:
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        return str(spec["fn"](**arguments))
    except Exception as e:
        return f"Error: {e}"


# ── LLM ───────────────────────────────────────────────────────────────────────

def complete(messages: list) -> dict:
    headers = {"Content-Type": "application/json"}
    if API_TOKEN:
        headers["Authorization"] = f"Bearer {API_TOKEN}"

    payload = json.dumps({
        "model": MODEL,
        "messages": [{"role": "system", "content": SYSTEM}] + messages,
        "tools": TOOL_DEFS,
    }).encode()

    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions",
        data=payload,
        headers=headers,
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"API error {e.code}: {e.read().decode()}") from e

    choice = data["choices"][0]
    msg = choice["message"]

    tool_calls = []
    for tc in msg.get("tool_calls") or []:
        try:
            args = json.loads(tc["function"]["arguments"])
        except Exception:
            args = {}
        tool_calls.append({"id": tc["id"], "name": tc["function"]["name"], "arguments": args})

    return {
        "finish_reason": choice.get("finish_reason", "stop"),
        "content": msg.get("content") or "",
        "tool_calls": tool_calls,
    }


# ── Agent loop ────────────────────────────────────────────────────────────────

def run_turn(session, messages: list, prompt: str):
    messages.append({"role": "user", "content": prompt})
    session.send_status("thinking", "Thinking…")

    for _ in range(15):
        result = complete(messages)

        if not result["tool_calls"]:
            if result["content"]:
                session.send_message(result["content"])
            messages.append({"role": "assistant", "content": result["content"]})
            break

        assistant_msg: dict = {"role": "assistant", "tool_calls": [
            {
                "id": tc["id"],
                "type": "function",
                "function": {"name": tc["name"], "arguments": json.dumps(tc["arguments"])},
            }
            for tc in result["tool_calls"]
        ]}
        if result["content"]:
            assistant_msg["content"] = result["content"]
        messages.append(assistant_msg)

        for tc in result["tool_calls"]:
            session.send_tool_call(tool_name=tc["name"], arguments=tc["arguments"], tool_call_id=tc["id"])
            session.send_status("running", f"Running {tc['name']}…")
            t0 = time.time()
            output = call_tool(tc["name"], tc["arguments"])
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": output})
            session.send_tool_result(
                tool_call_id=tc["id"], status="success",
                result=output, duration_ms=int((time.time() - t0) * 1000),
            )

        session.send_status("thinking", "Processing results…")


# ── Entry point ───────────────────────────────────────────────────────────────

def handler(session):
    messages = []
    run_turn(session, messages, session.prompt)

    while True:
        resp = session.request_input("Anything else? (type 'done' to end)")
        content = resp.get("content", "").strip()
        if not content or content.lower() in ("done", "exit", "quit", "bye", "no"):
            session.send_message("Session ended. Start a new one anytime!")
            break
        run_turn(session, messages, content)
