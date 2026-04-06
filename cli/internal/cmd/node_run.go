package cmd

import (
	"context"
	"encoding/json"
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
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/containermode"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/filemode"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/heartbeat"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/setupflow"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/transport"

	"github.com/OpenMined/syfthub/cli/internal/nodeconfig"
)

// nodeRunCmd is a hidden command that runs the node in the foreground.
// It is spawned as a background daemon by "syft node init".
var nodeRunCmd = &cobra.Command{
	Use:         "run",
	Annotations: map[string]string{authExemptKey: "true"},
	Short:       "Run the node server (internal)",
	Hidden:      true,
	RunE:        runNodeRun,
}

func runNodeRun(cmd *cobra.Command, args []string) error {
	cfg := nodeconfig.Load()
	if !cfg.Configured() {
		return errors.New("node is not configured — run 'syft node init' first")
	}

	// Resolve endpoints path
	endpointsPath, err := filepath.Abs(cfg.EndpointsPath)
	if err != nil {
		return fmt.Errorf("failed to resolve endpoints path: %w", err)
	}
	if err := os.MkdirAll(endpointsPath, 0755); err != nil {
		return fmt.Errorf("failed to create endpoints directory: %w", err)
	}

	// Derive tunnel username from API key
	fmt.Println("Authenticating with SyftHub...")

	hubClient, err := syfthub.NewClient(
		syfthub.WithBaseURL(cfg.HubURL),
		syfthub.WithAPIToken(cfg.APIToken),
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
	fmt.Printf("Authenticated as %s (tunnel mode)\n", user.Username)

	// Build SyftAPI options
	opts := []syfthubapi.Option{
		syfthubapi.WithSyftHubURL(cfg.HubURL),
		syfthubapi.WithAPIKey(cfg.APIToken),
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
	if cfg.ContainerEnabled {
		opts = append(opts, syfthubapi.WithContainerEnabled(true))
		if cfg.ContainerRuntime != "" {
			opts = append(opts, syfthubapi.WithContainerRuntime(cfg.ContainerRuntime))
		}
		if cfg.ContainerImage != "" {
			opts = append(opts, syfthubapi.WithContainerImage(cfg.ContainerImage))
		}
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

	// Wire container runtime factory when container mode is enabled.
	// The factory and cleanup func are called inside api.Run() after config validation.
	if cfg.ContainerEnabled {
		api.SetContainerRuntimeFactory(containermode.NewCLIRuntime)
		api.SetContainerCleanupFunc(containermode.CleanupOrphans)
	}

	// Load initial endpoints.
	// When container mode is enabled, skip pre-loading: api.Run() will load
	// endpoints AFTER injecting the container runtime into the file provider,
	// so that all endpoints are created with container executors.
	if !cfg.ContainerEnabled {
		endpoints, err := provider.LoadEndpoints()
		if err != nil {
			logger.Warn("failed to load endpoints", "error", err)
		} else {
			api.Registry().ReplaceFileBased(endpoints)
		}
	}

	// Setup NATS transport (always tunnel mode)
	apiHubClient := syfthubapi.NewHubClient(apiConfig.SyftHubURL, apiConfig.APIKey, newSlogAdapter(logger))
	natsCreds, err := apiHubClient.GetNATSCredentials(context.Background(), user.Username)
	if err != nil {
		return fmt.Errorf("failed to get NATS credentials: %w", err)
	}
	t, err := transport.NewNATSTransport(&transport.Config{
		SpaceURL:        spaceURL,
		NATSCredentials: natsCreds,
		KeyFilePath:     nodeconfig.NodeKeyFile,
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

	// Setup request log hook (writes per-endpoint JSONL files like syfthub-desktop)
	if err := os.MkdirAll(nodeconfig.LogsDir, 0755); err != nil {
		logger.Warn("failed to create logs directory", "error", err)
	} else {
		api.SetLogHook(func(ctx context.Context, entry *syfthubapi.RequestLog) {
			writeRequestLog(nodeconfig.LogsDir, entry, logger)
		})
	}

	// Write PID file
	if err := nodeconfig.WritePID(os.Getpid()); err != nil {
		logger.Warn("failed to write PID file", "error", err)
	}
	defer nodeconfig.RemovePID()

	endpointCount := len(api.Registry().List())
	fmt.Println()
	fmt.Printf("SyftHub Node running — NATS Tunnel (%s)\n", user.Username)
	fmt.Printf("  Port:      %d\n", cfg.Port)
	fmt.Printf("  Endpoints: %d loaded from %s\n", endpointCount, endpointsPath)
	fmt.Printf("  Hub:       %s\n", cfg.HubURL)
	if cfg.ContainerEnabled {
		fmt.Printf("  Container: enabled (runtime=%s, image=%s)\n", apiConfig.Container.Runtime, apiConfig.Container.Image)
	}
	fmt.Println()

	// Run (blocks until signal)
	ctx, stopSignal := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stopSignal()

	// Start lifecycle manager for token refresh
	if endpointsPath != "" {
		lifecycleEngine := setupflow.NewEngine()
		lifecycleMgr := setupflow.NewLifecycleManager(lifecycleEngine)

		go func() {
			ticker := time.NewTicker(5 * time.Minute)
			defer ticker.Stop()
			for {
				select {
				case <-ticker.C:
					results := lifecycleMgr.CheckAndRefresh(endpointsPath)
					for _, r := range results {
						if r.Success {
							logger.Info("refreshed token", "slug", r.Slug, "step", r.StepID)
							// Trigger endpoint reload
							reloadEndpoints, loadErr := provider.LoadEndpoints()
							if loadErr != nil {
								logger.Warn("failed to reload endpoints after token refresh", "error", loadErr)
							} else {
								api.Registry().ReplaceFileBased(reloadEndpoints)
							}
						} else if r.Error != nil {
							logger.Warn("token refresh failed", "slug", r.Slug, "step", r.StepID, "error", r.Error)
						}
					}
				case <-ctx.Done():
					return
				}
			}
		}()
	}

	return api.Run(ctx)
}

// writeRequestLog writes a request log entry to a per-endpoint JSONL file.
// File layout: {logsDir}/{endpoint-slug}/{YYYY-MM-DD}.jsonl
func writeRequestLog(logsDir string, entry *syfthubapi.RequestLog, logger *slog.Logger) {
	slug := entry.EndpointSlug
	if slug == "" {
		return
	}

	dir := filepath.Join(logsDir, slug)
	if err := os.MkdirAll(dir, 0755); err != nil {
		logger.Warn("failed to create endpoint log dir", "slug", slug, "error", err)
		return
	}

	date := entry.Timestamp.Format("2006-01-02")
	filename := filepath.Join(dir, date+".jsonl")

	data, err := json.Marshal(entry)
	if err != nil {
		logger.Warn("failed to marshal log entry", "error", err)
		return
	}

	f, err := os.OpenFile(filename, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err != nil {
		logger.Warn("failed to open log file", "path", filename, "error", err)
		return
	}
	defer f.Close()

	f.Write(data)
	f.Write([]byte("\n"))
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
