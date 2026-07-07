#!/bin/sh
# Syft CLI Installer
# Usage: curl -fsSL https://raw.githubusercontent.com/OpenMined/syfthub/main/cli/install.sh | sh
#
# Environment variables:
#   SYFT_INSTALL_DIR - Installation directory (default: /usr/local/bin or ~/.local/bin)
#   SYFT_VERSION     - Specific version to install (default: latest)

set -e

# Colors for output (disabled if not a terminal)
if [ -t 1 ]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[0;33m'
    BLUE='\033[0;34m'
    NC='\033[0m' # No Color
else
    RED=''
    GREEN=''
    YELLOW=''
    BLUE=''
    NC=''
fi

REPO="OpenMined/syfthub"
BINARY_NAME="syft"

info() {
    printf "${BLUE}==>${NC} %s\n" "$1"
}

success() {
    printf "${GREEN}==>${NC} %s\n" "$1"
}

warn() {
    printf "${YELLOW}Warning:${NC} %s\n" "$1"
}

error() {
    printf "${RED}Error:${NC} %s\n" "$1" >&2
    exit 1
}

# Detect OS
detect_os() {
    case "$(uname -s)" in
        Linux*)  echo "linux" ;;
        Darwin*) echo "darwin" ;;
        CYGWIN*|MINGW*|MSYS*) echo "windows" ;;
        *) error "Unsupported operating system: $(uname -s)" ;;
    esac
}

# Detect architecture
detect_arch() {
    case "$(uname -m)" in
        x86_64|amd64) echo "x64" ;;
        aarch64|arm64) echo "arm64" ;;
        *) error "Unsupported architecture: $(uname -m)" ;;
    esac
}

# Get the latest stable release version (skips pre-releases like alpha/beta/rc)
get_latest_version() {
    local releases_json
    if command -v curl >/dev/null 2>&1; then
        releases_json=$(curl -fsSL "https://api.github.com/repos/${REPO}/releases")
    elif command -v wget >/dev/null 2>&1; then
        releases_json=$(wget -qO- "https://api.github.com/repos/${REPO}/releases")
    else
        error "curl or wget is required"
    fi

    # Extract all cli/v* tags, exclude pre-release suffixes, take the first
    echo "$releases_json" | \
        grep -o '"tag_name": "cli/v[^"]*"' | \
        grep -v '\-alpha\|\-beta\|\-rc' | \
        head -1 | \
        sed 's/.*"cli\/v\([^"]*\)".*/\1/'
}

# Download file
download() {
    url="$1"
    output="$2"

    info "Downloading from ${url}"

    if command -v curl >/dev/null 2>&1; then
        curl -fsSL -o "$output" "$url"
    elif command -v wget >/dev/null 2>&1; then
        wget -q -O "$output" "$url"
    else
        error "curl or wget is required"
    fi
}

# Determine install directory
get_install_dir() {
    if [ -n "$SYFT_INSTALL_DIR" ]; then
        echo "$SYFT_INSTALL_DIR"
    elif [ -w "/usr/local/bin" ]; then
        echo "/usr/local/bin"
    else
        # Fall back to user's local bin
        mkdir -p "$HOME/.local/bin"
        echo "$HOME/.local/bin"
    fi
}

# Check if directory is in PATH
check_path() {
    dir="$1"
    case ":$PATH:" in
        *":$dir:"*) return 0 ;;
        *) return 1 ;;
    esac
}

# Build binary from local source tree
# All status output goes to stderr so the return value (path) can be captured cleanly
build_local() {
    # Locate cli/ directory — works from repo root or from within cli/
    if [ -f "go.mod" ] && grep -q "module github.com/OpenMined/syfthub/cli" go.mod 2>/dev/null; then
        CLI_DIR="."
    elif [ -f "cli/go.mod" ] && grep -q "module github.com/OpenMined/syfthub/cli" cli/go.mod 2>/dev/null; then
        CLI_DIR="cli"
    else
        error "Cannot find CLI source. Run from the repo root or the cli/ directory."
    fi

    if ! command -v go >/dev/null 2>&1; then
        error "Go is required to build from source. Install from https://golang.org/dl/"
    fi

    info "Building from source in ${CLI_DIR}/ ($(go version))..." >&2
    mkdir -p "${CLI_DIR}/build"
    ( cd "$CLI_DIR" && go build -o "build/${BINARY_NAME}" ./cmd/syft/ ) || error "Build failed"

    echo "${CLI_DIR}/build/${BINARY_NAME}"
}

main() {
    info "Syft CLI Installer"

    # Detect platform
    OS=$(detect_os)
    ARCH=$(detect_arch)
    info "Detected platform: ${OS}-${ARCH}"

    # Create temp directory
    TMP_DIR=$(mktemp -d)
    trap 'rm -rf "$TMP_DIR"' EXIT
    TMP_FILE="${TMP_DIR}/${BINARY_NAME}"

    if [ "${1}" = "local" ]; then
        # Build from local source instead of downloading a release
        info "Mode: local build"
        LOCAL_BINARY=$(build_local)
        cp "$LOCAL_BINARY" "$TMP_FILE"
        chmod +x "$TMP_FILE"
        VERSION=$("$TMP_FILE" --version 2>/dev/null | sed 's/^[^0-9]*//' | head -1)
        [ -z "$VERSION" ] && VERSION="local"
        info "Built version: ${VERSION}"
    else
        # Get version
        if [ -n "$SYFT_VERSION" ]; then
            VERSION="$SYFT_VERSION"
        else
            info "Fetching latest version..."
            VERSION=$(get_latest_version)
            if [ -z "$VERSION" ]; then
                error "Could not determine latest version. Set SYFT_VERSION manually or check https://github.com/${REPO}/releases"
            fi
        fi
        info "Installing version: ${VERSION}"

        # Construct download URL
        if [ "$OS" = "windows" ]; then
            FILENAME="${BINARY_NAME}-${OS}-${ARCH}.exe"
        else
            FILENAME="${BINARY_NAME}-${OS}-${ARCH}"
        fi

        DOWNLOAD_URL="https://github.com/${REPO}/releases/download/cli/v${VERSION}/${FILENAME}"

        # Download binary
        download "$DOWNLOAD_URL" "$TMP_FILE"
        chmod +x "$TMP_FILE"
    fi

    # Verify binary works
    info "Verifying binary..."
    if ! "$TMP_FILE" --version >/dev/null 2>&1; then
        error "Binary verification failed"
    fi

    # Get install directory
    INSTALL_DIR=$(get_install_dir)
    INSTALL_PATH="${INSTALL_DIR}/${BINARY_NAME}"

    # Install
    info "Installing to ${INSTALL_PATH}"
    if [ -w "$INSTALL_DIR" ]; then
        mv "$TMP_FILE" "$INSTALL_PATH"
    else
        info "Requesting sudo access to install to ${INSTALL_DIR}"
        sudo mv "$TMP_FILE" "$INSTALL_PATH"
    fi

    # Verify installation
    if [ -x "$INSTALL_PATH" ]; then
        success "Syft CLI v${VERSION} installed successfully!"
        echo ""
        "$INSTALL_PATH" --version
        echo ""

        # Check if install dir is in PATH
        if ! check_path "$INSTALL_DIR"; then
            warn "${INSTALL_DIR} is not in your PATH"
            echo ""
            echo "Add it to your PATH by running:"
            echo ""
            echo "  export PATH=\"${INSTALL_DIR}:\$PATH\""
            echo ""
            echo "Or add this line to your ~/.bashrc or ~/.zshrc"
        else
            echo "Run 'syft --help' to get started"
        fi
    else
        error "Installation failed"
    fi
}

main "$@"
