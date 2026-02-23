# SyftHub Go SDK Makefile

.PHONY: all build clean run-http run-file-based run-file-based-http run-tunnel test lint deps help \
        nats-docker nats-stop nats-logs nats-status list-endpoints \
        curl-health curl-model curl-datasource curl-echo

# Go parameters
GOCMD=go
GOBUILD=$(GOCMD) build
GORUN=$(GOCMD) run
GOTEST=$(GOCMD) test
GOMOD=$(GOCMD) mod
GOFMT=$(GOCMD) fmt

# Directories
SDK_DIR=./syfthub
API_DIR=./syfthubapi
EXAMPLES_DIR=./examples

# Binary names
HTTP_SERVER_BIN=http_server
FILE_BASED_BIN=file_based
NATS_TUNNEL_BIN=nats_tunnel

# Default environment variables for local testing
export SYFTHUB_URL ?= http://localhost:8080
export SYFTHUB_API_KEY ?= test-api-key
export SPACE_URL ?= tunneling:testuser
export LOG_LEVEL ?= DEBUG
export SERVER_PORT ?= 8001
export ENDPOINTS_PATH ?= $(CURDIR)/examples/file_based/endpoints
export NATS_URL ?= nats://localhost:4222
export NATS_TOKEN ?= test-token

# Colors for output
GREEN=\033[0;32m
YELLOW=\033[0;33m
NC=\033[0m # No Color

all: deps build

## deps: Download and tidy dependencies
deps:
	@echo "$(GREEN)Downloading dependencies...$(NC)"
	$(GOMOD) download
	$(GOMOD) tidy

## build: Build all examples
build: build-http build-file-based build-tunnel
	@echo "$(GREEN)All examples built successfully$(NC)"

## build-http: Build the HTTP server example
build-http:
	@echo "$(GREEN)Building HTTP server example...$(NC)"
	$(GOBUILD) -o bin/$(HTTP_SERVER_BIN) $(EXAMPLES_DIR)/http_server/main.go

## build-file-based: Build the file-based example
build-file-based:
	@echo "$(GREEN)Building file-based example...$(NC)"
	$(GOBUILD) -o bin/$(FILE_BASED_BIN) $(EXAMPLES_DIR)/file_based/main.go

## build-tunnel: Build the NATS tunnel example
build-tunnel:
	@echo "$(GREEN)Building NATS tunnel example...$(NC)"
	$(GOBUILD) -o bin/$(NATS_TUNNEL_BIN) $(EXAMPLES_DIR)/nats_tunnel/main.go

## run-http: Run the HTTP server example
run-http:
	@echo "$(GREEN)Running HTTP server example...$(NC)"
	@echo "$(YELLOW)Environment:$(NC)"
	@echo "  SYFTHUB_URL=$(SYFTHUB_URL)"
	@echo "  SPACE_URL=$(SPACE_URL)"
	@echo "  SERVER_PORT=$(SERVER_PORT)"
	@echo ""
	$(GORUN) $(EXAMPLES_DIR)/http_server/main.go

## run-file-based: Run the file-based endpoint example (NATS tunnel mode)
run-file-based:
	@echo "$(GREEN)Running file-based endpoint example (NATS tunnel mode)...$(NC)"
	@echo "$(YELLOW)Environment:$(NC)"
	@echo "  SYFTHUB_URL=$(SYFTHUB_URL)"
	@echo "  SPACE_URL=$(SPACE_URL)"
	@echo "  NATS_URL=$(NATS_URL)"
	@echo "  ENDPOINTS_PATH=$(ENDPOINTS_PATH)"
	@echo ""
	@echo "$(YELLOW)Note: Make sure NATS is running (use 'make nats-start' or 'make nats-docker')$(NC)"
	@echo ""
	$(GORUN) $(EXAMPLES_DIR)/file_based/main.go

## run-file-based-http: Run the file-based example in HTTP mode (fallback)
run-file-based-http:
	@echo "$(GREEN)Running file-based endpoint example (HTTP mode)...$(NC)"
	SPACE_URL=http://localhost:$(SERVER_PORT) $(GORUN) $(EXAMPLES_DIR)/file_based/main.go

## run-tunnel: Run the NATS tunnel example
run-tunnel:
	@echo "$(GREEN)Running NATS tunnel example...$(NC)"
	@echo "$(YELLOW)Note: Set SPACE_URL=tunneling:username for tunnel mode$(NC)"
	SPACE_URL=tunneling:testuser $(GORUN) $(EXAMPLES_DIR)/nats_tunnel/main.go

## test: Run all tests
test:
	@echo "$(GREEN)Running tests...$(NC)"
	$(GOTEST) -v ./...

## test-coverage: Run tests with coverage
test-coverage:
	@echo "$(GREEN)Running tests with coverage...$(NC)"
	$(GOTEST) -v -coverprofile=coverage.out ./...
	$(GOCMD) tool cover -html=coverage.out -o coverage.html
	@echo "Coverage report: coverage.html"

## lint: Run linters
lint:
	@echo "$(GREEN)Running linters...$(NC)"
	$(GOFMT) ./...
	$(GOCMD) vet ./...

## clean: Clean build artifacts
clean:
	@echo "$(GREEN)Cleaning...$(NC)"
	rm -rf bin/
	rm -f coverage.out coverage.html

## check: Verify the build compiles
check:
	@echo "$(GREEN)Checking build...$(NC)"
	$(GOBUILD) ./...

## curl-health: Test health endpoint (requires running server)
curl-health:
	@echo "$(GREEN)Testing health endpoint...$(NC)"
	curl -s http://localhost:$(SERVER_PORT)/health | jq .

## curl-model: Test model endpoint (requires running server)
curl-model:
	@echo "$(GREEN)Testing model endpoint...$(NC)"
	curl -s -X POST http://localhost:$(SERVER_PORT)/api/v1/endpoints/sample-model/query \
		-H "Content-Type: application/json" \
		-H "Authorization: Bearer test-token" \
		-d '{"messages": [{"role": "user", "content": "Hello, how are you?"}]}' | jq .

## curl-datasource: Test data source endpoint (requires running server)
curl-datasource:
	@echo "$(GREEN)Testing simple-search data source endpoint...$(NC)"
	curl -s -X POST http://localhost:$(SERVER_PORT)/api/v1/endpoints/simple-search/query \
		-H "Content-Type: application/json" \
		-H "Authorization: Bearer test-token" \
		-d '{"messages": [{"role": "user", "content": "machine learning"}]}' | jq .

## curl-echo: Test echo-model endpoint (requires running server)
curl-echo:
	@echo "$(GREEN)Testing echo-model endpoint...$(NC)"
	curl -s -X POST http://localhost:$(SERVER_PORT)/api/v1/endpoints/echo-model/query \
		-H "Content-Type: application/json" \
		-H "Authorization: Bearer test-token" \
		-d '{"messages": [{"role": "user", "content": "Hello from the test!"}]}' | jq .

## list-endpoints: List available file-based endpoints
list-endpoints:
	@echo "$(GREEN)Available endpoints in $(ENDPOINTS_PATH):$(NC)"
	@for dir in $(ENDPOINTS_PATH)/*/; do \
		if [ -f "$$dir/README.md" ]; then \
			name=$$(basename $$dir); \
			echo "  - $$name"; \
		fi; \
	done

## nats-docker: Start NATS server using Docker
nats-docker:
	@echo "$(GREEN)Starting NATS server with Docker...$(NC)"
	docker run -d --name syfthub-nats \
		-p 4222:4222 \
		-p 8222:8222 \
		nats:latest \
		--auth $(NATS_TOKEN)
	@echo "NATS server started at nats://localhost:4222"
	@echo "Monitoring at http://localhost:8222"

## nats-stop: Stop NATS Docker container
nats-stop:
	@echo "$(GREEN)Stopping NATS server...$(NC)"
	docker stop syfthub-nats || true
	docker rm syfthub-nats || true

## nats-logs: Show NATS server logs
nats-logs:
	docker logs -f syfthub-nats

## nats-status: Check NATS server status
nats-status:
	@echo "$(GREEN)Checking NATS server status...$(NC)"
	@curl -s http://localhost:8222/varz 2>/dev/null | jq '.server_id, .now, .connections' || echo "$(YELLOW)NATS server not running or monitoring not available$(NC)"

## help: Show this help message
help:
	@echo "$(GREEN)SyftHub Go SDK - Available targets:$(NC)"
	@echo ""
	@grep -E '^##' $(MAKEFILE_LIST) | sed -e 's/## //' | column -t -s ':'
	@echo ""
	@echo "$(YELLOW)Environment variables:$(NC)"
	@echo "  SYFTHUB_URL      - SyftHub backend URL (default: http://localhost:8080)"
	@echo "  SYFTHUB_API_KEY  - API key for authentication (default: test-api-key)"
	@echo "  SPACE_URL        - Space URL or tunneling:username (default: http://localhost:8001)"
	@echo "  LOG_LEVEL        - Log level: DEBUG, INFO, WARNING, ERROR (default: DEBUG)"
	@echo "  SERVER_PORT      - HTTP server port (default: 8001)"
	@echo "  ENDPOINTS_PATH   - Path to file-based endpoints (default: ./examples/file_based/endpoints)"
	@echo ""
	@echo "$(YELLOW)Quick start:$(NC)"
	@echo "  make deps              # Download dependencies"
	@echo "  make run-file-based    # Run the file-based example"
	@echo "  make curl-model        # Test the sample-model endpoint (in another terminal)"
