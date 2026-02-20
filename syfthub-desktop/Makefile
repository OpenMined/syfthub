# SyftHub Desktop GUI Makefile
# Build targets for Wails application

.PHONY: all dev build build-linux build-windows build-windows-debug build-darwin clean deps install-deps

# Default target
all: build

# Install Linux dependencies (requires sudo)
install-deps:
	@echo "Installing Linux dependencies..."
	sudo apt install -y libgtk-3-dev libwebkit2gtk-4.1-dev

# Install Node.js dependencies
deps:
	@echo "Installing frontend dependencies..."
	cd frontend && npm install

# Development mode with hot reload
dev: deps
	@echo "Starting development server..."
	wails dev -tags webkit2_41

# Build for current platform
build: deps
	@echo "Building for current platform..."
	wails build -tags webkit2_41

# Build for Linux (Ubuntu 24.04+)
build-linux: deps
	@echo "Building for Linux..."
	wails build -platform linux/amd64 -tags webkit2_41

# Build for Windows (cross-compile from Linux)
build-windows: deps
	@echo "Building for Windows..."
	wails build -platform windows/amd64

# Build for Windows with debug/devtools enabled
build-windows-debug: deps
	@echo "Building for Windows (debug mode with devtools)..."
	wails build -platform windows/amd64 -debug

# Build for macOS (cross-compile, requires xgo or macOS)
build-darwin: deps
	@echo "Building for macOS..."
	wails build -platform darwin/universal

# Generate Wails bindings
generate:
	@echo "Generating Wails bindings..."
	wails generate module

# Clean build artifacts
clean:
	@echo "Cleaning build artifacts..."
	rm -rf build/bin/*
	rm -rf frontend/dist
	rm -rf frontend/node_modules

# Run wails doctor to check system dependencies
doctor:
	wails doctor

# Copy runtime files to build directory
setup-runtime:
	@echo "Setting up runtime files..."
	mkdir -p build/bin/endpoints
	cp -r ../syfthub-desktop-v2/sample-endpoints/* build/bin/endpoints/ 2>/dev/null || true
	cp build/bin/.env.example build/bin/.env 2>/dev/null || true

# Help
help:
	@echo "SyftHub Desktop GUI - Build Targets"
	@echo ""
	@echo "  make install-deps  - Install Linux dependencies (requires sudo)"
	@echo "  make deps          - Install frontend dependencies"
	@echo "  make dev           - Run in development mode with hot reload"
	@echo "  make build         - Build for current platform"
	@echo "  make build-linux   - Build Linux executable"
	@echo "  make build-windows - Build Windows executable"
	@echo "  make build-darwin  - Build macOS executable"
	@echo "  make generate      - Regenerate Wails bindings"
	@echo "  make clean         - Clean build artifacts"
	@echo "  make doctor        - Run Wails doctor"
	@echo ""
	@echo "Note: Linux builds on Ubuntu 24.04+ require webkit2gtk-4.1 tag"
