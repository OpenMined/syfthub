package main

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
)

// builtinPackage holds the definition for a seed package.
type builtinPackage struct {
	CreatePackageRequest
	Readme string
	Runner string
}

var builtinPackages = []builtinPackage{
	{
		CreatePackageRequest: CreatePackageRequest{
			Slug:        "echo-model",
			Name:        "Echo Model",
			Description: "Simple echo model that mirrors back user messages. Great for testing.",
			Type:        PackageTypeModel,
			Author:      "syfthub",
			Version:     "1.0.0",
			Tags:        []string{"echo", "test", "starter"},
			Config:      []PackageConfigField{},
		},
		Readme: `---
slug: echo-model
type: model
name: Echo Model
description: Simple echo model that mirrors back user messages
enabled: true
version: "1.0.0"
env:
  required: []
  optional: []
  inherit: [PATH, HOME]
runtime:
  mode: subprocess
  workers: 1
  timeout: 30
---

# Echo Model

A simple model endpoint that echoes back user messages. Useful for testing your SyftHub setup.
`,
		Runner: `def handler(messages: list, context: dict = None) -> str:
    for msg in reversed(messages):
        if msg.get("role") == "user":
            return f"Echo: {msg.get('content', '')}"
    return "Echo: (no message received)"
`,
	},
	{
		CreatePackageRequest: CreatePackageRequest{
			Slug:        "openai-proxy",
			Name:        "OpenAI GPT Proxy",
			Description: "Proxies requests to OpenAI's chat completions API. Requires an API key.",
			Type:        PackageTypeModel,
			Author:      "syfthub",
			Version:     "1.0.0",
			Tags:        []string{"openai", "gpt", "llm", "proxy"},
			Config: []PackageConfigField{
				{Key: "OPENAI_API_KEY", Label: "OpenAI API Key", Description: "Your key from platform.openai.com/api-keys", Required: true, Secret: true, Default: ""},
				{Key: "OPENAI_MODEL", Label: "Model", Description: "Which model to use", Required: false, Secret: false, Default: "gpt-4o-mini"},
			},
		},
		Readme: `---
slug: openai-proxy
type: model
name: OpenAI GPT Proxy
description: Proxies requests to OpenAI chat completions API
enabled: true
version: "1.0.0"
env:
  required: [OPENAI_API_KEY]
  optional: [OPENAI_MODEL]
  inherit: [PATH, HOME]
runtime:
  mode: subprocess
  workers: 1
  timeout: 60
---

# OpenAI GPT Proxy

Forwards chat messages to OpenAI's API and returns the response.

## Configuration

- **OPENAI_API_KEY** (required): Your OpenAI API key
- **OPENAI_MODEL** (optional): Model to use, defaults to ` + "`gpt-4o-mini`" + `
`,
		Runner: `import os
import json
from urllib.request import Request, urlopen

def handler(messages: list, context: dict = None) -> str:
    api_key = os.environ.get("OPENAI_API_KEY", "")
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    if not api_key:
        return "Error: OPENAI_API_KEY not set"

    payload = json.dumps({"model": model, "messages": messages}).encode()
    req = Request(
        "https://api.openai.com/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(req, timeout=55) as resp:
            data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"OpenAI API error: {e}"
`,
	},
	{
		CreatePackageRequest: CreatePackageRequest{
			Slug:        "static-faq",
			Name:        "Static FAQ",
			Description: "A data source that returns FAQ entries matching the query via simple keyword search.",
			Type:        PackageTypeDataSource,
			Author:      "syfthub",
			Version:     "1.0.0",
			Tags:        []string{"faq", "static", "starter"},
			Config:      []PackageConfigField{},
		},
		Readme: `---
slug: static-faq
type: data_source
name: Static FAQ
description: Returns FAQ entries matching the query via keyword search
enabled: true
version: "1.0.0"
env:
  required: []
  optional: []
  inherit: [PATH, HOME]
runtime:
  mode: subprocess
  workers: 1
  timeout: 30
---

# Static FAQ

A simple data source with hardcoded FAQ entries. Returns documents that match the query keywords.
`,
		Runner: `FAQ_ENTRIES = [
    {"id": "1", "q": "What is SyftHub?", "a": "SyftHub is an AI/ML endpoint registry and discovery platform, like GitHub for AI endpoints."},
    {"id": "2", "q": "How do I create an endpoint?", "a": "Use the SyftHub Desktop app or the CLI to create a new endpoint with a runner.py handler."},
    {"id": "3", "q": "What types of endpoints exist?", "a": "There are two types: 'model' endpoints that accept messages and return text, and 'data_source' endpoints that accept queries and return documents."},
    {"id": "4", "q": "How does the marketplace work?", "a": "The marketplace lists pre-built endpoint packages. You can install them with one click and configure API keys during setup."},
    {"id": "5", "q": "What is NATS tunneling?", "a": "NATS tunneling lets endpoints behind firewalls connect to the hub via encrypted pub/sub messaging instead of direct HTTP."},
]

def handler(query: str, context: dict = None) -> list[dict]:
    query_lower = query.lower()
    results = []
    for entry in FAQ_ENTRIES:
        text = f"{entry['q']} {entry['a']}".lower()
        words = query_lower.split()
        score = sum(1 for w in words if w in text) / max(len(words), 1)
        if score > 0:
            results.append({
                "document_id": entry["id"],
                "content": f"Q: {entry['q']}\nA: {entry['a']}",
                "metadata": {"source": "faq"},
                "similarity_score": round(min(score, 1.0), 2),
            })
    results.sort(key=lambda d: d["similarity_score"], reverse=True)
    return results[:5]
`,
	},
	{
		CreatePackageRequest: CreatePackageRequest{
			Slug:        "rss-feed-source",
			Name:        "RSS Feed Reader",
			Description: "Fetches and searches articles from any RSS/Atom feed URL.",
			Type:        PackageTypeDataSource,
			Author:      "syfthub",
			Version:     "1.0.0",
			Tags:        []string{"rss", "feed", "news", "web"},
			Config: []PackageConfigField{
				{Key: "FEED_URL", Label: "RSS Feed URL", Description: "Full URL to an RSS or Atom feed", Required: true, Secret: false, Default: "https://hnrss.org/frontpage"},
				{Key: "MAX_ITEMS", Label: "Max Items", Description: "Maximum number of items to fetch", Required: false, Secret: false, Default: "20"},
			},
		},
		Readme: `---
slug: rss-feed-source
type: data_source
name: RSS Feed Reader
description: Fetches and searches articles from an RSS/Atom feed
enabled: true
version: "1.0.0"
env:
  required: [FEED_URL]
  optional: [MAX_ITEMS]
  inherit: [PATH, HOME]
runtime:
  mode: subprocess
  workers: 1
  timeout: 30
---

# RSS Feed Reader

Fetches articles from a configured RSS/Atom feed and returns entries matching the query.

## Configuration

- **FEED_URL** (required): URL of the RSS or Atom feed
- **MAX_ITEMS** (optional): Max items to fetch, defaults to 20
`,
		Runner: `import os
import re
import xml.etree.ElementTree as ET
from urllib.request import urlopen

def handler(query: str, context: dict = None) -> list[dict]:
    feed_url = os.environ.get("FEED_URL", "https://hnrss.org/frontpage")
    max_items = int(os.environ.get("MAX_ITEMS", "20"))

    try:
        with urlopen(feed_url, timeout=10) as resp:
            xml_data = resp.read()
    except Exception as e:
        return [{"document_id": "error", "content": f"Failed to fetch feed: {e}", "metadata": {}, "similarity_score": 0.0}]

    root = ET.fromstring(xml_data)
    items = []

    # Handle RSS 2.0
    for item in root.findall(".//item")[:max_items]:
        title = item.findtext("title", "")
        desc = item.findtext("description", "")
        link = item.findtext("link", "")
        desc_clean = re.sub(r"<[^>]+>", "", desc)[:500]
        items.append({"title": title, "content": desc_clean, "link": link})

    # Handle Atom
    if not items:
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.findall(".//atom:entry", ns)[:max_items]:
            title = entry.findtext("atom:title", "", ns)
            summary = entry.findtext("atom:summary", "", ns)
            link_el = entry.find("atom:link", ns)
            link = link_el.get("href", "") if link_el is not None else ""
            items.append({"title": title, "content": re.sub(r"<[^>]+>", "", summary)[:500], "link": link})

    query_lower = query.lower()
    results = []
    for i, item in enumerate(items):
        text = f"{item['title']} {item['content']}".lower()
        words = query_lower.split()
        score = sum(1 for w in words if w in text) / max(len(words), 1)
        if score > 0:
            results.append({
                "document_id": str(i),
                "content": f"{item['title']}\n{item['content']}",
                "metadata": {"link": item["link"], "source": "rss"},
                "similarity_score": round(min(score, 1.0), 2),
            })

    results.sort(key=lambda d: d["similarity_score"], reverse=True)
    return results[:10] if results else [{"document_id": "0", "content": "No matching articles found.", "metadata": {}, "similarity_score": 0.0}]
`,
	},
}

// SeedBuiltinPackages inserts the 4 built-in packages if they don't exist.
func SeedBuiltinPackages(ctx context.Context, store *Store, baseURL string) error {
	for _, bp := range builtinPackages {
		// Build zip
		zipData, zipHash, err := buildZip(bp.Slug, bp.Readme, bp.Runner)
		if err != nil {
			return fmt.Errorf("build zip for %s: %w", bp.Slug, err)
		}

		pkg := &Package{
			Slug:        bp.Slug,
			Name:        bp.Name,
			Description: bp.Description,
			Type:        bp.Type,
			Author:      bp.Author,
			Version:     bp.Version,
			Tags:        bp.Tags,
			Config:      bp.Config,
			ZipSize:     int64(len(zipData)),
			ZipSHA256:   zipHash,
			BuiltIn:     true,
		}
		if pkg.Tags == nil {
			pkg.Tags = []string{}
		}
		if pkg.Config == nil {
			pkg.Config = []PackageConfigField{}
		}

		// Create package (skip if already exists)
		err = store.Create(ctx, pkg)
		if err != nil {
			if errors.Is(err, ErrConflict) {
				slog.Info("seed: package already exists, skipping", "slug", bp.Slug)
				continue
			}
			return fmt.Errorf("seed %s: %w", bp.Slug, err)
		}

		// Store the zip data
		if err := store.SetZip(ctx, bp.Slug, zipData, zipHash); err != nil {
			return fmt.Errorf("seed zip for %s: %w", bp.Slug, err)
		}

		slog.Info("seed: created package", "slug", bp.Slug, "zipSize", len(zipData))
	}
	return nil
}
