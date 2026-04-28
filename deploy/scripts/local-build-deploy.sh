#!/bin/bash
# =============================================================================
# SyftHub Local Build & Deploy Script
# =============================================================================
# Emergency deployment script that builds Docker images directly on the VM,
# bypassing GHCR pulls. Use when GitHub Container Registry egress limits
# prevent the normal CI/CD pipeline from pulling pre-built images.
#
# This script replicates the CI pipeline's build + deploy flow:
#   1. Clones/updates the repository from GitHub
#   2. Builds all 4 Docker images locally (backend, frontend, aggregator, mcp)
#   3. Tags them identically to the CI pipeline (ghcr.io/openmined/syfthub-*)
#   4. Syncs config files to the deploy directory
#   5. Runs deploy.sh (with pulls disabled since images are already local)
#
# The images are tagged to be fully compatible with docker-compose.deploy.yml
# and future CI-triggered deployments. No manual retagging needed.
#
# Prerequisites:
#   - Docker and Docker Buildx installed
#   - Git installed
#   - /opt/syfthub/.env with production secrets
#   - Network access to github.com (for git clone only, NOT for GHCR)
#
# Usage:
#   ./local-build-deploy.sh                  # Build + deploy from main
#   ./local-build-deploy.sh --branch dev     # Build from a specific branch
#   ./local-build-deploy.sh --skip-build     # Re-deploy with existing images
#   ./local-build-deploy.sh --dry-run        # Show what would be done
#
# Environment variables (optional):
#   VITE_GOOGLE_CLIENT_ID  - Google OAuth client ID for frontend build
#   REPO_URL               - Override git remote URL
# =============================================================================

set -euo pipefail

# =============================================================================
# Configuration
# =============================================================================

REPO_URL="${REPO_URL:-https://github.com/OpenMined/syfthub.git}"
REPO_DIR="/opt/syfthub/repo"
DEPLOY_DIR="/opt/syfthub"
GITHUB_REPOSITORY="openmined/syfthub"  # lowercase, matching Docker/CI convention
REGISTRY="ghcr.io/${GITHUB_REPOSITORY}"

# Defaults
BRANCH="main"
SKIP_BUILD=false
DRY_RUN=false

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# =============================================================================
# Helpers
# =============================================================================

log()   { echo -e "${GREEN}[INFO]${NC}  $(date '+%H:%M:%S') - $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $(date '+%H:%M:%S') - $*"; }
error() { echo -e "${RED}[ERROR]${NC} $(date '+%H:%M:%S') - $*"; }
step()  { echo -e "\n${BLUE}[STEP]${NC}  $(date '+%H:%M:%S') - $*"; }

die() { error "$1"; exit 1; }

# =============================================================================
# Argument Parsing
# =============================================================================

while [[ $# -gt 0 ]]; do
    case $1 in
        --branch)
            BRANCH="$2"
            shift 2
            ;;
        --skip-build)
            SKIP_BUILD=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h|--help)
            head -35 "$0" | tail -30
            exit 0
            ;;
        *)
            die "Unknown argument: $1. Use --help for usage."
            ;;
    esac
done

# =============================================================================
# Pre-flight Checks
# =============================================================================

preflight() {
    step "Running pre-flight checks"

    for cmd in docker git; do
        command -v "$cmd" &>/dev/null || die "Required command not found: $cmd"
    done

    docker buildx version &>/dev/null || die "Docker Buildx not found"

    [[ -f "${DEPLOY_DIR}/.env" ]] || die "Production .env not found at ${DEPLOY_DIR}/.env"

    # Check disk space (need at least 10G free for builds)
    local free_gb
    free_gb=$(df -BG --output=avail /opt | tail -1 | tr -d ' G')
    if [[ "$free_gb" -lt 10 ]]; then
        die "Insufficient disk space: ${free_gb}G free, need at least 10G"
    fi

    log "Pre-flight checks passed (${free_gb}G disk free)"
}

# =============================================================================
# Step 1: Clone or Update Repository
# =============================================================================

update_repo() {
    step "Updating repository (branch: ${BRANCH})"

    if [[ "$DRY_RUN" == "true" ]]; then
        log "[DRY RUN] Would clone/update ${REPO_URL} branch ${BRANCH} into ${REPO_DIR}"
        IMAGE_TAG="dry-run"
        return 0
    fi

    if [[ -d "${REPO_DIR}/.git" ]]; then
        log "Existing repo found, fetching updates..."
        cd "$REPO_DIR"
        git fetch origin
        git checkout "$BRANCH"
        git reset --hard "origin/${BRANCH}"
    else
        log "Cloning repository (shallow)..."
        git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$REPO_DIR"
        cd "$REPO_DIR"
    fi

    IMAGE_TAG=$(git rev-parse --short=7 HEAD)
    log "Repository updated. HEAD: ${IMAGE_TAG} ($(git log -1 --format='%s' HEAD))"
}

# =============================================================================
# Step 2: Build Docker Images
# =============================================================================

build_images() {
    step "Building Docker images (tag: ${IMAGE_TAG})"

    if [[ "$DRY_RUN" == "true" ]]; then
        log "[DRY RUN] Would build 4 images tagged as ${REGISTRY}-{backend,frontend,aggregator,mcp}:${IMAGE_TAG} + :latest"
        if [[ -z "${VITE_GOOGLE_CLIENT_ID:-}" ]]; then
            warn "VITE_GOOGLE_CLIENT_ID not set - Google Sign-In will be disabled in this build"
        fi
        return 0
    fi

    if [[ "$SKIP_BUILD" == "true" ]]; then
        log "Skipping build (--skip-build flag set)"
        # Verify images exist locally
        local missing=false
        for svc in backend frontend aggregator mcp; do
            if ! docker image inspect "${REGISTRY}-${svc}:${IMAGE_TAG}" &>/dev/null; then
                error "Image not found: ${REGISTRY}-${svc}:${IMAGE_TAG}"
                missing=true
            fi
        done
        [[ "$missing" == "true" ]] && die "Missing images. Remove --skip-build to build them."
        return 0
    fi

    cd "$REPO_DIR"

    # Build each image matching CI's exact context, dockerfile, and target
    # -----------------------------------------------------------------------

    log "Building backend (1/4)..."
    docker build --target production \
        -t "${REGISTRY}-backend:${IMAGE_TAG}" \
        -t "${REGISTRY}-backend:latest" \
        -f components/backend/Dockerfile \
        ./components/backend

    log "Building frontend (2/4)..."
    if [[ -z "${VITE_GOOGLE_CLIENT_ID:-}" ]]; then
        warn "VITE_GOOGLE_CLIENT_ID not set - Google Sign-In will be disabled in this build"
    fi
    docker build --target production \
        -t "${REGISTRY}-frontend:${IMAGE_TAG}" \
        -t "${REGISTRY}-frontend:latest" \
        --build-arg "VITE_GOOGLE_CLIENT_ID=${VITE_GOOGLE_CLIENT_ID:-}" \
        -f components/frontend/Dockerfile \
        .

    log "Building aggregator (3/4)..."
    docker build \
        -t "${REGISTRY}-aggregator:${IMAGE_TAG}" \
        -t "${REGISTRY}-aggregator:latest" \
        -f components/aggregator/Dockerfile \
        ./components/aggregator

    log "Building mcp (4/4)..."
    docker build --target production \
        -t "${REGISTRY}-mcp:${IMAGE_TAG}" \
        -t "${REGISTRY}-mcp:latest" \
        -f components/mcp/Dockerfile \
        .

    log "All images built successfully"
    echo ""
    docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}" | grep -E "syfthub|REPOSITORY"
}

# =============================================================================
# Step 3: Sync Config Files
# =============================================================================

sync_configs() {
    step "Syncing config files to ${DEPLOY_DIR}"

    if [[ "$DRY_RUN" == "true" ]]; then
        log "[DRY RUN] Would copy docker-compose.deploy.yml, nginx.prod.conf, nats.prod.conf, deploy.sh"
        return 0
    fi

    cd "$REPO_DIR"

    mkdir -p "${DEPLOY_DIR}/nginx" "${DEPLOY_DIR}/nats"

    cp deploy/docker-compose.deploy.yml "${DEPLOY_DIR}/docker-compose.deploy.yml"
    cp deploy/nginx/nginx.prod.conf     "${DEPLOY_DIR}/nginx/nginx.prod.conf"
    cp deploy/nats/nats.prod.conf       "${DEPLOY_DIR}/nats/nats.prod.conf"
    cp deploy/scripts/deploy.sh         "${DEPLOY_DIR}/deploy.sh"
    chmod +x "${DEPLOY_DIR}/deploy.sh"

    log "Config files synced"
}

# =============================================================================
# Step 4: Deploy (using deploy.sh with pulls disabled)
# =============================================================================

run_deploy() {
    step "Running deployment (IMAGE_TAG=${IMAGE_TAG})"

    if [[ "$DRY_RUN" == "true" ]]; then
        log "[DRY RUN] Would run deploy.sh with IMAGE_TAG=${IMAGE_TAG}, pull_images disabled"
        return 0
    fi

    cd "$DEPLOY_DIR"

    # Backup deploy.sh, then replace pull_images() with a no-op.
    # This is safe because:
    #   - Images were already built and tagged locally in step 2
    #   - deploy.sh is restored immediately after deployment
    #   - Future CI runs sync a fresh deploy.sh anyway (see ci.yml "Sync config files")
    cp deploy.sh deploy.sh.pre-local-build

    sed -i '/^pull_images() {$/,/^}$/c\
pull_images() {\
    log INFO "Skipping image pulls - images were built locally by local-build-deploy.sh"\
}' deploy.sh

    # Export env vars that deploy.sh requires
    export IMAGE_TAG
    export GITHUB_REPOSITORY

    log "Starting deploy.sh (pull_images disabled)..."
    echo "=========================================="

    # Run deployment - deploy.sh handles migrations, rolling restarts, health checks
    ./deploy.sh

    echo "=========================================="

    # Restore original deploy.sh
    mv deploy.sh.pre-local-build deploy.sh
    log "Original deploy.sh restored"
}

# =============================================================================
# Main
# =============================================================================

main() {
    echo "=========================================="
    echo "  SyftHub Local Build & Deploy"
    echo "  Branch: ${BRANCH}"
    echo "  Skip Build: ${SKIP_BUILD}"
    echo "  Dry Run: ${DRY_RUN}"
    echo "=========================================="
    echo ""

    preflight
    update_repo
    build_images
    sync_configs
    run_deploy

    echo ""
    step "Deployment complete!"
    log "Image tag: ${IMAGE_TAG}"
    log "Branch: ${BRANCH}"
    log "To verify: curl -sf http://localhost/health"
}

main "$@"
