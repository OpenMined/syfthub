package syfthub

import "context"

// SearchResource provides retrieval-only queries via the Aggregator.
// It is a thin facade over ChatResource.Retrieve, exposed as client.Search()
// to mirror the shape of client.Chat().
//
// Example usage:
//
//	result, err := client.Search().Query(ctx, &syfthub.SearchRequest{
//	    Prompt:      "What happened at EPFL this week?",
//	    DataSources: []string{"epfl-news/epfl-news"},
//	})
//	for _, doc := range result.Documents {
//	    fmt.Println(doc.Title, "->", doc.Content[:80])
//	}
type SearchResource struct {
	chat *ChatResource
}

func newSearchResource(chat *ChatResource) *SearchResource {
	return &SearchResource{chat: chat}
}

// Query retrieves documents from data sources without invoking a model.
func (s *SearchResource) Query(ctx context.Context, req *SearchRequest) (*SearchResponse, error) {
	return s.chat.Retrieve(ctx, req)
}
