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

# Get the latest release version
get_latest_version() {
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL "https://api.github.com/repos/${REPO}/releases" | \
            grep -o '"tag_name": "cli/v[^"]*"' | \
            head -1 | \
            sed 's/.*"cli\/v\([^"]*\)".*/\1/'
    elif command -v wget >/dev/null 2>&1; then
        wget -qO- "https://api.github.com/repos/${REPO}/releases" | \
            grep -o '"tag_name": "cli/v[^"]*"' | \
            head -1 | \
            sed 's/.*"cli\/v\([^"]*\)".*/\1/'
    else
        error "curl or wget is required"
    fi
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

main() {
    info "Syft CLI Installer"

    # Detect platform
    OS=$(detect_os)
    ARCH=$(detect_arch)
    info "Detected platform: ${OS}-${ARCH}"

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

    # Create temp directory
    TMP_DIR=$(mktemp -d)
    trap 'rm -rf "$TMP_DIR"' EXIT

    # Download binary
    TMP_FILE="${TMP_DIR}/${BINARY_NAME}"
    download "$DOWNLOAD_URL" "$TMP_FILE"

    # Make executable
    chmod +x "$TMP_FILE"

    # Verify binary works
    info "Verifying binary..."
    if ! "$TMP_FILE" --version >/dev/null 2>&1; then
        error "Downloaded binary verification failed"
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
