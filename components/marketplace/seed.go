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
	Readme    string
	Runner    string
	Pyproject string // optional; included in zip if non-empty
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
	{
		CreatePackageRequest: CreatePackageRequest{
			Slug:        "llm-proxy",
			Name:        "LLM Proxy",
			Description: "Universal LLM proxy supporting OpenAI, Anthropic, Google Gemini, and OpenRouter. Configure your provider and model via environment variables.",
			Type:        PackageTypeModel,
			Author:      "syfthub",
			Version:     "1.0.0",
			Tags:        []string{"llm", "proxy", "openai", "anthropic", "gemini", "openrouter", "multi-provider"},
			Config: []PackageConfigField{
				{Key: "LLM_API_KEY", Label: "API Key", Description: "API key for your chosen provider", Required: true, Secret: true, Default: ""},
				{Key: "LLM_PROVIDER", Label: "Provider", Description: "Provider: openai, anthropic, google, or openrouter", Required: true, Secret: false, Default: "openai"},
				{Key: "LLM_MODEL", Label: "Model", Description: "Model name (leave empty for provider default)", Required: false, Secret: false, Default: ""},
			},
		},
		Readme: `---
slug: llm-proxy
type: model
name: LLM Proxy
description: Universal LLM proxy for OpenAI, Anthropic, Google Gemini, and OpenRouter
enabled: true
version: "1.0.0"
env:
  required: [LLM_API_KEY, LLM_PROVIDER]
  optional: [LLM_MODEL]
  inherit: [PATH, HOME]
runtime:
  mode: subprocess
  workers: 1
  timeout: 60
---

# LLM Proxy

A universal model endpoint that forwards chat messages to your chosen LLM provider.

## Supported Providers

| Provider | Default Model | API Key Source |
|----------|--------------|----------------|
| openai | gpt-4o-mini | platform.openai.com/api-keys |
| anthropic | claude-sonnet-4-20250514 | console.anthropic.com |
| google | gemini-2.0-flash | aistudio.google.com/apikey |
| openrouter | openai/gpt-4o-mini | openrouter.ai/keys |

## Configuration

- **LLM_API_KEY** (required): API key for your provider
- **LLM_PROVIDER** (required): One of openai, anthropic, google, openrouter
- **LLM_MODEL** (optional): Override the default model for your provider
`,
		Runner: `import os
import json
from urllib.request import Request, urlopen

PROVIDERS = {
    "openai": {
        "url": "https://api.openai.com/v1/chat/completions",
        "default_model": "gpt-4o-mini",
    },
    "anthropic": {
        "url": "https://api.anthropic.com/v1/messages",
        "default_model": "claude-sonnet-4-20250514",
    },
    "google": {
        "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "default_model": "gemini-2.0-flash",
    },
    "openrouter": {
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "default_model": "openai/gpt-4o-mini",
    },
}


def _call_openai_compatible(url, api_key, model, messages):
    payload = json.dumps({"model": model, "messages": messages}).encode()
    req = Request(url, data=payload, headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    })
    with urlopen(req, timeout=55) as resp:
        return json.loads(resp.read())["choices"][0]["message"]["content"]


def _call_anthropic(api_key, model, messages):
    system = None
    chat = []
    for m in messages:
        if m.get("role") == "system":
            system = m.get("content", "")
        else:
            chat.append({"role": m.get("role", "user"), "content": m.get("content", "")})
    if not chat:
        chat = [{"role": "user", "content": "Hello"}]

    body = {"model": model, "max_tokens": 4096, "messages": chat}
    if system:
        body["system"] = system

    req = Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode(),
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
    )
    with urlopen(req, timeout=55) as resp:
        data = json.loads(resp.read())
        return "".join(b["text"] for b in data.get("content", []) if b.get("type") == "text")


def handler(messages: list, context: dict = None) -> str:
    api_key = os.environ.get("LLM_API_KEY", "")
    provider = os.environ.get("LLM_PROVIDER", "openai").lower().strip()
    model = os.environ.get("LLM_MODEL", "").strip()

    if not api_key:
        return "Error: LLM_API_KEY not set"

    if provider not in PROVIDERS:
        return f"Error: unknown provider '{provider}'. Use: openai, anthropic, google, openrouter"

    cfg = PROVIDERS[provider]
    model = model or cfg["default_model"]

    try:
        if provider == "anthropic":
            return _call_anthropic(api_key, model, messages)
        return _call_openai_compatible(cfg["url"], api_key, model, messages)
    except Exception as e:
        return f"{provider} API error: {e}"
`,
	},
	{
		CreatePackageRequest: CreatePackageRequest{
			Slug:        "chromadb-source",
			Name:        "ChromaDB Source",
			Description: "Data source that queries a ChromaDB collection. Supports local and remote Chroma servers.",
			Type:        PackageTypeDataSource,
			Author:      "syfthub",
			Version:     "1.0.0",
			Tags:        []string{"chromadb", "vector", "embeddings", "search", "rag"},
			Config: []PackageConfigField{
				{Key: "CHROMA_HOST", Label: "Chroma Host", Description: "Chroma server URL (e.g. http://localhost:8000)", Required: true, Secret: false, Default: "http://localhost:8000"},
				{Key: "CHROMA_COLLECTION", Label: "Collection", Description: "Name of the collection to query", Required: true, Secret: false, Default: ""},
				{Key: "CHROMA_API_KEY", Label: "API Key", Description: "API key (for Chroma Cloud or authenticated servers)", Required: false, Secret: true, Default: ""},
				{Key: "CHROMA_TOP_K", Label: "Top K", Description: "Number of results to return", Required: false, Secret: false, Default: "5"},
			},
		},
		Readme: `---
slug: chromadb-source
type: data_source
name: ChromaDB Source
description: Queries a ChromaDB collection for relevant documents
enabled: true
version: "1.0.0"
env:
  required: [CHROMA_HOST, CHROMA_COLLECTION]
  optional: [CHROMA_API_KEY, CHROMA_TOP_K]
  inherit: [PATH, HOME]
runtime:
  mode: subprocess
  workers: 1
  timeout: 30
---

# ChromaDB Source

Queries a ChromaDB collection and returns the most relevant documents for the given query.

## Configuration

- **CHROMA_HOST** (required): URL of the Chroma server
- **CHROMA_COLLECTION** (required): Name of the collection to query
- **CHROMA_API_KEY** (optional): API key for authenticated servers
- **CHROMA_TOP_K** (optional): Number of results, defaults to 5
`,
		Runner: `import os
import chromadb
from chromadb.config import Settings

def handler(query: str, context: dict = None) -> list[dict]:
    host = os.environ.get("CHROMA_HOST", "http://localhost:8000")
    collection_name = os.environ.get("CHROMA_COLLECTION", "")
    api_key = os.environ.get("CHROMA_API_KEY", "")
    top_k = int(os.environ.get("CHROMA_TOP_K", "5"))

    if not collection_name:
        return [{"document_id": "error", "content": "Error: CHROMA_COLLECTION not set", "metadata": {}, "similarity_score": 0.0}]

    try:
        settings = Settings(chroma_client_auth_provider="chromadb.auth.token_authn.TokenAuthClientProvider",
                            chroma_client_auth_credentials=api_key) if api_key else Settings()
        client = chromadb.HttpClient(host=host, settings=settings)
        collection = client.get_collection(collection_name)

        results = collection.query(query_texts=[query], n_results=top_k, include=["documents", "metadatas", "distances"])

        docs = []
        for i in range(len(results["ids"][0])):
            doc_id = results["ids"][0][i]
            content = results["documents"][0][i] if results["documents"] else ""
            metadata = results["metadatas"][0][i] if results["metadatas"] else {}
            distance = results["distances"][0][i] if results["distances"] else 1.0
            score = round(max(0.0, 1.0 - distance), 4)
            docs.append({"document_id": doc_id, "content": content, "metadata": metadata, "similarity_score": score})
        return docs if docs else [{"document_id": "0", "content": "No matching documents found.", "metadata": {}, "similarity_score": 0.0}]
    except Exception as e:
        return [{"document_id": "error", "content": f"ChromaDB error: {e}", "metadata": {}, "similarity_score": 0.0}]
`,
		Pyproject: `[project]
name = "chromadb-source"
version = "1.0.0"
dependencies = [
    "chromadb>=1.0.0",
]
`,
	},
	{
		CreatePackageRequest: CreatePackageRequest{
			Slug:        "qdrant-source",
			Name:        "Qdrant Source",
			Description: "Data source that queries a Qdrant vector database collection. Works with local and Qdrant Cloud instances.",
			Type:        PackageTypeDataSource,
			Author:      "syfthub",
			Version:     "1.0.0",
			Tags:        []string{"qdrant", "vector", "embeddings", "search", "rag"},
			Config: []PackageConfigField{
				{Key: "QDRANT_URL", Label: "Qdrant URL", Description: "Qdrant server URL (e.g. http://localhost:6333)", Required: true, Secret: false, Default: "http://localhost:6333"},
				{Key: "QDRANT_COLLECTION", Label: "Collection", Description: "Name of the collection to query", Required: true, Secret: false, Default: ""},
				{Key: "QDRANT_API_KEY", Label: "API Key", Description: "API key (for Qdrant Cloud)", Required: false, Secret: true, Default: ""},
				{Key: "QDRANT_TOP_K", Label: "Top K", Description: "Number of results to return", Required: false, Secret: false, Default: "5"},
			},
		},
		Readme: `---
slug: qdrant-source
type: data_source
name: Qdrant Source
description: Queries a Qdrant vector database for relevant documents
enabled: true
version: "1.0.0"
env:
  required: [QDRANT_URL, QDRANT_COLLECTION]
  optional: [QDRANT_API_KEY, QDRANT_TOP_K]
  inherit: [PATH, HOME]
runtime:
  mode: subprocess
  workers: 1
  timeout: 30
---

# Qdrant Source

Queries a Qdrant collection and returns the most relevant documents using Qdrant's built-in query API.

## Configuration

- **QDRANT_URL** (required): URL of the Qdrant server
- **QDRANT_COLLECTION** (required): Name of the collection to query
- **QDRANT_API_KEY** (optional): API key for Qdrant Cloud
- **QDRANT_TOP_K** (optional): Number of results, defaults to 5
`,
		Runner: `import os
from qdrant_client import QdrantClient, models

def handler(query: str, context: dict = None) -> list[dict]:
    url = os.environ.get("QDRANT_URL", "http://localhost:6333")
    collection_name = os.environ.get("QDRANT_COLLECTION", "")
    api_key = os.environ.get("QDRANT_API_KEY", "") or None
    top_k = int(os.environ.get("QDRANT_TOP_K", "5"))

    if not collection_name:
        return [{"document_id": "error", "content": "Error: QDRANT_COLLECTION not set", "metadata": {}, "similarity_score": 0.0}]

    try:
        client = QdrantClient(url=url, api_key=api_key)

        results = client.query(collection_name=collection_name, query_text=query, limit=top_k)

        docs = []
        for point in results:
            payload = point.metadata or {}
            content = payload.pop("content", "") or payload.pop("text", "") or payload.pop("document", "") or str(payload)
            docs.append({
                "document_id": str(point.id),
                "content": content,
                "metadata": payload,
                "similarity_score": round(point.score, 4),
            })
        return docs if docs else [{"document_id": "0", "content": "No matching documents found.", "metadata": {}, "similarity_score": 0.0}]
    except Exception as e:
        return [{"document_id": "error", "content": f"Qdrant error: {e}", "metadata": {}, "similarity_score": 0.0}]
`,
		Pyproject: `[project]
name = "qdrant-source"
version = "1.0.0"
dependencies = [
    "qdrant-client>=1.13.0",
]
`,
	},
	{
		CreatePackageRequest: CreatePackageRequest{
			Slug:        "weaviate-source",
			Name:        "Weaviate Source",
			Description: "Data source that queries a Weaviate vector database. Works with local, Docker, and Weaviate Cloud instances.",
			Type:        PackageTypeDataSource,
			Author:      "syfthub",
			Version:     "1.0.0",
			Tags:        []string{"weaviate", "vector", "embeddings", "search", "rag"},
			Config: []PackageConfigField{
				{Key: "WEAVIATE_URL", Label: "Weaviate URL", Description: "Weaviate server URL (e.g. http://localhost:8080)", Required: true, Secret: false, Default: "http://localhost:8080"},
				{Key: "WEAVIATE_COLLECTION", Label: "Collection", Description: "Name of the collection to query", Required: true, Secret: false, Default: ""},
				{Key: "WEAVIATE_API_KEY", Label: "API Key", Description: "API key (for Weaviate Cloud)", Required: false, Secret: true, Default: ""},
				{Key: "WEAVIATE_TOP_K", Label: "Top K", Description: "Number of results to return", Required: false, Secret: false, Default: "5"},
			},
		},
		Readme: `---
slug: weaviate-source
type: data_source
name: Weaviate Source
description: Queries a Weaviate vector database for relevant documents
enabled: true
version: "1.0.0"
env:
  required: [WEAVIATE_URL, WEAVIATE_COLLECTION]
  optional: [WEAVIATE_API_KEY, WEAVIATE_TOP_K]
  inherit: [PATH, HOME]
runtime:
  mode: subprocess
  workers: 1
  timeout: 30
---

# Weaviate Source

Queries a Weaviate collection using hybrid search (vector + keyword) and returns relevant documents.

## Configuration

- **WEAVIATE_URL** (required): URL of the Weaviate server
- **WEAVIATE_COLLECTION** (required): Name of the collection to query
- **WEAVIATE_API_KEY** (optional): API key for Weaviate Cloud
- **WEAVIATE_TOP_K** (optional): Number of results, defaults to 5
`,
		Runner: `import os
import weaviate
from weaviate.classes.query import MetadataQuery
from weaviate.auth import Auth

def handler(query: str, context: dict = None) -> list[dict]:
    url = os.environ.get("WEAVIATE_URL", "http://localhost:8080")
    collection_name = os.environ.get("WEAVIATE_COLLECTION", "")
    api_key = os.environ.get("WEAVIATE_API_KEY", "")
    top_k = int(os.environ.get("WEAVIATE_TOP_K", "5"))

    if not collection_name:
        return [{"document_id": "error", "content": "Error: WEAVIATE_COLLECTION not set", "metadata": {}, "similarity_score": 0.0}]

    try:
        auth = Auth.api_key(api_key) if api_key else None
        client = weaviate.connect_to_custom(http_host=url.replace("http://", "").replace("https://", "").split(":")[0],
                                             http_port=int(url.split(":")[-1]) if ":" in url.split("//")[-1] else 80,
                                             http_secure=url.startswith("https"),
                                             auth_credentials=auth)

        collection = client.collections.get(collection_name)
        response = collection.query.hybrid(query=query, limit=top_k,
                                           return_metadata=MetadataQuery(score=True))

        docs = []
        for obj in response.objects:
            props = obj.properties or {}
            content = props.pop("content", "") or props.pop("text", "") or props.pop("document", "") or str(props)
            score = obj.metadata.score if obj.metadata and obj.metadata.score is not None else 0.0
            docs.append({
                "document_id": str(obj.uuid),
                "content": str(content),
                "metadata": {k: str(v) for k, v in props.items()},
                "similarity_score": round(float(score), 4),
            })

        client.close()
        return docs if docs else [{"document_id": "0", "content": "No matching documents found.", "metadata": {}, "similarity_score": 0.0}]
    except Exception as e:
        return [{"document_id": "error", "content": f"Weaviate error: {e}", "metadata": {}, "similarity_score": 0.0}]
`,
		Pyproject: `[project]
name = "weaviate-source"
version = "1.0.0"
dependencies = [
    "weaviate-client>=4.12.0",
]
`,
	},
	{
		CreatePackageRequest: CreatePackageRequest{
			Slug:        "pinecone-source",
			Name:        "Pinecone Source",
			Description: "Data source that queries a Pinecone vector database index. Works with any Pinecone serverless or pod-based index.",
			Type:        PackageTypeDataSource,
			Author:      "syfthub",
			Version:     "1.0.0",
			Tags:        []string{"pinecone", "vector", "embeddings", "search", "rag"},
			Config: []PackageConfigField{
				{Key: "PINECONE_API_KEY", Label: "API Key", Description: "Pinecone API key from app.pinecone.io", Required: true, Secret: true, Default: ""},
				{Key: "PINECONE_INDEX", Label: "Index Name", Description: "Name of the Pinecone index to query", Required: true, Secret: false, Default: ""},
				{Key: "PINECONE_NAMESPACE", Label: "Namespace", Description: "Namespace within the index (leave empty for default)", Required: false, Secret: false, Default: ""},
				{Key: "PINECONE_TOP_K", Label: "Top K", Description: "Number of results to return", Required: false, Secret: false, Default: "5"},
			},
		},
		Readme: `---
slug: pinecone-source
type: data_source
name: Pinecone Source
description: Queries a Pinecone index for relevant documents
enabled: true
version: "1.0.0"
env:
  required: [PINECONE_API_KEY, PINECONE_INDEX]
  optional: [PINECONE_NAMESPACE, PINECONE_TOP_K]
  inherit: [PATH, HOME]
runtime:
  mode: subprocess
  workers: 1
  timeout: 30
---

# Pinecone Source

Queries a Pinecone index using integrated inference and returns relevant documents.

## Configuration

- **PINECONE_API_KEY** (required): API key from app.pinecone.io
- **PINECONE_INDEX** (required): Name of the index to query
- **PINECONE_NAMESPACE** (optional): Namespace within the index
- **PINECONE_TOP_K** (optional): Number of results, defaults to 5
`,
		Runner: `import os
from pinecone import Pinecone

def handler(query: str, context: dict = None) -> list[dict]:
    api_key = os.environ.get("PINECONE_API_KEY", "")
    index_name = os.environ.get("PINECONE_INDEX", "")
    namespace = os.environ.get("PINECONE_NAMESPACE", "") or ""
    top_k = int(os.environ.get("PINECONE_TOP_K", "5"))

    if not api_key:
        return [{"document_id": "error", "content": "Error: PINECONE_API_KEY not set", "metadata": {}, "similarity_score": 0.0}]
    if not index_name:
        return [{"document_id": "error", "content": "Error: PINECONE_INDEX not set", "metadata": {}, "similarity_score": 0.0}]

    try:
        pc = Pinecone(api_key=api_key)
        index = pc.Index(index_name)

        results = index.search(namespace=namespace, query={"top_k": top_k, "inputs": {"text": query}})

        docs = []
        for match in results.get("result", {}).get("hits", []):
            metadata = match.get("fields", {})
            content = metadata.pop("content", "") or metadata.pop("text", "") or metadata.pop("document", "") or str(metadata)
            docs.append({
                "document_id": match.get("_id", ""),
                "content": content,
                "metadata": metadata,
                "similarity_score": round(match.get("_score", 0.0), 4),
            })
        return docs if docs else [{"document_id": "0", "content": "No matching documents found.", "metadata": {}, "similarity_score": 0.0}]
    except Exception as e:
        return [{"document_id": "error", "content": f"Pinecone error: {e}", "metadata": {}, "similarity_score": 0.0}]
`,
		Pyproject: `[project]
name = "pinecone-source"
version = "1.0.0"
dependencies = [
    "pinecone>=5.4.0",
]
`,
	},
}

// SeedBuiltinPackages inserts the 9 built-in packages if they don't exist.
func SeedBuiltinPackages(ctx context.Context, store *Store, baseURL string) error {
	for _, bp := range builtinPackages {
		// Build zip
		zipData, zipHash, err := buildZip(bp.Slug, bp.Readme, bp.Runner, bp.Pyproject)
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
