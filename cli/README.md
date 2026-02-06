# SyftHub CLI

A Unix-style command-line interface for interacting with the SyftHub platform.

## Installation

### Quick Install (Recommended)

Install with a single command (auto-detects your OS and architecture):

```bash
curl -fsSL https://raw.githubusercontent.com/OpenMined/syfthub/main/cli/install.sh | sh
```

Or with wget:

```bash
wget -qO- https://raw.githubusercontent.com/OpenMined/syfthub/main/cli/install.sh | sh
```

**Options:**
- Install a specific version: `SYFT_VERSION=0.1.0 curl -fsSL ... | sh`
- Custom install directory: `SYFT_INSTALL_DIR=~/bin curl -fsSL ... | sh`

### Manual Download

Download the pre-built binary for your platform from the [releases page](https://github.com/OpenMined/syfthub/releases):

**Linux (x64):**
```bash
curl -L -o syft https://github.com/OpenMined/syfthub/releases/latest/download/syft-linux-x64
chmod +x syft
sudo mv syft /usr/local/bin/
```

**macOS (Apple Silicon):**
```bash
curl -L -o syft https://github.com/OpenMined/syfthub/releases/latest/download/syft-darwin-arm64
chmod +x syft
sudo mv syft /usr/local/bin/
```

**macOS (Intel):**
```bash
curl -L -o syft https://github.com/OpenMined/syfthub/releases/latest/download/syft-darwin-x64
chmod +x syft
sudo mv syft /usr/local/bin/
```

**Windows (x64):**
```powershell
Invoke-WebRequest -Uri "https://github.com/OpenMined/syfthub/releases/latest/download/syft-windows-x64.exe" -OutFile "syft.exe"
# Add to PATH or move to a directory in your PATH
```

### From Source (Python Required)

```bash
# From the cli directory
uv sync
uv pip install -e .

# Or using pip
pip install -e .
```

## Quick Start

```bash
# Authenticate
syft login

# Browse users and endpoints
syft ls                      # List all users
syft ls alice                # List alice's endpoints
syft ls alice/my-model       # Show endpoint details

# Query with RAG
syft query alice/gpt4 "What is machine learning?"
syft query alice/gpt4 --source bob/docs "Explain the API"

# Manage aggregators
syft add aggregator local http://localhost:8001 --default
syft list aggregator

# Configuration
syft config show
syft config set timeout 60
```

## Commands

### Authentication

```bash
syft login                   # Interactive login
syft login -u user -p pass   # Non-interactive login
syft logout                  # Clear credentials
syft whoami                  # Show current user
```

### Discovery

```bash
syft ls                      # List all active users
syft ls <username>           # List user's endpoints
syft ls <user>/<endpoint>    # Show endpoint details/README
```

### Query

```bash
syft query <model> "<prompt>"
syft query <model> --source <datasource> "<prompt>"
syft query <model> -s <ds1> -s <ds2> "<prompt>"

# Options
--top-k, -k       Number of documents to retrieve (default: 5)
--max-tokens, -m  Maximum response tokens (default: 1024)
--temperature, -t Sampling temperature (default: 0.7)
--verbose, -V     Show retrieval progress
--aggregator, -a  Use specific aggregator
--json            Output as JSON (non-streaming)
```

### Infrastructure Management

```bash
# Aggregators
syft add aggregator <alias> <url> [--default]
syft list aggregator
syft update aggregator <alias> --url <new-url>
syft remove aggregator <alias>

# Accounting services
syft add accounting <alias> <url> [--default]
syft list accounting
syft update accounting <alias> --url <new-url>
syft remove accounting <alias>
```

### Configuration

```bash
syft config show             # Display all settings
syft config set <key> <val>  # Set a configuration value
syft config path             # Show config file location

# Available keys:
#   default_aggregator  - Default aggregator alias
#   default_accounting  - Default accounting alias
#   timeout            - Request timeout (seconds)
#   hub_url            - SyftHub API URL
```

### Upgrading

The CLI automatically checks for updates once per day and notifies you when a new version is available.

```bash
syft upgrade                 # Check and install updates
syft upgrade --check         # Only check, don't install
syft upgrade -y              # Update without confirmation
```

**Disable update notifications:**
```bash
# Via environment variable
export SYFT_NO_UPDATE_CHECK=1

# Via command flag (single invocation)
syft --no-update-check <command>
```

## Configuration File

Configuration is stored in `~/.syfthub/config.json`:

```json
{
  "access_token": null,
  "refresh_token": null,
  "aggregators": {
    "local": {"url": "http://localhost:8001"}
  },
  "accounting_services": {},
  "default_aggregator": "local",
  "default_accounting": null,
  "timeout": 30.0,
  "hub_url": "https://hub.syftbox.org"
}
```

### Shell Completion

```bash
# Generate completion script for your shell
syft completion bash         # Bash completion script
syft completion zsh          # Zsh completion script
syft completion fish         # Fish completion script

# Show installation instructions
syft completion install      # Auto-detect shell
syft completion install bash # Specific shell
```

**Installation examples:**

```bash
# Bash - add to ~/.bashrc
eval "$(syft completion bash)"

# Zsh - add to ~/.zshrc
eval "$(syft completion zsh)"

# Fish - save to completions
syft completion fish > ~/.config/fish/completions/syft.fish
```

## JSON Output

All commands support `--json` for machine-readable output:

```bash
syft ls --json
syft query alice/gpt4 "Hello" --json
syft config show --json
```

## Development

```bash
# Install dev dependencies
uv sync --all-extras

# Run tests
pytest

# Type checking
mypy src/

# Linting
ruff check src/
ruff format src/
```

## Building Standalone Binaries

The CLI can be compiled into standalone executables that don't require Python:

```bash
# Install build dependencies
uv sync --extra build

# Build for current platform
uv run python scripts/build.py

# Build with checksum generation
uv run python scripts/build.py --checksum

# Output will be in dist/ (e.g., dist/syft-linux-x64)
```

Alternatively, run PyInstaller directly:

```bash
uv run pyinstaller syft.spec
# Output: dist/syft (or dist/syft.exe on Windows)
```

Expected binary sizes:
- Linux x64: ~80-120 MB
- macOS: ~90-130 MB
- Windows: ~100-140 MB

## License

Apache-2.0
