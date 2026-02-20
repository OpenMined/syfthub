#!/bin/bash
# =============================================================================
# SyftHub Production Deployment Script
# =============================================================================
# This script is executed on the production VM via SSH from GitHub Actions.
# It handles pulling new images, running migrations, and deploying services
# with zero-downtime rolling restarts.
#
# Prerequisites:
#   - Docker and Docker Compose installed
#   - GHCR authentication completed (done in CI before calling this script)
#   - Environment variables: IMAGE_TAG, GITHUB_REPOSITORY
#   - .env file with production secrets
#
# Usage:
#   ./deploy.sh
#
# Environment:
#   IMAGE_TAG         - Docker image tag (git SHA short)
#   GITHUB_REPOSITORY - GitHub repository (org/repo)
# =============================================================================

set -euo pipefail

# =============================================================================
# Configuration
# =============================================================================

# Docker requires lowercase repository names
GITHUB_REPOSITORY=$(echo "${GITHUB_REPOSITORY:-}" | tr '[:upper:]' '[:lower:]')

DEPLOY_DIR="${DEPLOY_DIR:-/opt/syfthub}"
COMPOSE_FILE="docker-compose.deploy.yml"
LOG_DIR="/var/log/syfthub"
LOG_FILE="${LOG_DIR}/deploy-$(date +%Y%m%d-%H%M%S).log"
HEALTH_CHECK_RETRIES=30
HEALTH_CHECK_INTERVAL=2

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# =============================================================================
# Helper Functions
# =============================================================================

log() {
    local level=$1
    shift
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    case $level in
        INFO)  echo -e "${GREEN}[INFO]${NC} ${timestamp} - ${message}" ;;
        WARN)  echo -e "${YELLOW}[WARN]${NC} ${timestamp} - ${message}" ;;
        ERROR) echo -e "${RED}[ERROR]${NC} ${timestamp} - ${message}" ;;
    esac

    # Also log to file if log directory exists
    if [[ -d "$LOG_DIR" ]]; then
        echo "[${level}] ${timestamp} - ${message}" >> "$LOG_FILE"
    fi
}

die() {
    log ERROR "$1"
    exit 1
}

# =============================================================================
# Pre-flight Checks
# =============================================================================

check_prerequisites() {
    log INFO "Checking prerequisites..."

    # Check required commands
    for cmd in docker curl; do
        if ! command -v "$cmd" &> /dev/null; then
            die "Required command not found: $cmd"
        fi
    done

    # Check Docker Compose (v2)
    if ! docker compose version &> /dev/null; then
        die "Docker Compose v2 not found"
    fi

    # Check deployment directory
    if [[ ! -d "$DEPLOY_DIR" ]]; then
        die "Deployment directory not found: $DEPLOY_DIR"
    fi

    # Check compose file
    if [[ ! -f "${DEPLOY_DIR}/${COMPOSE_FILE}" ]]; then
        die "Compose file not found: ${DEPLOY_DIR}/${COMPOSE_FILE}"
    fi

    # Check .env file
    if [[ ! -f "${DEPLOY_DIR}/.env" ]]; then
        die "Environment file not found: ${DEPLOY_DIR}/.env"
    fi

    # Check required environment variables
    if [[ -z "${IMAGE_TAG:-}" ]]; then
        die "IMAGE_TAG environment variable is required"
    fi

    if [[ -z "${GITHUB_REPOSITORY:-}" ]]; then
        die "GITHUB_REPOSITORY environment variable is required"
    fi

    log INFO "Prerequisites check passed"
}

# =============================================================================
# Backup Current State
# =============================================================================

backup_current_state() {
    log INFO "Backing up current deployment state..."

    local backup_file="${DEPLOY_DIR}/.deploy-backup"

    # Save current image tags
    if docker compose -f "${DEPLOY_DIR}/${COMPOSE_FILE}" ps -q backend &> /dev/null; then
        local current_backend=$(docker inspect --format='{{.Config.Image}}' syfthub-backend 2>/dev/null || echo "none")
        local current_aggregator=$(docker inspect --format='{{.Config.Image}}' syfthub-aggregator 2>/dev/null || echo "none")
        local current_frontend=$(docker inspect --format='{{.Config.Image}}' syfthub-frontend-init 2>/dev/null || echo "none")
        local current_mcp=$(docker inspect --format='{{.Config.Image}}' syfthub-mcp 2>/dev/null || echo "none")

        cat > "$backup_file" << EOF
BACKUP_TIMESTAMP=$(date +%s)
BACKUP_BACKEND_IMAGE=${current_backend}
BACKUP_AGGREGATOR_IMAGE=${current_aggregator}
BACKUP_FRONTEND_IMAGE=${current_frontend}
BACKUP_MCP_IMAGE=${current_mcp}
EOF
        log INFO "Backup saved to $backup_file"
    else
        log WARN "No existing deployment found, skipping backup"
    fi
}

# =============================================================================
# Pull New Images
# =============================================================================

pull_images() {
    log INFO "Pulling new images with tag: ${IMAGE_TAG}..."

    cd "$DEPLOY_DIR"

    # Export variables for docker-compose
    export IMAGE_TAG
    export GITHUB_REPOSITORY

    # Source .env for other variables
    set -a
    source .env
    set +a

    # Ensure GITHUB_REPOSITORY is lowercase (Docker requirement)
    GITHUB_REPOSITORY=$(echo "${GITHUB_REPOSITORY}" | tr '[:upper:]' '[:lower:]')
    export GITHUB_REPOSITORY

    # Pull all images
    docker compose -f "$COMPOSE_FILE" pull backend aggregator mcp || die "Failed to pull backend/aggregator/mcp images"

    # Pull frontend image (for frontend-init)
    docker pull "ghcr.io/${GITHUB_REPOSITORY}-frontend:${IMAGE_TAG}" || die "Failed to pull frontend image"

    log INFO "Images pulled successfully"
}

# =============================================================================
# Update Frontend Static Files
# =============================================================================

update_frontend() {
    log INFO "Updating frontend static files..."

    cd "$DEPLOY_DIR"

    # Run frontend-init to copy static files to volume
    docker compose -f "$COMPOSE_FILE" up frontend-init --force-recreate || die "Failed to update frontend files"

    log INFO "Frontend files updated"
}

# =============================================================================
# Run Database Migrations
# =============================================================================

run_migrations() {
    log INFO "Running database migrations..."

    cd "$DEPLOY_DIR"

    # Ensure database is running and healthy
    docker compose -f "$COMPOSE_FILE" up -d db

    local retries=30
    while [ $retries -gt 0 ]; do
        if docker compose -f "$COMPOSE_FILE" exec -T db pg_isready -U syfthub -d syfthub &>/dev/null; then
            break
        fi
        log INFO "Waiting for database to be ready... ($retries retries left)"
        sleep 2
        retries=$((retries - 1))
    done

    if [ $retries -eq 0 ]; then
        die "Database failed to become ready"
    fi

    # Try to run migrations - handle case where Alembic isn't configured
    local migration_output
    if migration_output=$(docker compose -f "$COMPOSE_FILE" --profile migrate run --rm migrate 2>&1); then
        log INFO "Migrations completed successfully"
    else
        # Check if the error is because Alembic isn't configured
        if echo "$migration_output" | grep -q "No 'script_location' key found\|No such file or directory.*alembic"; then
            log WARN "Alembic not configured - skipping migrations"
            log INFO "Database schema will be created on application startup"
        else
            # Real migration error - fail the deployment
            echo "$migration_output"
            die "Database migration failed"
        fi
    fi
}

# =============================================================================
# Deploy Services (Rolling Restart)
# =============================================================================

deploy_services() {
    log INFO "Deploying services with rolling restart..."

    cd "$DEPLOY_DIR"

    # Ensure database, redis, and meilisearch are running
    log INFO "Ensuring database, redis, and meilisearch are running..."
    docker compose -f "$COMPOSE_FILE" up -d db redis meilisearch

    # Wait for database to be healthy
    log INFO "Waiting for database to be healthy..."
    local retries=0
    while ! docker compose -f "$COMPOSE_FILE" exec -T db pg_isready -U syfthub -d syfthub &> /dev/null; do
        retries=$((retries + 1))
        if [[ $retries -ge 30 ]]; then
            die "Database failed to become healthy"
        fi
        sleep 2
    done

    # Wait for meilisearch to be healthy
    log INFO "Waiting for meilisearch to be healthy..."
    retries=0
    while ! docker compose -f "$COMPOSE_FILE" exec -T meilisearch curl -sf http://localhost:7700/health &> /dev/null; do
        retries=$((retries + 1))
        if [[ $retries -ge 30 ]]; then
            die "Meilisearch failed to become healthy"
        fi
        sleep 2
    done
    log INFO "Meilisearch is healthy"

    # Rolling restart: Backend first
    log INFO "Restarting backend..."
    docker compose -f "$COMPOSE_FILE" up -d --no-deps --force-recreate backend
    sleep 5

    # Wait for backend to be healthy
    log INFO "Waiting for backend to be healthy..."
    retries=0
    while ! docker compose -f "$COMPOSE_FILE" exec -T backend curl -sf http://localhost:8000/health &> /dev/null; do
        retries=$((retries + 1))
        if [[ $retries -ge $HEALTH_CHECK_RETRIES ]]; then
            die "Backend failed health check after restart"
        fi
        sleep $HEALTH_CHECK_INTERVAL
    done
    log INFO "Backend is healthy"

    # Rolling restart: Aggregator
    log INFO "Restarting aggregator..."
    docker compose -f "$COMPOSE_FILE" up -d --no-deps --force-recreate aggregator
    sleep 5

    # Wait for aggregator to be healthy (use Python since curl not installed in aggregator container)
    log INFO "Waiting for aggregator to be healthy..."
    retries=0
    while ! docker compose -f "$COMPOSE_FILE" exec -T aggregator python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/health', timeout=5)" &> /dev/null; do
        retries=$((retries + 1))
        if [[ $retries -ge $HEALTH_CHECK_RETRIES ]]; then
            die "Aggregator failed health check after restart"
        fi
        sleep $HEALTH_CHECK_INTERVAL
    done
    log INFO "Aggregator is healthy"

    # Rolling restart: MCP Server
    log INFO "Restarting MCP server..."
    docker compose -f "$COMPOSE_FILE" up -d --no-deps --force-recreate mcp
    sleep 5

    # Wait for MCP to be healthy
    log INFO "Waiting for MCP server to be healthy..."
    retries=0
    while ! docker compose -f "$COMPOSE_FILE" exec -T mcp curl -sf http://localhost:8002/health &> /dev/null; do
        retries=$((retries + 1))
        if [[ $retries -ge $HEALTH_CHECK_RETRIES ]]; then
            die "MCP server failed health check after restart"
        fi
        sleep $HEALTH_CHECK_INTERVAL
    done
    log INFO "MCP server is healthy"

    # Restart proxy (to pick up any nginx config changes)
    log INFO "Restarting proxy..."
    docker compose -f "$COMPOSE_FILE" up -d --no-deps --force-recreate proxy
    sleep 3

    # Clean up orphaned containers
    docker compose -f "$COMPOSE_FILE" up -d --remove-orphans

    log INFO "All services deployed"
}

# =============================================================================
# Health Check
# =============================================================================

health_check() {
    log INFO "Running final health checks..."

    local retries=0

    # Check main health endpoint
    while ! curl -sf http://localhost/health > /dev/null; do
        retries=$((retries + 1))
        if [[ $retries -ge $HEALTH_CHECK_RETRIES ]]; then
            die "Final health check failed - deployment may be broken"
        fi
        log WARN "Health check attempt $retries failed, retrying..."
        sleep $HEALTH_CHECK_INTERVAL
    done

    log INFO "Health check passed"

    # Show service status
    log INFO "Current service status:"
    docker compose -f "${DEPLOY_DIR}/${COMPOSE_FILE}" ps
}

# =============================================================================
# Cleanup
# =============================================================================

cleanup() {
    log INFO "Cleaning up old images..."

    # Remove dangling images
    docker image prune -f

    # Remove old images (keep last 3 versions)
    for image in backend frontend aggregator mcp; do
        local full_image="ghcr.io/${GITHUB_REPOSITORY}-${image}"
        local image_ids=$(docker images "$full_image" --format "{{.ID}}" | tail -n +4)
        if [[ -n "$image_ids" ]]; then
            echo "$image_ids" | xargs -r docker rmi -f 2>/dev/null || true
        fi
    done

    log INFO "Cleanup completed"
}

# =============================================================================
# Rollback (called on failure)
# =============================================================================

rollback() {
    log ERROR "Deployment failed, attempting rollback..."

    local backup_file="${DEPLOY_DIR}/.deploy-backup"

    if [[ ! -f "$backup_file" ]]; then
        log ERROR "No backup file found, cannot rollback"
        return 1
    fi

    source "$backup_file"

    if [[ "${BACKUP_BACKEND_IMAGE:-}" == "none" ]]; then
        log ERROR "No previous deployment to rollback to"
        return 1
    fi

    log INFO "Rolling back to previous images..."

    cd "$DEPLOY_DIR"

    # Restart with previous images
    # This is a simplified rollback - in production you might want more sophisticated handling
    docker compose -f "$COMPOSE_FILE" up -d --force-recreate

    log INFO "Rollback completed"
}

# =============================================================================
# Main
# =============================================================================

main() {
    log INFO "=========================================="
    log INFO "SyftHub Deployment Starting"
    log INFO "Image Tag: ${IMAGE_TAG:-not set}"
    log INFO "Repository: ${GITHUB_REPOSITORY:-not set}"
    log INFO "=========================================="

    # Create log directory if needed
    mkdir -p "$LOG_DIR" 2>/dev/null || true

    # Set trap for rollback on failure
    trap 'rollback' ERR

    # Run deployment steps
    check_prerequisites
    backup_current_state
    pull_images
    update_frontend
    run_migrations
    deploy_services
    health_check
    cleanup

    # Remove trap on success
    trap - ERR

    log INFO "=========================================="
    log INFO "Deployment completed successfully!"
    log INFO "Image Tag: ${IMAGE_TAG}"
    log INFO "=========================================="
}

# Run main function
main "$@"
