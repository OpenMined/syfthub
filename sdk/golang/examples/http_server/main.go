// Example: Basic HTTP server with SyftAPI
//
// This example demonstrates how to create a simple SyftHub Space with
// data source and model endpoints using the Go SDK.
//
// Usage:
//
//	export SYFTHUB_URL=https://syfthub.example.com
//	export SYFTHUB_API_KEY=syft_pat_xxx
//	export SPACE_URL=http://localhost:8001
//	go run main.go
package main

import (
	"context"
	"log"
	"os"

	"github.com/openmined/syfthub/sdk/golang/syfthubapi"
)

func main() {
	// Create the SyftAPI instance
	// Configuration is loaded from environment variables by default
	app := syfthubapi.New(
		syfthubapi.WithLogLevel("INFO"),
		syfthubapi.WithServerPort(8001),
	)

	// Register a data source endpoint
	// Data sources return documents based on a query
	if err := app.DataSource("papers").
		Name("Research Papers").
		Description("Search through research papers using semantic search").
		Version("1.0.0").
		Handler(searchPapers); err != nil {
		log.Fatalf("Failed to register data source: %v", err)
	}

	// Register a model endpoint
	// Models take messages and return a response
	if err := app.Model("assistant").
		Name("AI Assistant").
		Description("A helpful AI assistant that answers questions").
		Version("1.0.0").
		Handler(chatAssistant); err != nil {
		log.Fatalf("Failed to register model: %v", err)
	}

	// Add lifecycle hooks
	app.OnStartup(func(ctx context.Context) error {
		log.Println("Starting up...")
		return nil
	})

	app.OnShutdown(func(ctx context.Context) error {
		log.Println("Shutting down...")
		return nil
	})

	// Run the server
	log.Println("Starting SyftHub Space...")
	if err := app.Run(context.Background()); err != nil {
		log.Fatalf("Server error: %v", err)
		os.Exit(1)
	}
}

// searchPapers is a data source handler that searches for papers
func searchPapers(ctx context.Context, query string, reqCtx *syfthubapi.RequestContext) ([]syfthubapi.Document, error) {
	// In a real implementation, you would:
	// 1. Embed the query using a model
	// 2. Search a vector database
	// 3. Return the most relevant documents

	log.Printf("Searching papers for: %s (user: %s)", query, reqCtx.User.Username)

	// Return sample documents
	return []syfthubapi.Document{
		{
			DocumentID:      "paper-001",
			Content:         "This paper discusses the fundamentals of machine learning...",
			Metadata:        map[string]any{"title": "ML Fundamentals", "year": 2024},
			SimilarityScore: 0.95,
		},
		{
			DocumentID:      "paper-002",
			Content:         "A comprehensive review of neural network architectures...",
			Metadata:        map[string]any{"title": "Neural Networks Review", "year": 2023},
			SimilarityScore: 0.87,
		},
	}, nil
}

// chatAssistant is a model handler that generates responses
func chatAssistant(ctx context.Context, messages []syfthubapi.Message, reqCtx *syfthubapi.RequestContext) (string, error) {
	// In a real implementation, you would:
	// 1. Send messages to an LLM API (OpenAI, Anthropic, etc.)
	// 2. Return the generated response

	log.Printf("Chat request with %d messages (user: %s)", len(messages), reqCtx.User.Username)

	// Get the last user message
	var lastUserMessage string
	for i := len(messages) - 1; i >= 0; i-- {
		if messages[i].Role == "user" {
			lastUserMessage = messages[i].Content
			break
		}
	}

	// Return a sample response
	return "I understand you're asking about: " + lastUserMessage + ". This is a sample response from the AI assistant.", nil
}
