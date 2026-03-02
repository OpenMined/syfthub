package main

import (
	"log/slog"
	"net/http"
	"time"
)

// Config holds the server configuration.
type Config struct {
	Port    string
	Host    string
	DBPath  string
	BaseURL string
}

// Option is a functional option for Config.
type Option func(*Config)

func WithPort(port string) Option    { return func(c *Config) { c.Port = port } }
func WithHost(host string) Option    { return func(c *Config) { c.Host = host } }
func WithDBPath(path string) Option  { return func(c *Config) { c.DBPath = path } }
func WithBaseURL(url string) Option  { return func(c *Config) { c.BaseURL = url } }

// DefaultConfig returns sensible defaults.
func DefaultConfig() Config {
	return Config{
		Port:    "8003",
		Host:    "0.0.0.0",
		DBPath:  "marketplace.db",
		BaseURL: "http://localhost:8003",
	}
}

// LoadConfigFromEnv overrides config fields from environment variables.
func LoadConfigFromEnv(cfg *Config) {
	if v := getenv("MARKETPLACE_PORT"); v != "" {
		cfg.Port = v
	}
	if v := getenv("MARKETPLACE_HOST"); v != "" {
		cfg.Host = v
	}
	if v := getenv("MARKETPLACE_DB_PATH"); v != "" {
		cfg.DBPath = v
	}
	if v := getenv("MARKETPLACE_BASE_URL"); v != "" {
		cfg.BaseURL = v
	}
}

// Server is the marketplace HTTP server.
type Server struct {
	store   *Store
	logger  *slog.Logger
	baseURL string
	config  Config
}

// NewServer creates a new Server.
func NewServer(store *Store, logger *slog.Logger, cfg Config) *Server {
	return &Server{
		store:   store,
		logger:  logger,
		baseURL: cfg.BaseURL,
		config:  cfg,
	}
}

// NewHTTPServer creates the http.Server with all routes registered.
func (s *Server) NewHTTPServer() *http.Server {
	mux := http.NewServeMux()

	// API routes (Go 1.22+ method routing)
	mux.HandleFunc("GET /health", s.handleHealth)
	mux.HandleFunc("GET /api/v1/packages", s.handleListPackages)
	mux.HandleFunc("GET /api/v1/packages/{slug}", s.handleGetPackage)
	mux.HandleFunc("POST /api/v1/packages", s.handleCreatePackage)
	mux.HandleFunc("PATCH /api/v1/packages/{slug}", s.handleUpdatePackage)
	mux.HandleFunc("DELETE /api/v1/packages/{slug}", s.handleDeletePackage)
	mux.HandleFunc("GET /api/v1/packages/{slug}/download", s.handleDownloadPackage)

	// Legacy routes (desktop app compat)
	mux.HandleFunc("GET /manifest.json", s.handleManifest)
	mux.HandleFunc("GET /packages/{file}", s.handleLegacyDownload)

	return &http.Server{
		Addr:         s.config.Host + ":" + s.config.Port,
		Handler:      corsMiddleware(mux),
		ReadTimeout:  30 * time.Second,
		WriteTimeout: 120 * time.Second,
		IdleTimeout:  120 * time.Second,
	}
}

// corsMiddleware adds CORS headers and handles preflight requests.
func corsMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization")

		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}

		next.ServeHTTP(w, r)
	})
}
