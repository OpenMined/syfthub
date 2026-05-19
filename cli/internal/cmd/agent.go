package cmd

import (
	"bufio"
	"context"
	"fmt"
	"os"
	"os/signal"
	"path/filepath"
	"strings"
	"syscall"

	"github.com/spf13/cobra"
	"golang.org/x/sync/errgroup"

	"github.com/OpenMined/syfthub/cli/internal/clientutil"
	"github.com/OpenMined/syfthub/cli/internal/config"
	"github.com/OpenMined/syfthub/cli/internal/output"
	"github.com/openmined/syfthub/sdk/golang/agenttypes"
	"github.com/openmined/syfthub/sdk/golang/syfthub"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/transport"
)

var (
	agentAggregator        string
	agentAttachPaths       []string
	agentSaveAttachmentsTo string
)

var agentCmd = &cobra.Command{
	Use:   "agent <endpoint> <prompt>",
	Short: "Start an interactive agent session",
	Long: `Start an interactive agent session with an agent endpoint.

Opens a bidirectional session where the agent can think, call tools,
request input, and send messages. You can send follow-up messages
when the agent pauses for input.

The session is a direct peer-to-peer connection over NATS:
  CLI → NATS → host → agent handler
The hub mints the session tokens; no aggregator relays the traffic, so
the prompt and the agent's replies are end-to-end encrypted.

Tool results are collapsed by default. Type /expand to see the full
output of the last tool call, or /expand N to expand tool call #N.

Examples:

    syft agent alice/research-agent "Summarize recent ML papers"
    syft agent bob/code-assistant "Help me refactor this function"`,
	Args: cobra.ExactArgs(2),
	RunE: runAgent,
}

func init() {
	agentCmd.Flags().StringVarP(&agentAggregator, "aggregator", "a", "", "Aggregator alias or URL (unused for agent sessions; kept for compatibility)")
	agentCmd.Flags().StringSliceVar(&agentAttachPaths, "attach", nil, "File(s) to attach to the prompt (repeat or comma-separate). Files up to 64 KiB ride inline; larger files are not yet supported on the direct path.")
	agentCmd.Flags().StringVar(&agentSaveAttachmentsTo, "save-attachments-to", "", "Directory to save inbound agent attachments (defaults to current dir)")
}

// ── Tool result rendering ──────────────────────────────────────────────────

const (
	previewLines = 3
	previewWidth = 120
)

// toolEntry stores a tool call + result pair for expand/collapse.
type toolEntry struct {
	index  int
	name   string
	args   string
	status string
	result string
}

// formatPreview returns a truncated preview of a tool result.
func (t *toolEntry) formatPreview() string {
	raw := t.result
	lines := strings.Split(raw, "\n")

	// Flatten single-line result
	if len(lines) == 1 && len(raw) <= previewWidth {
		return raw
	}

	var preview []string
	for i, line := range lines {
		if i >= previewLines {
			break
		}
		if len(line) > previewWidth {
			line = line[:previewWidth-1] + "…"
		}
		preview = append(preview, line)
	}

	hidden := len(lines) - previewLines
	if hidden > 0 {
		preview = append(preview, fmt.Sprintf("\033[2m   ⋯ %d more lines (/expand %d to show all)\033[0m", hidden, t.index))
	} else if len(raw) > previewWidth {
		preview = append(preview, fmt.Sprintf("\033[2m   ⋯ truncated (/expand %d to show all)\033[0m", t.index))
	}

	return strings.Join(preview, "\n")
}

// printFull prints the complete tool call + result.
func (t *toolEntry) printFull() {
	fmt.Printf("\033[33m── Tool #%d: %s ──\033[0m\n", t.index, t.name)
	if t.args != "" {
		fmt.Printf("\033[2mArgs: %s\033[0m\n", t.args)
	}
	fmt.Printf("\033[2mStatus: %s\033[0m\n", t.status)
	fmt.Println(t.result)
	fmt.Printf("\033[33m── end ──\033[0m\n")
}

// ── Main ───────────────────────────────────────────────────────────────────

func runAgent(_ *cobra.Command, args []string) error {
	endpoint := args[0]
	prompt := args[1]

	parts := strings.SplitN(endpoint, "/", 2)
	if len(parts) != 2 || parts[0] == "" || parts[1] == "" {
		return fmt.Errorf("endpoint must be in 'owner/slug' format, got: %s", endpoint)
	}
	owner, slug := parts[0], parts[1]

	cfg := config.Load()

	fail := func(msg string, err error) error {
		output.Error("%s: %v", msg, err)
		return err
	}

	client, err := clientutil.NewClient(cfg, agentAggregator, 0)
	if err != nil {
		return fail("Failed to create client", err)
	}
	defer client.Close()

	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()

	fmt.Printf("Connecting to %s...\n", endpoint)

	// Load (or generate) this CLI's persistent X25519 identity key — the host
	// encrypts the agent's reply stream to it.
	identityKey, err := transport.LoadOrGenerateKey(filepath.Join(config.ConfigDir, "identity.key"))
	if err != nil {
		return fail("Failed to load identity key", err)
	}

	// Resolve the credentials the direct dial needs: NATS connection details,
	// the reply channel, the satellite token, and the host's encryption key.
	// The four hub lookups are independent, so fan them out concurrently.
	var (
		natsCreds *syfthub.NatsCredentials
		peerResp  *syfthub.PeerTokenResponse
		satResp   *syfthub.SatelliteTokenResponse
		hostKey   string
	)
	g, gctx := errgroup.WithContext(ctx)
	g.Go(func() (err error) { natsCreds, err = client.Users.GetNatsCredentials(gctx); return })
	g.Go(func() (err error) { peerResp, err = client.Auth.GetPeerToken(gctx, []string{owner}); return })
	g.Go(func() (err error) { satResp, err = client.Auth.GetSatelliteToken(gctx, owner); return })
	g.Go(func() (err error) { hostKey, err = client.Auth.GetEncryptionPublicKey(gctx, owner); return })
	if err := g.Wait(); err != nil {
		return fail("Failed to resolve session credentials", err)
	}

	// Connect directly to NATS and dial the host — no aggregator in the path.
	natsConn, err := transport.NewNATSConn(&syfthubapi.NATSCredentials{
		URL:   peerResp.NatsURL,
		Token: natsCreds.NatsAuthToken,
	}, "syft-cli-agent", nil)
	if err != nil {
		return fail("Failed to connect to NATS", err)
	}
	defer natsConn.Close()

	dialer, err := transport.NewAgentDialer(natsConn, identityKey, nil)
	if err != nil {
		return fail("Failed to create agent dialer", err)
	}

	dialParams := transport.DialParams{
		TargetUsername:   owner,
		HostPublicKeyB64: hostKey,
		PeerChannel:      peerResp.PeerChannel,
		SatelliteToken:   satResp.TargetToken,
		Prompt:           prompt,
		EndpointSlug:     slug,
	}
	if len(agentAttachPaths) > 0 {
		dialParams.Capabilities = append(dialParams.Capabilities, agenttypes.AttachmentCapability)
	}

	session, err := dialer.Dial(ctx, dialParams)
	if err != nil {
		return fail("Failed to start session", err)
	}
	defer session.Close()

	fmt.Printf("Session %s started\n\n", session.SessionID)

	// Stage attachments up-front so the agent sees them before the prompt.
	for _, p := range agentAttachPaths {
		if err := uploadAgentAttachment(ctx, session, p); err != nil {
			output.Error("Failed to attach %s: %v", p, err)
			return err
		}
	}

	// ── State ──
	var tools []toolEntry      // all tool calls for /expand
	var pendingTool *toolEntry // tool_call waiting for its result

	// ── Stdin reader ──
	inputCh := make(chan string, 1)
	go func() {
		scanner := bufio.NewScanner(os.Stdin)
		for scanner.Scan() {
			inputCh <- scanner.Text()
		}
	}()

	for {
		select {
		case event, ok := <-session.Events():
			if !ok {
				fmt.Println("\nSession ended.")
				return nil
			}
			switch e := event.(type) {
			case *agenttypes.ThinkingEvent:
				fmt.Printf("\033[2m💭 %s\033[0m\n", e.Content)

			case *agenttypes.ToolCallEvent:
				idx := len(tools) + 1
				argsStr := ""
				if len(e.Arguments) > 0 {
					parts := make([]string, 0, len(e.Arguments))
					for k, v := range e.Arguments {
						parts = append(parts, fmt.Sprintf("%s=%v", k, v))
					}
					argsStr = strings.Join(parts, ", ")
				}

				pendingTool = &toolEntry{
					index: idx,
					name:  e.Name,
					args:  argsStr,
				}

				fmt.Printf("\033[33m🔧 #%d %s\033[0m", idx, e.Name)
				if argsStr != "" {
					display := argsStr
					if len(display) > 80 {
						display = display[:77] + "..."
					}
					fmt.Printf("\033[2m(%s)\033[0m", display)
				}
				fmt.Println()

			case *agenttypes.ToolResultEvent:
				statusIcon := "\033[32m✓\033[0m"
				if e.Status == "error" {
					statusIcon = "\033[31m✗\033[0m"
				}

				resultStr := fmt.Sprintf("%v", e.Result)

				if pendingTool != nil {
					pendingTool.status = e.Status
					pendingTool.result = resultStr
					tools = append(tools, *pendingTool)

					preview := pendingTool.formatPreview()
					for _, line := range strings.Split(preview, "\n") {
						fmt.Printf("   %s %s\n", statusIcon, line)
						statusIcon = " " // only show icon on first line
					}

					pendingTool = nil
				} else {
					fmt.Printf("   %s %s\n", statusIcon, truncate(resultStr, previewWidth))
				}

			case *agenttypes.MessageEvent:
				fmt.Printf("\n\033[1m%s\033[0m\n", e.Content)
				fmt.Print("\033[96m> \033[0m")

			case *agenttypes.AgentTokenEvent:
				fmt.Print(e.Token)

			case *agenttypes.AgentStatusEvent:
				fmt.Printf("\033[2m⏳ %s\033[0m\n", e.Detail)

			case *agenttypes.RequestInputEvent:
				fmt.Printf("\n\033[96m%s\033[0m\n", e.Prompt)
				fmt.Print("\033[96m> \033[0m")

			case *agenttypes.SessionCompletedEvent:
				fmt.Println("\n✓ Session completed.")
				return nil

			case *agenttypes.SessionFailedEvent:
				fmt.Printf("\n✗ Session failed: %s\n", e.Error)
				return fmt.Errorf("session failed: %s", e.Error)

			case *agenttypes.AgentErrorEvent:
				fmt.Printf("\n⚠ Error [%s]: %s\n", e.Code, e.Message)
				if !e.Recoverable {
					return fmt.Errorf("agent error: %s", e.Message)
				}

			case *agenttypes.AttachmentEvent:
				if err := saveAgentAttachment(session, e); err != nil {
					fmt.Printf("\n⚠ Attachment %s (%s): %v\n", e.Name, e.FileID, err)
				}

			case *agenttypes.AgentPaymentRequiredEvent:
				// Payment cannot be completed on the direct peer-to-peer path;
				// the host follows this with a terminal session.failed event.
				priced := strings.TrimSpace(e.Amount + " " + e.Currency)
				if priced != "" {
					fmt.Printf("\n⚠ This agent requires a payment of %s to start; payment is not supported on the direct peer-to-peer path.\n", priced)
				} else {
					fmt.Print("\n⚠ This agent requires a payment to start; payment is not supported on the direct peer-to-peer path.\n")
				}
			}

		case text := <-inputCh:
			text = strings.TrimSpace(text)
			if text == "" {
				continue
			}

			// Handle /expand command
			if text == "/expand" || text == "/e" {
				if len(tools) > 0 {
					tools[len(tools)-1].printFull()
				} else {
					fmt.Println("\033[2mNo tool results to expand.\033[0m")
				}
				fmt.Print("\033[96m> \033[0m")
				continue
			}
			if strings.HasPrefix(text, "/expand ") || strings.HasPrefix(text, "/e ") {
				var idx int
				parts := strings.Fields(text)
				if len(parts) >= 2 {
					fmt.Sscanf(parts[1], "%d", &idx)
				}
				if idx >= 1 && idx <= len(tools) {
					tools[idx-1].printFull()
				} else {
					fmt.Printf("\033[2mTool #%d not found. Available: 1-%d\033[0m\n", idx, len(tools))
				}
				fmt.Print("\033[96m> \033[0m")
				continue
			}

			if err := session.SendMessage(text); err != nil {
				output.Error("Failed to send message: %v", err)
			}

		case err := <-session.Errors():
			if err != nil {
				output.Error("Session error: %v", err)
			}
			return err

		case <-ctx.Done():
			fmt.Println("\nCancelling session...")
			_ = session.Cancel()
			return nil
		}
	}
}

func truncate(s string, max int) string {
	if len(s) <= max {
		return s
	}
	return s[:max-1] + "…"
}
