---
name: syfthub-cli
description: Execute SyftHub CLI commands for privacy-preserving AI interactions. Use when the user wants to (1) authenticate with SyftHub platform, (2) browse or list AI endpoints and users, (3) query AI models with RAG (retrieval-augmented generation), (4) manage aggregator or accounting service configurations, (5) update the CLI, or (6) any task involving the `syft` command-line tool. Triggers on requests like "login to syfthub", "list endpoints", "query alice/gpt", "syft ls", "syft query", or any mention of the syft CLI.
---

# SyftHub CLI

The `syft` CLI is a standalone command-line tool for interacting with the SyftHub privacy-preserving AI platform. It provides Unix-style commands for authentication, endpoint discovery, RAG queries, and configuration management.

## Quick Reference

| Command | Purpose |
|---------|---------|
| `syft login` | Authenticate with username/password |
| `syft logout` | Clear stored credentials |
| `syft ls` | List active users |
| `syft ls <user>` | List user's endpoints |
| `syft ls <user>/<endpoint>` | Show endpoint details |
| `syft query <target> "<prompt>"` | RAG query with streaming output |
| `syft config show` | Display current configuration |
| `syft upgrade` | Update CLI to latest version |

## Authentication

```bash
# Login (prompts for credentials)
syft login

# Logout (clears tokens)
syft logout
```

Tokens stored in `~/.syfthub/config.json`:
- Access token: 30 min TTL
- Refresh token: 7 days TTL

## Browsing Endpoints

```bash
# List all active users (grid format with type icons)
syft ls
# Output: ⚡ alice/gpt-4   📦 bob/ml-papers   🔀 carol/hybrid

# List specific user's endpoints
syft ls alice

# Show endpoint details (includes README)
syft ls alice/gpt-model

# Long format (table with TYPE, VISIBILITY, STARS)
syft ls -l
syft ls --long

# JSON output (any command)
syft ls --json
```

**Type Icons:**
- ⚡ = model (LLM generation)
- 📦 = data_source (RAG retrieval)
- 🔀 = model_data_source (combined)

## RAG Queries

```bash
# Basic query (streams tokens to terminal)
syft query alice/gpt "Explain quantum computing"

# JSON output
syft query alice/gpt "Hello world" --json
```

The query command:
1. Acquires satellite tokens for the target endpoint
2. Sends request to aggregator service
3. Streams response tokens in real-time

## Configuration Management

Config file: `~/.syfthub/config.json`

```bash
# Show current config
syft config show

# Set config value
syft config set timeout 60
syft config set hub_url https://hub.syftbox.org
```

### Aggregator Management

```bash
# Add aggregator alias
syft add aggregator prod https://aggregator.syftbox.org
syft add aggregator staging https://staging-aggregator.example.com

# List configured aggregators
syft list aggregator

# Update aggregator
syft update aggregator prod

# Remove aggregator
syft remove aggregator staging
```

### Accounting Service Management

```bash
# Add accounting service
syft add accounting main https://accounting.example.com

# List accounting services
syft list accounting
```

## CLI Updates

```bash
# Check and install updates
syft upgrade

# Check only (no install)
syft upgrade --check

# Auto-confirm update
syft upgrade -y
```

Disable auto-update checks:
```bash
export SYFT_NO_UPDATE_CHECK=1
# or
syft --no-update-check <command>
```

## Shell Completion

```bash
syft --install-completion bash
syft --install-completion zsh
syft --install-completion fish
```

Completions are cached for 5 minutes.

## Installation

**Binary (recommended):**
```bash
curl -fsSL https://raw.githubusercontent.com/OpenMined/syfthub/main/cli/install.sh | sh

# Specific version
SYFT_VERSION=1.2.0 curl -fsSL https://raw.githubusercontent.com/OpenMined/syfthub/main/cli/install.sh | sh

# Custom directory
SYFT_INSTALL_DIR=~/.local/bin curl -fsSL https://raw.githubusercontent.com/OpenMined/syfthub/main/cli/install.sh | sh
```

**pip:**
```bash
pip install syfthub-cli
# or
uv add syfthub-cli
```

## Common Workflows

### First-time Setup
```bash
curl -fsSL https://raw.githubusercontent.com/OpenMined/syfthub/main/cli/install.sh | sh
syft login
syft ls
```

### Discover and Query
```bash
syft ls                              # Browse users
syft ls alice                        # See alice's endpoints
syft ls alice/gpt-model              # View details
syft query alice/gpt-model "Hello"   # Query the model
```

### Configure Custom Aggregator
```bash
syft add aggregator myagg https://my-aggregator.example.com
syft config set defaults.aggregator myagg
syft config show
```

## Config File Structure

```json
{
  "access_token": "...",
  "refresh_token": "...",
  "aggregators": {
    "prod": "https://aggregator.example.com"
  },
  "accounting_services": {
    "main": "https://accounting.example.com"
  },
  "defaults": {
    "aggregator": "prod"
  },
  "timeout": 30,
  "hub_url": "https://hub.syftbox.org"
}
```
