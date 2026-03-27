# CLI Reference

The SyftHub CLI is a Go/Cobra binary named `syft`.

## Authentication

```bash
# Interactive login
syft login

# Non-interactive login
syft login -u username -p password

# JSON output (for scripting)
syft login -u username -p password --json

# Logout
syft logout
syft logout --json

# Show current user
syft whoami
```

## Browsing Endpoints

```bash
# List users
syft ls

# List a user's endpoints
syft ls alice

# Show endpoint detail
syft ls alice/my-model

# Limit results
syft ls -n 10

# Long format (more detail)
syft ls -l

# JSON output
syft ls --json
```

## Querying (RAG)

```bash
syft query alice/my-model "What can this model do?"

# With options
syft query alice/my-model "summarize the data" \
  -s alice/data-source \
  -a my-aggregator \
  -k 5 \
  -m 1024 \
  -t 0.7 \
  -V \
  --json
```

| Flag | Description |
|------|-------------|
| `-s` | Data source endpoint |
| `-a` | Aggregator alias |
| `-k` | Top-k results for retrieval |
| `-m` | Max tokens |
| `-t` | Temperature |
| `-V` | Verbose output |
| `--json` | JSON output |

## Configuration

```bash
# Set a config value
syft config set hub_url http://localhost:8080

# Show all config
syft config show

# Show config file path
syft config path
```

### Config Keys

| Key | Description |
|-----|-------------|
| `hub_url` | SyftHub server URL |
| `default_aggregator` | Default aggregator alias |
| `default_accounting` | Default accounting alias |
| `timeout` | Request timeout |

## Aliases (Aggregator and Accounting)

```bash
# Add an aggregator alias (-d to set as default)
syft add aggregator my-agg http://aggregator.example.com -d default

# Add an accounting alias
syft add accounting my-acct http://accounting.example.com

# List aliases
syft list aggregators
syft list accounting

# Update an alias
syft update aggregator my-agg http://new-url.example.com

# Remove an alias
syft remove aggregator my-agg
```

## Utilities

```bash
# Upgrade the CLI to the latest version
syft upgrade

# Generate shell completions
syft completion bash
syft completion zsh
syft completion fish
```
