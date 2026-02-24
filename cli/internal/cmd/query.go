package cmd

import (
	"context"
	"fmt"
	"time"

	"github.com/spf13/cobra"

	"github.com/OpenMined/syfthub/cli/internal/completion"
	"github.com/OpenMined/syfthub/cli/internal/config"
	"github.com/OpenMined/syfthub/cli/internal/output"
	"github.com/openmined/syfthub/sdk/golang/syfthub"
)

var (
	querySources     []string
	queryAggregator  string
	queryTopK        int
	queryMaxTokens   int
	queryTemperature float64
	queryVerbose     bool
	queryJSONOutput  bool
)

var queryCmd = &cobra.Command{
	Use:   "query <target> <prompt>",
	Short: "Query endpoints using RAG",
	Long: `Query endpoints using RAG.

Sends a query to a model endpoint, optionally retrieving context from
data source endpoints.

Examples:

    syft query alice/gpt4 "What is machine learning?"
    syft query alice/gpt4 --source bob/docs "Explain the API"
    syft query alice/gpt4 -s bob/docs -s carol/data "Compare approaches"`,
	Args:              cobra.ExactArgs(2),
	RunE:              runQuery,
	ValidArgsFunction: completion.CompleteModelEndpoint,
}

func init() {
	queryCmd.Flags().StringArrayVarP(&querySources, "source", "s", nil, "Data source endpoints to query. Can be specified multiple times.")
	queryCmd.Flags().StringVarP(&queryAggregator, "aggregator", "a", "", "Aggregator alias or URL to use")
	queryCmd.Flags().IntVarP(&queryTopK, "top-k", "k", 5, "Number of documents to retrieve")
	queryCmd.Flags().IntVarP(&queryMaxTokens, "max-tokens", "m", 1024, "Maximum tokens in response")
	queryCmd.Flags().Float64VarP(&queryTemperature, "temperature", "t", 0.7, "Sampling temperature (0.0-2.0)")
	queryCmd.Flags().BoolVarP(&queryVerbose, "verbose", "V", false, "Show retrieval progress")
	queryCmd.Flags().BoolVar(&queryJSONOutput, "json", false, "Output result as JSON (non-streaming)")

	// Register completion for --source flag
	_ = queryCmd.RegisterFlagCompletionFunc("source", completion.CompleteDataSource)
	_ = queryCmd.RegisterFlagCompletionFunc("aggregator", completion.CompleteAggregatorAlias)
}

func runQuery(cmd *cobra.Command, args []string) error {
	target := args[0]
	prompt := args[1]

	cfg := config.Load()

	// Resolve aggregator URL
	aggregatorURL := cfg.GetAggregatorURL(queryAggregator)

	// Create client options
	opts := []syfthub.Option{
		syfthub.WithBaseURL(cfg.HubURL),
		syfthub.WithTimeout(time.Duration(cfg.Timeout) * time.Second),
	}
	if aggregatorURL != "" {
		opts = append(opts, syfthub.WithAggregatorURL(aggregatorURL))
	}

	client, err := syfthub.NewClient(opts...)
	if err != nil {
		if queryJSONOutput {
			output.JSON(map[string]interface{}{
				"status":  "error",
				"message": err.Error(),
			})
		} else {
			output.Error("Failed to create client: %v", err)
		}
		return err
	}
	defer client.Close()

	// Set tokens if available
	if cfg.HasTokens() {
		refreshToken := ""
		if cfg.RefreshToken != nil {
			refreshToken = *cfg.RefreshToken
		}
		client.SetTokens(&syfthub.AuthTokens{
			AccessToken:  *cfg.AccessToken,
			RefreshToken: refreshToken,
		})
	}

	ctx := context.Background()

	if queryJSONOutput {
		return queryComplete(ctx, client, target, prompt, aggregatorURL)
	}
	return queryStream(ctx, client, target, prompt, aggregatorURL)
}

func queryComplete(ctx context.Context, client *syfthub.Client, target, prompt, aggregatorURL string) error {
	req := &syfthub.ChatCompleteRequest{
		Prompt:        prompt,
		Model:         target,
		DataSources:   querySources,
		TopK:          queryTopK,
		MaxTokens:     queryMaxTokens,
		Temperature:   queryTemperature,
		AggregatorURL: aggregatorURL,
	}

	response, err := client.Chat().Complete(ctx, req)
	if err != nil {
		output.JSON(map[string]interface{}{
			"status":  "error",
			"message": err.Error(),
		})
		return err
	}

	// Format sources
	sources := make([]map[string]interface{}, 0)
	for title, doc := range response.Sources {
		sources = append(sources, map[string]interface{}{
			"title": title,
			"slug":  doc.Slug,
		})
	}

	// Format retrieval info
	retrievalInfo := make([]map[string]interface{}, 0)
	for _, info := range response.RetrievalInfo {
		retrievalInfo = append(retrievalInfo, map[string]interface{}{
			"path":                info.Path,
			"documents_retrieved": info.DocumentsRetrieved,
			"status":              string(info.Status),
		})
	}

	// Format usage
	usage := map[string]int{
		"prompt_tokens":     0,
		"completion_tokens": 0,
		"total_tokens":      0,
	}
	if response.Usage != nil {
		usage["prompt_tokens"] = response.Usage.PromptTokens
		usage["completion_tokens"] = response.Usage.CompletionTokens
		usage["total_tokens"] = response.Usage.TotalTokens
	}

	output.JSON(map[string]interface{}{
		"status":         "success",
		"response":       response.Response,
		"sources":        sources,
		"retrieval_info": retrievalInfo,
		"usage":          usage,
	})

	return nil
}

func queryStream(ctx context.Context, client *syfthub.Client, target, prompt, aggregatorURL string) error {
	req := &syfthub.ChatCompleteRequest{
		Prompt:        prompt,
		Model:         target,
		DataSources:   querySources,
		TopK:          queryTopK,
		MaxTokens:     queryMaxTokens,
		Temperature:   queryTemperature,
		AggregatorURL: aggregatorURL,
	}

	events, errs := client.Chat().Stream(ctx, req)

	for {
		select {
		case event, ok := <-events:
			if !ok {
				return nil
			}

			switch e := event.(type) {
			case *syfthub.RetrievalStartEvent:
				if queryVerbose {
					output.Dim.Println("Retrieving from sources...")
				}

			case *syfthub.SourceCompleteEvent:
				if queryVerbose {
					output.Dim.Printf("  Retrieved %d docs from %s\n",
						e.Source.DocumentsRetrieved, e.Source.Path)
				}

			case *syfthub.RetrievalCompleteEvent:
				if queryVerbose {
					total := 0
					for _, s := range e.Sources {
						total += s.DocumentsRetrieved
					}
					output.Dim.Printf("Retrieved %d documents total\n", total)
					fmt.Println()
				}

			case *syfthub.GenerationStartEvent:
				if queryVerbose {
					output.Dim.Println("Generating response...")
				}

			case *syfthub.TokenEvent:
				output.StreamToken(e.Content)

			case *syfthub.DoneEvent:
				output.StreamDone()

			case *syfthub.ErrorEvent:
				output.StreamDone()
				output.Error("%s", e.Error)
				return fmt.Errorf("%s", e.Error)
			}

		case err := <-errs:
			if err != nil {
				output.StreamDone()
				output.Error("%v", err)
				return err
			}
		}
	}
}
