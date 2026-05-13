#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)/syfthub-desktop"
BUILD_BIN="$APP_DIR/build/bin"

usage() {
    echo "Usage: $0 {build|run|clean}"
    echo ""
    echo "  build  - Install deps and build the desktop app for the current platform"
    echo "  run    - Run the built desktop app binary"
    echo "  clean  - Remove build artifacts, frontend dist, and node_modules"
    exit 1
}

cmd_build() {
    echo "Installing frontend dependencies..."
    cd "$APP_DIR/frontend" && npm install
    cd "$APP_DIR"
    # Ensure system pkg-config paths are visible (needed for X11/GTK .pc files)
    export PKG_CONFIG_PATH="${PKG_CONFIG_PATH:+$PKG_CONFIG_PATH:}/usr/share/pkgconfig:/usr/lib/x86_64-linux-gnu/pkgconfig"
    echo "Building for current platform..."
    wails build -tags webkit2_41
}

cmd_run() {
    local binary="$BUILD_BIN/syfthub-desktop"
    if [[ ! -x "$binary" ]]; then
        echo "Binary not found at $binary. Run '$0 build' first."
        exit 1
    fi
    echo "Running syfthub-desktop..."
    exec "$binary"
}

cmd_clean() {
    echo "Cleaning build artifacts..."
    rm -rf "$BUILD_BIN"/*
    rm -rf "$APP_DIR/frontend/dist"
    rm -rf "$APP_DIR/frontend/node_modules"
    rm -rf "$HOME/.config/syfthub"
    echo "Done."
}

if [[ $# -ne 1 ]]; then
    usage
fi

case "$1" in
    build) cmd_build ;;
    run)   cmd_run ;;
    clean) cmd_clean ;;
    *)     usage ;;
esac
