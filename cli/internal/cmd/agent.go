package cmd

import (
	"bufio"
	"context"
	"fmt"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/spf13/cobra"

	"github.com/OpenMined/syfthub/cli/internal/config"
	"github.com/OpenMined/syfthub/cli/internal/output"
	"github.com/openmined/syfthub/sdk/golang/syfthub"
)

var (
	agentAggregator string
)

var agentCmd = &cobra.Command{
	Use:   "agent <endpoint> <prompt>",
	Short: "Start an interactive agent session",
	Long: `Start an interactive agent session with an agent endpoint.

Opens a bidirectional session where the agent can think, call tools,
request input, and send messages. You can send follow-up messages
when the agent pauses for input.

The session runs through the full SyftHub pipeline:
  CLI → Hub → Aggregator → NATS → Node → Agent Handler

Tool results are collapsed by default. Type /expand to see the full
output of the last tool call, or /expand N to expand tool call #N.

Examples:

    syft agent alice/research-agent "Summarize recent ML papers"
    syft agent bob/code-assistant "Help me refactor this function"
    syft agent alice/agent --aggregator local "Hello"`,
	Args: cobra.ExactArgs(2),
	RunE: runAgent,
}

func init() {
	agentCmd.Flags().StringVarP(&agentAggregator, "aggregator", "a", "", "Aggregator alias or URL to use")
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

func runAgent(cmd *cobra.Command, args []string) error {
	endpoint := args[0]
	prompt := args[1]

	cfg := config.Load()

	aggregatorURL := cfg.GetAggregatorURL(agentAggregator)

	opts := []syfthub.Option{
		syfthub.WithBaseURL(cfg.HubURL),
		syfthub.WithTimeout(time.Duration(cfg.Timeout) * time.Second),
	}
	if aggregatorURL != "" {
		opts = append(opts, syfthub.WithAggregatorURL(aggregatorURL))
	}
	if cfg.HasAPIToken() {
		opts = append(opts, syfthub.WithAPIToken(cfg.APIToken))
	}

	client, err := syfthub.NewClient(opts...)
	if err != nil {
		output.Error("Failed to create client: %v", err)
		return err
	}
	defer client.Close()

	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()

	fmt.Printf("Connecting to %s...\n", endpoint)

	session, err := client.Agent().StartSession(ctx, &syfthub.AgentSessionRequest{
		Prompt:   prompt,
		Endpoint: endpoint,
	})
	if err != nil {
		output.Error("Failed to start session: %v", err)
		return err
	}
	defer session.Close()

	fmt.Printf("Session %s started\n\n", session.SessionID)

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
			case *syfthub.ThinkingEvent:
				fmt.Printf("\033[2m💭 %s\033[0m\n", e.Content)

			case *syfthub.ToolCallEvent:
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

				// Show tool call header
				fmt.Printf("\033[33m🔧 #%d %s\033[0m", idx, e.Name)
				if argsStr != "" {
					// Truncate long args
					display := argsStr
					if len(display) > 80 {
						display = display[:77] + "..."
					}
					fmt.Printf("\033[2m(%s)\033[0m", display)
				}
				fmt.Println()

			case *syfthub.ToolResultEvent:
				statusIcon := "\033[32m✓\033[0m"
				if e.Status == "error" {
					statusIcon = "\033[31m✗\033[0m"
				}

				resultStr := fmt.Sprintf("%v", e.Result)

				if pendingTool != nil {
					pendingTool.status = e.Status
					pendingTool.result = resultStr
					tools = append(tools, *pendingTool)

					// Show collapsed preview
					preview := pendingTool.formatPreview()
					for _, line := range strings.Split(preview, "\n") {
						fmt.Printf("   %s %s\n", statusIcon, line)
						statusIcon = " " // only show icon on first line
					}

					pendingTool = nil
				} else {
					// Standalone result without a preceding tool_call
					fmt.Printf("   %s %s\n", statusIcon, truncate(resultStr, previewWidth))
				}

			case *syfthub.MessageEvent:
				fmt.Printf("\n\033[1m%s\033[0m\n", e.Content)
				fmt.Print("\033[96m> \033[0m")

			case *syfthub.AgentTokenEvent:
				fmt.Print(e.Token)

			case *syfthub.AgentStatusEvent:
				fmt.Printf("\033[2m⏳ %s\033[0m\n", e.Detail)

			case *syfthub.RequestInputEvent:
				fmt.Printf("\n\033[96m%s\033[0m\n", e.Prompt)
				fmt.Print("\033[96m> \033[0m")

			case *syfthub.SessionCompletedEvent:
				fmt.Println("\n✓ Session completed.")
				return nil

			case *syfthub.SessionFailedEvent:
				fmt.Printf("\n✗ Session failed: %s\n", e.Error)
				return fmt.Errorf("session failed: %s", e.Error)

			case *syfthub.AgentErrorEvent:
				fmt.Printf("\n⚠ Error [%s]: %s\n", e.Code, e.Message)
				if !e.Recoverable {
					return fmt.Errorf("agent error: %s", e.Message)
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

			if err := session.SendMessage(ctx, text); err != nil {
				output.Error("Failed to send message: %v", err)
			}

		case err := <-session.Errors():
			if err != nil {
				output.Error("Session error: %v", err)
			}
			return err

		case <-ctx.Done():
			fmt.Println("\nCancelling session...")
			session.Cancel(context.Background())
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
