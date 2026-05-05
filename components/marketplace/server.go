package main

import (
	"crypto/subtle"
	"log/slog"
	"net/http"
	"os"
	"strings"
	"time"
)

// Config holds the server configuration.
type Config struct {
	Port       string
	Host       string
	DBPath     string
	BaseURL    string
	AdminToken string
}

// Option is a functional option for Config.
type Option func(*Config)

func WithPort(port string) Option       { return func(c *Config) { c.Port = port } }
func WithHost(host string) Option       { return func(c *Config) { c.Host = host } }
func WithDBPath(path string) Option     { return func(c *Config) { c.DBPath = path } }
func WithBaseURL(url string) Option     { return func(c *Config) { c.BaseURL = url } }
func WithAdminToken(token string) Option { return func(c *Config) { c.AdminToken = token } }

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
	if v := os.Getenv("MARKETPLACE_PORT"); v != "" {
		cfg.Port = v
	}
	if v := os.Getenv("MARKETPLACE_HOST"); v != "" {
		cfg.Host = v
	}
	if v := os.Getenv("MARKETPLACE_DB_PATH"); v != "" {
		cfg.DBPath = v
	}
	if v := os.Getenv("MARKETPLACE_BASE_URL"); v != "" {
		cfg.BaseURL = v
	}
	if v := os.Getenv("MARKETPLACE_ADMIN_TOKEN"); v != "" {
		cfg.AdminToken = v
	}
}

// Server is the marketplace HTTP server.
type Server struct {
	store  *Store
	logger *slog.Logger
	config Config
}

// NewServer creates a new Server.
func NewServer(store *Store, logger *slog.Logger, cfg Config) *Server {
	return &Server{
		store:  store,
		logger: logger,
		config: cfg,
	}
}

// requireAuth wraps a handler and enforces Bearer token authentication.
// Requests must include "Authorization: Bearer <MARKETPLACE_ADMIN_TOKEN>".
func (s *Server) requireAuth(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		auth := r.Header.Get("Authorization")
		if !strings.HasPrefix(auth, "Bearer ") ||
			subtle.ConstantTimeCompare([]byte(strings.TrimPrefix(auth, "Bearer ")), []byte(s.config.AdminToken)) != 1 {
			writeProblem(w, http.StatusUnauthorized, "Unauthorized", "valid Bearer token required")
			return
		}
		next(w, r)
	}
}

// NewHTTPServer creates the http.Server with all routes registered.
func (s *Server) NewHTTPServer() *http.Server {
	mux := http.NewServeMux()

	// API routes (Go 1.22+ method routing)
	mux.HandleFunc("GET /health", s.handleHealth)
	mux.HandleFunc("GET /api/v1/packages", s.handleListPackages)
	mux.HandleFunc("GET /api/v1/packages/{slug}", s.handleGetPackage)
	mux.HandleFunc("POST /api/v1/packages", s.requireAuth(s.handleCreatePackage))
	mux.HandleFunc("PATCH /api/v1/packages/{slug}", s.requireAuth(s.handleUpdatePackage))
	mux.HandleFunc("DELETE /api/v1/packages/{slug}", s.requireAuth(s.handleDeletePackage))
	mux.HandleFunc("PUT /api/v1/packages/{slug}/upload", s.requireAuth(s.handleUploadPackageZip))
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
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization")

		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}

		next.ServeHTTP(w, r)
	})
}
