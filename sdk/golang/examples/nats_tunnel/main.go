// Example: NATS tunnel mode
//
// This example demonstrates how to run a SyftHub Space in tunnel mode
// using NATS for communication instead of direct HTTP.
//
// Tunnel mode is useful when:
// - The space is behind a firewall
// - The space doesn't have a public IP address
// - You want SyftHub to manage routing
//
// Usage:
//
//	export SYFTHUB_URL=https://syfthub.example.com
//	export SYFTHUB_API_KEY=syft_pat_xxx
//	export SPACE_URL=tunneling:my-username
//	go run main.go
package main

import (
	"context"
	"log"
	"os"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
)

func main() {
	// In tunnel mode, set SPACE_URL to tunneling:username
	// The SDK will automatically fetch NATS credentials from SyftHub
	app := syfthubapi.New(
		syfthubapi.WithLogLevel("INFO"),
		// SpaceURL is loaded from SPACE_URL env var
	)

	// Check that we're in tunnel mode
	if !app.Config().IsTunnelMode() {
		log.Println("Warning: Not configured for tunnel mode")
		log.Println("Set SPACE_URL=tunneling:your-username to use tunnel mode")
	} else {
		log.Printf("Tunnel mode enabled for user: %s", app.Config().GetTunnelUsername())
	}

	// Register endpoints (same as HTTP mode)
	if err := app.DataSource("search").
		Name("Document Search").
		Description("Search through documents").
		Handler(searchDocuments); err != nil {
		log.Fatalf("Failed to register search endpoint: %v", err)
	}

	if err := app.Model("chat").
		Name("Chat Assistant").
		Description("An AI chat assistant").
		Handler(chatHandler); err != nil {
		log.Fatalf("Failed to register chat endpoint: %v", err)
	}

	// Run the server
	// In tunnel mode, this will connect to NATS and listen for messages
	log.Println("Starting SyftHub Space in tunnel mode...")
	if err := app.Run(context.Background()); err != nil {
		log.Fatalf("Server error: %v", err)
		os.Exit(1)
	}
}

func searchDocuments(ctx context.Context, query string, reqCtx *syfthubapi.RequestContext) ([]syfthubapi.Document, error) {
	log.Printf("Tunnel: Search request for '%s' from user %s", query, reqCtx.User.Username)

	return []syfthubapi.Document{
		{
			DocumentID:      "doc-1",
			Content:         "Sample document content matching: " + query,
			SimilarityScore: 0.9,
		},
	}, nil
}

func chatHandler(ctx context.Context, messages []syfthubapi.Message, reqCtx *syfthubapi.RequestContext) (string, error) {
	log.Printf("Tunnel: Chat request with %d messages from user %s", len(messages), reqCtx.User.Username)

	// Get last message
	if len(messages) > 0 {
		lastMsg := messages[len(messages)-1]
		return "Tunnel response to: " + lastMsg.Content, nil
	}

	return "Hello from tunnel mode!", nil
}
