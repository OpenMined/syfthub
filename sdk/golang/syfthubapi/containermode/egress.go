package containermode

// Egress-broker contract shared between the host provisioner (desktop), the
// container spec builder, and the in-container relay (runner/server.py).
//
// Flow: the handler reaches the broker at http://127.0.0.1:<EgressLoopbackPort>;
// server.py's keyless relay listens there and forwards every byte to the host
// broker over the bind-mounted AF_UNIX socket at EgressGuestSocket. The real
// credential is injected on the host side; nothing secret lives in the container.
const (
	// EgressGuestSocket is the in-container path the host broker socket is
	// bind-mounted to. server.py reads its actual path from EnvEgressSock.
	EgressGuestSocket = "/run/egress.sock"

	// EgressLoopbackPort is the container-loopback port the relay listens on.
	// Base URLs injected into the handler point here.
	EgressLoopbackPort = "8788"

	// EnvEgressPort / EnvEgressSock are read by server.py (NOT forwarded to the
	// bwrap child) to start the relay. Absent ⇒ no relay (egress disabled).
	// Declared in runner/_protocol.py and pinned by TestProtocolDrift.
	EnvEgressPort = "SYFT_EGRESS_PORT"
	EnvEgressSock = "SYFT_EGRESS_SOCK"

	// EgressMCPPath is the broker path prefix under which per-endpoint MCP tool
	// servers are routed. The handler reaches a server at
	// http://127.0.0.1:<EgressLoopbackPort><EgressMCPPath>/<server-name>/ —
	// the broker swaps in the server's host-held credential and forwards.
	EgressMCPPath = "/mcp"

	// EnvMCPBaseURL / EnvMCPServers are HANDLER-VISIBLE (unlike the relay vars):
	// they tell the runner where brokered MCP tool servers live
	// (http://127.0.0.1:<port>/mcp) and which server names are exposed
	// (comma-separated). The runner builds its own MCP client config from these;
	// no credential is involved — the broker injects it host-side. Set only when
	// the endpoint exposes at least one MCP server. Declared in
	// runner/_protocol.py and pinned by TestProtocolDrift.
	EnvMCPBaseURL = "SYFT_MCP_BASE_URL"
	EnvMCPServers = "SYFT_MCP_SERVERS"
)
