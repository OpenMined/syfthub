package main

import (
	"context"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"
)

func main() {
	// Structured JSON logging
	logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))
	slog.SetDefault(logger)

	// Load config
	cfg := DefaultConfig()
	LoadConfigFromEnv(&cfg)

	if cfg.AdminToken == "" {
		slog.Error("MARKETPLACE_ADMIN_TOKEN must be set")
		os.Exit(1)
	}

	slog.Info("starting marketplace server",
		"host", cfg.Host,
		"port", cfg.Port,
		"dbPath", cfg.DBPath,
		"baseURL", cfg.BaseURL,
	)

	// Open store
	store, err := NewStore(cfg.DBPath)
	if err != nil {
		slog.Error("failed to open store", "error", err)
		os.Exit(1)
	}
	defer store.Close()

	ctx := context.Background()
	count, _ := store.Count(ctx)
	slog.Info("store ready", "packages", count)

	// Create server
	srv := NewServer(store, logger, cfg)
	httpServer := srv.NewHTTPServer()

	// Start in goroutine
	errCh := make(chan error, 1)
	go func() {
		slog.Info("listening", "addr", httpServer.Addr)
		if err := httpServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			errCh <- err
		}
	}()

	// Graceful shutdown
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)

	select {
	case sig := <-quit:
		slog.Info("shutting down", "signal", sig)
	case err := <-errCh:
		slog.Error("server error", "error", err)
	}

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	if err := httpServer.Shutdown(shutdownCtx); err != nil {
		slog.Error("shutdown error", "error", err)
		os.Exit(1)
	}

	slog.Info("server stopped")
}
