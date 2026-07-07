// Demo script: Login, RAG Query, and Accounting Balance Check.
//
// This script demonstrates a complete SyftHub SDK workflow:
// 1. Login with username/password
// 2. Query a model using data sources (RAG)
// 3. Check accounting balance (auto-retrieved from backend)
//
// Usage:
//
//	# Using environment variables
//	export SYFTHUB_URL="https://hub.syft.com"
//
//	go run . --username alice --password secret123 \
//	    --model "owner/model-slug" \
//	    --data-sources "owner1/docs,owner2/knowledge-base" \
//	    --prompt "What is machine learning?"
//
//	# Or with explicit URLs
//	go run . --base-url https://hub.syft.com \
//	    --username alice --password secret123 \
//	    --model "owner/model-slug" \
//	    --prompt "Explain neural networks"
package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"os"
	"strings"

	"github.com/openmined/syfthub/sdk/golang/syfthub"
)

var (
	baseURL        = flag.String("base-url", os.Getenv("SYFTHUB_URL"), "SyftHub API URL (or set SYFTHUB_URL env var)")
	username       = flag.String("username", "", "Username or email for login")
	password       = flag.String("password", "", "Password for login")
	model          = flag.String("model", "", "Model endpoint path (e.g., 'owner/model-slug')")
	dataSources    = flag.String("data-sources", "", "Comma-separated data source paths")
	prompt         = flag.String("prompt", "", "The prompt/question to send to the model")
	topK           = flag.Int("top-k", 5, "Number of documents to retrieve per source")
	maxTokens      = flag.Int("max-tokens", 1024, "Maximum tokens to generate")
	temperature    = flag.Float64("temperature", 0.7, "Generation temperature")
	stream         = flag.Bool("stream", false, "Use streaming mode for response")
	skipAccounting = flag.Bool("skip-accounting", false, "Skip the accounting balance check")
)

func main() {
	flag.Usage = func() {
		fmt.Fprintf(os.Stderr, "Usage: %s [options]\n\n", os.Args[0])
		fmt.Fprintln(os.Stderr, "SyftHub SDK Demo: Login, RAG Query, and Accounting")
		fmt.Fprintln(os.Stderr, "Options:")
		flag.PrintDefaults()
		fmt.Fprintln(os.Stderr, "\nExamples:")
		fmt.Fprintln(os.Stderr, "  # Basic usage with model and data sources")
		fmt.Fprintln(os.Stderr, "  go run . -username alice -password secret123 \\")
		fmt.Fprintln(os.Stderr, "      -model \"bob/gpt-model\" \\")
		fmt.Fprintln(os.Stderr, "      -data-sources \"carol/docs,dave/tutorials\" \\")
		fmt.Fprintln(os.Stderr, "      -prompt \"What is Python?\"")
		fmt.Fprintln(os.Stderr, "")
		fmt.Fprintln(os.Stderr, "  # Streaming mode")
		fmt.Fprintln(os.Stderr, "  go run . -username alice -password secret123 \\")
		fmt.Fprintln(os.Stderr, "      -model \"bob/gpt-model\" \\")
		fmt.Fprintln(os.Stderr, "      -prompt \"Explain AI\" \\")
		fmt.Fprintln(os.Stderr, "      -stream")
	}
	flag.Parse()

	// Validate required arguments
	if *username == "" || *password == "" {
		printError("username and password are required")
	}
	if *model == "" {
		printError("model is required")
	}
	if *prompt == "" {
		printError("prompt is required")
	}
	if *baseURL == "" {
		printError("SyftHub URL not configured. Either pass -base-url or set SYFTHUB_URL environment variable.")
	}

	// Parse data sources
	var sources []string
	if *dataSources != "" {
		for _, ds := range strings.Split(*dataSources, ",") {
			ds = strings.TrimSpace(ds)
			if ds != "" {
				sources = append(sources, ds)
			}
		}
	}

	fmt.Printf("Connecting to: %s\n", *baseURL)

	// Create client
	client, err := syfthub.NewClient(syfthub.WithBaseURL(*baseURL))
	if err != nil {
		printError(fmt.Sprintf("Failed to create client: %v", err))
	}
	defer client.Close()

	ctx := context.Background()

	// Step 1: Login
	login(ctx, client, *username, *password)

	// Step 2: RAG Chat Query
	if *stream {
		queryModelStream(ctx, client, *model, sources, *prompt, *topK, *maxTokens, *temperature)
	} else {
		queryModelComplete(ctx, client, *model, sources, *prompt, *topK, *maxTokens, *temperature)
	}

	// Step 3: Accounting Balance (optional)
	if !*skipAccounting {
		checkAccounting(ctx, client)
	}

	printHeader("Complete")
	fmt.Println("Demo workflow finished successfully!")
}

func printHeader(title string) {
	fmt.Println()
	fmt.Println(strings.Repeat("=", 60))
	fmt.Printf("  %s\n", title)
	fmt.Println(strings.Repeat("=", 60))
	fmt.Println()
}

func printError(message string) {
	fmt.Fprintf(os.Stderr, "\nError: %s\n", message)
	os.Exit(1)
}

func login(ctx context.Context, client *syfthub.Client, username, password string) {
	printHeader("Step 1: Authentication")

	fmt.Printf("Logging in as: %s\n", username)

	user, err := client.Auth.Login(ctx, username, password)
	if err != nil {
		var authErr *syfthub.AuthenticationError
		if errors.As(err, &authErr) {
			printError(fmt.Sprintf("Login failed: %s", authErr.Message))
		}
		printError(fmt.Sprintf("Login failed: %v", err))
	}

	fmt.Println("Login successful!")
	fmt.Printf("  User ID: %d\n", user.ID)
	fmt.Printf("  Username: %s\n", user.Username)
	fmt.Printf("  Email: %s\n", user.Email)
	fmt.Printf("  Full Name: %s\n", user.FullName)
	fmt.Printf("  Role: %s\n", user.Role)
	fmt.Printf("  Created: %s\n", user.CreatedAt.Format("2006-01-02 15:04:05"))
}

func queryModelComplete(
	ctx context.Context,
	client *syfthub.Client,
	model string,
	dataSources []string,
	prompt string,
	topK, maxTokens int,
	temperature float64,
) {
	printHeader("Step 2: RAG Chat Query")

	fmt.Println("Sending request to aggregator...")
	fmt.Printf("  Model: %s\n", model)
	if len(dataSources) > 0 {
		fmt.Printf("  Data Sources: %s\n", strings.Join(dataSources, ", "))
	}
	displayPrompt := prompt
	if len(displayPrompt) > 100 {
		displayPrompt = displayPrompt[:100] + "..."
	}
	fmt.Printf("  Prompt: %s\n\n", displayPrompt)

	chat := client.Chat()
	response, err := chat.Complete(ctx, &syfthub.ChatCompleteRequest{
		Prompt:      prompt,
		Model:       model,
		DataSources: dataSources,
		TopK:        topK,
		MaxTokens:   maxTokens,
		Temperature: temperature,
	})
	if err != nil {
		var epErr *syfthub.EndpointResolutionError
		if errors.As(err, &epErr) {
			printError(fmt.Sprintf("Failed to resolve endpoint '%s': %s", epErr.Path, epErr.Message))
		}
		printError(fmt.Sprintf("Chat request failed: %v", err))
	}

	fmt.Println("Response:")
	fmt.Println(strings.Repeat("-", 40))
	fmt.Println(response.Response)
	fmt.Println(strings.Repeat("-", 40))

	// Display retrieval info
	if len(response.RetrievalInfo) > 0 {
		fmt.Println("\nSources Used:")
		for _, source := range response.RetrievalInfo {
			statusIcon := "+"
			if source.Status != syfthub.SourceStatusSuccess {
				statusIcon = "!"
			}
			fmt.Printf("  [%s] %s: %d docs\n", statusIcon, source.Path, source.DocumentsRetrieved)
			if source.ErrorMessage != nil && *source.ErrorMessage != "" {
				fmt.Printf("      Error: %s\n", *source.ErrorMessage)
			}
		}
	}

	// Display metadata
	fmt.Println("\nPerformance Metrics:")
	fmt.Printf("  Retrieval Time: %dms\n", response.Metadata.RetrievalTimeMs)
	fmt.Printf("  Generation Time: %dms\n", response.Metadata.GenerationTimeMs)
	fmt.Printf("  Total Time: %dms\n", response.Metadata.TotalTimeMs)

	// Display token usage
	if response.Usage != nil {
		fmt.Println("\nToken Usage:")
		fmt.Printf("  Prompt Tokens: %d\n", response.Usage.PromptTokens)
		fmt.Printf("  Completion Tokens: %d\n", response.Usage.CompletionTokens)
		fmt.Printf("  Total Tokens: %d\n", response.Usage.TotalTokens)
	}
}

func queryModelStream(
	ctx context.Context,
	client *syfthub.Client,
	model string,
	dataSources []string,
	prompt string,
	topK, maxTokens int,
	temperature float64,
) {
	printHeader("Step 2: RAG Chat Query (Streaming)")

	fmt.Println("Streaming request to aggregator...")
	fmt.Printf("  Model: %s\n", model)
	if len(dataSources) > 0 {
		fmt.Printf("  Data Sources: %s\n", strings.Join(dataSources, ", "))
	}
	displayPrompt := prompt
	if len(displayPrompt) > 100 {
		displayPrompt = displayPrompt[:100] + "..."
	}
	fmt.Printf("  Prompt: %s\n\n", displayPrompt)

	chat := client.Chat()
	events, errChan := chat.Stream(ctx, &syfthub.ChatCompleteRequest{
		Prompt:      prompt,
		Model:       model,
		DataSources: dataSources,
		TopK:        topK,
		MaxTokens:   maxTokens,
		Temperature: temperature,
	})

	fmt.Println("Response:")
	fmt.Println(strings.Repeat("-", 40))

	var retrievalInfo []syfthub.SourceInfo
	var metadata syfthub.ChatMetadata

	for event := range events {
		switch e := event.(type) {
		case *syfthub.RetrievalStartEvent:
			fmt.Print("\r[Retrieving from sources...]")

		case *syfthub.SourceCompleteEvent:
			fmt.Print("\r" + strings.Repeat(" ", 50) + "\r")

		case *syfthub.RetrievalCompleteEvent:
			retrievalInfo = e.Sources
			totalDocs := 0
			for _, s := range e.Sources {
				totalDocs += s.DocumentsRetrieved
			}
			fmt.Printf("[Retrieved %d docs]\n\n", totalDocs)

		case *syfthub.GenerationStartEvent:
			// Model starting, output will follow

		case *syfthub.TokenEvent:
			fmt.Print(e.Content)

		case *syfthub.DoneEvent:
			metadata = e.Metadata
			fmt.Println() // Newline after streaming content

		case *syfthub.ErrorEvent:
			fmt.Printf("\n[ERROR: %s]\n", e.Error)
		}
	}

	// Check for errors
	if err := <-errChan; err != nil {
		var epErr *syfthub.EndpointResolutionError
		if errors.As(err, &epErr) {
			printError(fmt.Sprintf("Failed to resolve endpoint '%s': %s", epErr.Path, epErr.Message))
		}
		printError(fmt.Sprintf("Chat request failed: %v", err))
	}

	fmt.Println(strings.Repeat("-", 40))

	// Display retrieval info
	if len(retrievalInfo) > 0 {
		fmt.Println("\nSources Used:")
		for _, source := range retrievalInfo {
			statusIcon := "+"
			if source.Status != syfthub.SourceStatusSuccess {
				statusIcon = "!"
			}
			fmt.Printf("  [%s] %s: %d docs\n", statusIcon, source.Path, source.DocumentsRetrieved)
			if source.ErrorMessage != nil && *source.ErrorMessage != "" {
				fmt.Printf("      Error: %s\n", *source.ErrorMessage)
			}
		}
	}

	// Display metadata
	fmt.Println("\nPerformance Metrics:")
	fmt.Printf("  Retrieval Time: %dms\n", metadata.RetrievalTimeMs)
	fmt.Printf("  Generation Time: %dms\n", metadata.GenerationTimeMs)
	fmt.Printf("  Total Time: %dms\n", metadata.TotalTimeMs)
}

func checkAccounting(ctx context.Context, client *syfthub.Client) {
	printHeader("Step 3: Accounting Balance")

	accounting, err := client.Accounting(ctx)
	if err != nil {
		var configErr *syfthub.ConfigurationError
		if errors.As(err, &configErr) {
			fmt.Printf("Configuration error: %s\n", configErr.Message)
			return
		}
		fmt.Printf("Failed to fetch accounting info: %v\n", err)
		return
	}

	user, err := accounting.GetUser(ctx)
	if err != nil {
		fmt.Printf("Failed to fetch accounting info: %v\n", err)
		return
	}

	fmt.Printf("Account ID: %s\n", user.ID)
	fmt.Printf("Email: %s\n", user.Email)
	fmt.Printf("Balance: %.2f credits\n", user.Balance)
	if user.Organization != nil && *user.Organization != "" {
		fmt.Printf("Organization: %s\n", *user.Organization)
	}

	// Show recent transactions
	fmt.Println("\nRecent Transactions:")
	transactions, err := accounting.GetTransactions(ctx).Take(ctx, 5)
	if err != nil {
		fmt.Printf("  Failed to fetch transactions: %v\n", err)
		return
	}

	if len(transactions) > 0 {
		for _, tx := range transactions {
			direction := "-"
			if tx.RecipientEmail == user.Email {
				direction = "+"
			}
			statusIcon := "?"
			switch tx.Status {
			case syfthub.TransactionStatusPending:
				statusIcon = "?"
			case syfthub.TransactionStatusCompleted:
				statusIcon = "+"
			case syfthub.TransactionStatusCancelled:
				statusIcon = "x"
			}
			fmt.Printf("  [%s] %s%.2f (%s -> %s) @ %s\n",
				statusIcon, direction, tx.Amount,
				tx.SenderEmail, tx.RecipientEmail,
				tx.CreatedAt.Format("2006-01-02 15:04"))
		}
	} else {
		fmt.Println("  No transactions found.")
	}
}
