// Example: File-based endpoints with NATS tunneling mode
//
// This example demonstrates how to use file-based endpoint configuration
// with NATS tunneling for communication with SyftHub.
//
// Endpoint directory structure:
//
//	endpoints/
//	├── my-model/
//	│   ├── README.md      # YAML frontmatter + docs
//	│   ├── runner.py      # Python handler
//	│   ├── .env           # Environment variables
//	│   ├── pyproject.toml # Dependencies
//	│   └── policy/
//	│       └── rate_limit.yaml
//	└── my-datasource/
//	    ├── README.md
//	    └── runner.py
//
// Usage:
//
//	export SYFTHUB_URL=https://syfthub.example.com
//	export SYFTHUB_API_KEY=syft_pat_xxx
//	export SPACE_URL=tunneling:my-username
//	export ENDPOINTS_PATH=./endpoints
//	go run main.go
package main

import (
	"context"
	"fmt"
	"log"
	"log/slog"
	"os"
	"time"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/filemode"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/heartbeat"
	"github.com/openmined/syfthub/sdk/golang/syfthubapi/transport"
)

func main() {
	// Get configuration from environment
	endpointsPath := os.Getenv("ENDPOINTS_PATH")
	if endpointsPath == "" {
		endpointsPath = "./endpoints"
	}

	// Create the SyftAPI instance with tunneling mode
	// SPACE_URL should be set to "tunneling:username"
	app := syfthubapi.New(
		syfthubapi.WithLogLevel("DEBUG"),
		syfthubapi.WithEndpointsPath(endpointsPath),
		syfthubapi.WithWatchEnabled(true),
		syfthubapi.WithWatchDebounce(1.0),
	)

	logger := app.Logger()
	config := app.Config()

	// Verify tunnel mode is enabled
	if !config.IsTunnelMode() {
		log.Printf("WARNING: Not in tunnel mode. Set SPACE_URL=tunneling:username")
		log.Printf("Current SPACE_URL: %s", config.SpaceURL)
		log.Printf("Falling back to HTTP mode on port %d", config.ServerPort)
	} else {
		log.Printf("Tunnel mode enabled for user: %s", config.GetTunnelUsername())
	}

	// Create and configure the file provider
	provider, err := filemode.NewProvider(&filemode.ProviderConfig{
		BasePath:     endpointsPath,
		PythonPath:   os.Getenv("PYTHON_PATH"),
		WatchEnabled: true,
		Debounce:     time.Second,
		Logger:       logger,
		OnReload: func(endpoints []*syfthubapi.Endpoint) {
			log.Printf("Endpoints reloaded: %d endpoints", len(endpoints))
			app.Registry().ReplaceFileBased(endpoints)
			// Re-sync endpoints with SyftHub after hot-reload
			if err := app.SyncEndpoints(context.Background()); err != nil {
				log.Printf("Failed to re-sync endpoints: %v", err)
			} else {
				log.Printf("Endpoints re-synced with SyftHub")
			}
		},
	})
	if err != nil {
		log.Fatalf("Failed to create file provider: %v", err)
	}
	app.SetFileProvider(provider)

	// Load initial endpoints
	endpoints, err := provider.LoadEndpoints()
	if err != nil {
		log.Printf("Warning: Failed to load endpoints: %v", err)
	} else {
		app.Registry().ReplaceFileBased(endpoints)
		log.Printf("Loaded %d file-based endpoints", len(endpoints))
		for _, ep := range endpoints {
			log.Printf("  - %s (%s): %s", ep.Slug, ep.Type, ep.Name)
		}
	}

	// Setup transport based on mode
	var t syfthubapi.Transport
	if config.IsTunnelMode() {
		// For tunnel mode, we need to get NATS credentials from SyftHub
		// In a real scenario, this would call the auth client
		log.Println("Setting up NATS transport...")

		// Create auth client to get NATS credentials
		authClient := syfthubapi.NewAuthClient(config.SyftHubURL, config.APIKey, &slogAdapter{logger})

		natsCreds, err := authClient.GetNATSCredentials(context.Background(), config.GetTunnelUsername())
		if err != nil {
			log.Printf("Failed to get NATS credentials: %v", err)
			log.Println("Using mock NATS credentials for testing...")
			// Use mock credentials for local testing
			natsCreds = &syfthubapi.NATSCredentials{
				URL:     getEnvOrDefault("NATS_URL", "nats://localhost:4222"),
				Token:   getEnvOrDefault("NATS_TOKEN", "test-token"),
				Subject: fmt.Sprintf("syfthub.spaces.%s", config.GetTunnelUsername()),
			}
		}
		log.Printf("NATS URL: %s", natsCreds.URL)
		tokenPreview := natsCreds.Token
		if len(tokenPreview) > 20 {
			tokenPreview = tokenPreview[:20] + "..."
		}
		log.Printf("NATS Token: %s", tokenPreview)

		natsTransport, err := transport.NewNATSTransport(&transport.Config{
			SpaceURL:        config.SpaceURL,
			NATSCredentials: natsCreds,
			Logger:          logger,
		})
		if err != nil {
			log.Fatalf("Failed to create NATS transport: %v", err)
		}
		t = natsTransport
		log.Printf("NATS transport configured for subject: %s", natsCreds.Subject)
	} else {
		// HTTP mode fallback
		httpTransport, err := transport.NewHTTPTransport(&transport.Config{
			SpaceURL: config.SpaceURL,
			Host:     config.ServerHost,
			Port:     config.ServerPort,
			Logger:   logger,
		})
		if err != nil {
			log.Fatalf("Failed to create HTTP transport: %v", err)
		}
		t = httpTransport
	}
	app.SetTransport(t)

	// Setup heartbeat manager
	if config.HeartbeatEnabled {
		hbManager := heartbeat.NewManager(&heartbeat.Config{
			BaseURL:            config.SyftHubURL,
			APIKey:             config.APIKey,
			SpaceURL:           config.SpaceURL,
			TTLSeconds:         config.HeartbeatTTLSeconds,
			IntervalMultiplier: config.HeartbeatIntervalMultiplier,
			Logger:             logger,
		})
		app.SetHeartbeatManager(hbManager)
	}

	// Add lifecycle hooks
	app.OnStartup(func(ctx context.Context) error {
		log.Println("Space starting up...")
		return nil
	})

	app.OnShutdown(func(ctx context.Context) error {
		log.Println("Space shutting down...")
		return nil
	})

	// Run the server
	log.Printf("Starting SyftHub Space...")
	log.Printf("  Mode: %s", getModeString(config))
	log.Printf("  Endpoints path: %s", endpointsPath)
	log.Printf("  Watch enabled: %v", true)

	if err := app.Run(context.Background()); err != nil {
		log.Fatalf("Server error: %v", err)
	}
}

func getModeString(config *syfthubapi.Config) string {
	if config.IsTunnelMode() {
		return fmt.Sprintf("NATS Tunnel (user: %s)", config.GetTunnelUsername())
	}
	return fmt.Sprintf("HTTP (port: %d)", config.ServerPort)
}

func getEnvOrDefault(key, defaultVal string) string {
	if val := os.Getenv(key); val != "" {
		return val
	}
	return defaultVal
}

// slogAdapter adapts slog.Logger to the Logger interface
type slogAdapter struct {
	*slog.Logger
}

func (s *slogAdapter) Debug(msg string, args ...any) {
	s.Logger.Debug(msg, args...)
}

func (s *slogAdapter) Info(msg string, args ...any) {
	s.Logger.Info(msg, args...)
}

func (s *slogAdapter) Warn(msg string, args ...any) {
	s.Logger.Warn(msg, args...)
}

func (s *slogAdapter) Error(msg string, args ...any) {
	s.Logger.Error(msg, args...)
}
