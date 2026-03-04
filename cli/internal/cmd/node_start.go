package cmd

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"
	"time"

	"github.com/spf13/cobra"

	"github.com/openmined/syfthub/sdk/golang/syfthub"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/filemode"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/heartbeat"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/transport"

	"github.com/OpenMined/syfthub/cli/internal/nodeconfig"
	"github.com/OpenMined/syfthub/cli/internal/output"
)

var (
	nodeStartPort          int
	nodeStartLogLevel      string
	nodeStartEndpointsPath string
	nodeStartJSON          bool
)

var nodeStartCmd = &cobra.Command{
	Use:   "start",
	Short: "Start the node server",
	Long: `Start the SyftHub node server as a foreground process.

The node loads endpoints from the configured endpoints directory, connects to
SyftHub via NATS tunneling (using the username derived from your API key),
registers endpoints, and begins sending heartbeats.

Press Ctrl+C to stop the node.`,
	RunE: runNodeStart,
}

func init() {
	nodeStartCmd.Flags().IntVar(&nodeStartPort, "port", 0, "Override HTTP server port")
	nodeStartCmd.Flags().StringVar(&nodeStartLogLevel, "log-level", "", "Override log level (DEBUG, INFO, WARNING, ERROR)")
	nodeStartCmd.Flags().StringVar(&nodeStartEndpointsPath, "endpoints-path", "", "Override endpoints directory")
	nodeStartCmd.Flags().BoolVar(&nodeStartJSON, "json", false, "Output result as JSON")
}

func runNodeStart(cmd *cobra.Command, args []string) error {
	cfg := nodeconfig.Load()
	if !cfg.Configured() {
		msg := "Node is not configured. Run 'syft node init' first."
		if nodeStartJSON {
			output.JSON(map[string]interface{}{"status": "error", "message": msg})
		} else {
			output.Error(msg)
		}
		return errors.New(msg)
	}

	// Apply flag overrides
	if nodeStartPort > 0 {
		cfg.Port = nodeStartPort
	}
	if nodeStartLogLevel != "" {
		cfg.LogLevel = nodeStartLogLevel
	}
	if nodeStartEndpointsPath != "" {
		cfg.EndpointsPath = nodeStartEndpointsPath
	}

	// Resolve endpoints path
	endpointsPath, err := filepath.Abs(cfg.EndpointsPath)
	if err != nil {
		return fmt.Errorf("failed to resolve endpoints path: %w", err)
	}

	// Ensure endpoints dir exists
	if err := os.MkdirAll(endpointsPath, 0755); err != nil {
		return fmt.Errorf("failed to create endpoints directory: %w", err)
	}

	// Derive tunnel username from API key (like syfthub-desktop does)
	if !nodeStartJSON {
		fmt.Println("Authenticating with SyftHub...")
	}

	hubClient, err := syfthub.NewClient(
		syfthub.WithBaseURL(cfg.SyftHubURL),
		syfthub.WithAPIToken(cfg.APIKey),
	)
	if err != nil {
		return fmt.Errorf("failed to create hub client: %w", err)
	}

	fetchCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	user, err := hubClient.Auth.Me(fetchCtx)
	if err != nil {
		return fmt.Errorf("failed to authenticate with SyftHub: %w", err)
	}

	spaceURL := fmt.Sprintf("tunneling:%s", user.Username)

	if !nodeStartJSON {
		fmt.Printf("Authenticated as %s (tunnel mode)\n", user.Username)
	}

	// Build SyftAPI options
	opts := []syfthubapi.Option{
		syfthubapi.WithSyftHubURL(cfg.SyftHubURL),
		syfthubapi.WithAPIKey(cfg.APIKey),
		syfthubapi.WithEndpointsPath(endpointsPath),
		syfthubapi.WithServerPort(cfg.Port),
		syfthubapi.WithWatchEnabled(true),
		syfthubapi.WithSpaceURL(spaceURL),
	}
	if cfg.LogLevel != "" {
		opts = append(opts, syfthubapi.WithLogLevel(cfg.LogLevel))
	}
	if cfg.PythonPath != "" {
		opts = append(opts, syfthubapi.WithPythonPath(cfg.PythonPath))
	}

	api := syfthubapi.New(opts...)
	apiConfig := api.Config()
	logger := api.Logger()

	// Setup file provider
	provider, err := filemode.NewProvider(&filemode.ProviderConfig{
		BasePath:     endpointsPath,
		PythonPath:   cfg.PythonPath,
		WatchEnabled: true,
		Logger:       logger,
		OnReload: func(endpoints []*syfthubapi.Endpoint) {
			logger.Info("endpoints reloaded", "count", len(endpoints))
			api.Registry().ReplaceFileBased(endpoints)
			if err := api.SyncEndpoints(context.Background()); err != nil {
				logger.Error("failed to sync endpoints", "error", err)
			}
		},
	})
	if err != nil {
		return fmt.Errorf("failed to create file provider: %w", err)
	}
	api.SetFileProvider(provider)

	// Load initial endpoints
	endpoints, err := provider.LoadEndpoints()
	if err != nil {
		logger.Warn("failed to load endpoints", "error", err)
	} else {
		api.Registry().ReplaceFileBased(endpoints)
	}

	// Setup NATS transport (always tunnel mode)
	authClient := syfthubapi.NewAuthClient(apiConfig.SyftHubURL, apiConfig.APIKey, newSlogAdapter(logger))
	natsCreds, err := authClient.GetNATSCredentials(context.Background(), user.Username)
	if err != nil {
		return fmt.Errorf("failed to get NATS credentials: %w", err)
	}
	t, err := transport.NewNATSTransport(&transport.Config{
		SpaceURL:        spaceURL,
		NATSCredentials: natsCreds,
		Logger:          logger,
	})
	if err != nil {
		return fmt.Errorf("failed to create NATS transport: %w", err)
	}
	api.SetTransport(t)

	// Setup heartbeat
	if apiConfig.HeartbeatEnabled {
		hbManager := heartbeat.NewManager(&heartbeat.Config{
			BaseURL:            apiConfig.SyftHubURL,
			APIKey:             apiConfig.APIKey,
			SpaceURL:           spaceURL,
			TTLSeconds:         apiConfig.HeartbeatTTLSeconds,
			IntervalMultiplier: apiConfig.HeartbeatIntervalMultiplier,
			Logger:             logger,
		})
		api.SetHeartbeatManager(hbManager)
	}

	// Write PID file
	if err := nodeconfig.WritePID(os.Getpid()); err != nil {
		logger.Warn("failed to write PID file", "error", err)
	}
	defer nodeconfig.RemovePID()

	// Print startup banner
	endpointCount := len(api.Registry().List())

	if nodeStartJSON {
		output.JSON(map[string]interface{}{
			"status":    "starting",
			"mode":      fmt.Sprintf("NATS Tunnel (%s)", user.Username),
			"port":      cfg.Port,
			"endpoints": endpointCount,
			"path":      endpointsPath,
		})
	} else {
		fmt.Println()
		output.Success("SyftHub Node starting")
		fmt.Printf("  Mode:      NATS Tunnel (%s)\n", user.Username)
		fmt.Printf("  Port:      %d\n", cfg.Port)
		fmt.Printf("  Endpoints: %d loaded from %s\n", endpointCount, endpointsPath)
		fmt.Printf("  Hub:       %s\n", cfg.SyftHubURL)
		fmt.Println()
		fmt.Println("Press Ctrl+C to stop.")
		fmt.Println()
	}

	// Run (blocks until signal)
	ctx, stopSignal := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stopSignal()

	return api.Run(ctx)
}

// slogAdapter adapts slog.Logger to the syfthubapi Logger interface.
type slogAdapter struct {
	*slog.Logger
}

func newSlogAdapter(l *slog.Logger) *slogAdapter {
	return &slogAdapter{l}
}

func (s *slogAdapter) Debug(msg string, args ...any) { s.Logger.Debug(msg, args...) }
func (s *slogAdapter) Info(msg string, args ...any)  { s.Logger.Info(msg, args...) }
func (s *slogAdapter) Warn(msg string, args ...any)  { s.Logger.Warn(msg, args...) }
func (s *slogAdapter) Error(msg string, args ...any) { s.Logger.Error(msg, args...) }
