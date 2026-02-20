# SyftHub CLI Makefile

# Version from git tag or default
VERSION ?= $(shell git describe --tags --always --dirty 2>/dev/null || echo "dev")
LDFLAGS := -ldflags "-X github.com/OpenMined/syfthub/cli-go/internal/version.Version=$(VERSION)"

# Binary name
BINARY := syft

# Build directories
BUILD_DIR := build
DIST_DIR := dist

# Go parameters
GOCMD := go
GOBUILD := $(GOCMD) build
GOTEST := $(GOCMD) test
GOMOD := $(GOCMD) mod
GOVET := $(GOCMD) vet

# Platforms for cross-compilation
PLATFORMS := linux/amd64 linux/arm64 darwin/arm64 windows/amd64

.PHONY: all build clean test lint install deps help

# Default target
all: build

# Build for current platform
build:
	@echo "Building $(BINARY) version $(VERSION)..."
	$(GOBUILD) $(LDFLAGS) -o $(BUILD_DIR)/$(BINARY) ./cmd/syft

# Build for all platforms
build-all: clean
	@echo "Building for all platforms..."
	@mkdir -p $(DIST_DIR)
	@for platform in $(PLATFORMS); do \
		GOOS=$${platform%/*} GOARCH=$${platform#*/} \
		$(GOBUILD) $(LDFLAGS) -o $(DIST_DIR)/$(BINARY)-$${platform%/*}-$${platform#*/}$$(if [ "$${platform%/*}" = "windows" ]; then echo ".exe"; fi) ./cmd/syft; \
		echo "Built: $(BINARY)-$${platform%/*}-$${platform#*/}"; \
	done

# Clean build artifacts
clean:
	@echo "Cleaning..."
	@rm -rf $(BUILD_DIR) $(DIST_DIR)

# Run tests
test:
	@echo "Running tests..."
	$(GOTEST) -v ./...

# Run tests with race detection
test-race:
	@echo "Running tests with race detection..."
	$(GOTEST) -race -v ./...

# Run linter
lint:
	@echo "Running linter..."
	@if command -v golangci-lint >/dev/null 2>&1; then \
		golangci-lint run ./...; \
	else \
		echo "golangci-lint not installed. Running go vet instead."; \
		$(GOVET) ./...; \
	fi

# Install to GOPATH/bin
install:
	@echo "Installing $(BINARY)..."
	$(GOBUILD) $(LDFLAGS) -o $(GOPATH)/bin/$(BINARY) ./cmd/syft

# Install to /usr/local/bin (requires sudo)
install-system:
	@echo "Installing $(BINARY) to /usr/local/bin..."
	$(GOBUILD) $(LDFLAGS) -o /usr/local/bin/$(BINARY) ./cmd/syft

# Download dependencies
deps:
	@echo "Downloading dependencies..."
	$(GOMOD) download
	$(GOMOD) tidy

# Update dependencies
deps-update:
	@echo "Updating dependencies..."
	$(GOMOD) get -u ./...
	$(GOMOD) tidy

# Run the CLI
run:
	$(GOCMD) run ./cmd/syft $(ARGS)

# Generate shell completions
completions:
	@mkdir -p $(BUILD_DIR)/completions
	$(GOCMD) run ./cmd/syft completion bash > $(BUILD_DIR)/completions/syft.bash
	$(GOCMD) run ./cmd/syft completion zsh > $(BUILD_DIR)/completions/_syft
	$(GOCMD) run ./cmd/syft completion fish > $(BUILD_DIR)/completions/syft.fish
	@echo "Completions generated in $(BUILD_DIR)/completions/"

# Show version
version:
	@echo $(VERSION)

# Help
help:
	@echo "SyftHub CLI Makefile"
	@echo ""
	@echo "Targets:"
	@echo "  build         Build for current platform"
	@echo "  build-all     Build for all platforms (linux/darwin/windows)"
	@echo "  clean         Remove build artifacts"
	@echo "  test          Run tests"
	@echo "  test-race     Run tests with race detection"
	@echo "  lint          Run linter (golangci-lint or go vet)"
	@echo "  install       Install to GOPATH/bin"
	@echo "  install-system Install to /usr/local/bin (requires sudo)"
	@echo "  deps          Download dependencies"
	@echo "  deps-update   Update dependencies"
	@echo "  run           Run the CLI (use ARGS='...' to pass arguments)"
	@echo "  completions   Generate shell completion scripts"
	@echo "  version       Show version"
	@echo "  help          Show this help"
