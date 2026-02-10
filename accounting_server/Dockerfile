# Multi-stage Dockerfile for Unified Global Ledger (accounting_server)
# Supports both development and production environments

# =============================================================================
# Base stage with Node.js and system dependencies
FROM node:20-slim AS base

# Set environment variables
ENV NODE_ENV=production \
    NPM_CONFIG_LOGLEVEL=warn \
    NPM_CONFIG_UPDATE_NOTIFIER=false

# Install system dependencies (for native modules and health checks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r ledger && useradd -r -g ledger -m -d /home/ledger ledger

# Set working directory
WORKDIR /app

# =============================================================================
# Dependencies stage - install production npm packages
FROM base AS dependencies

# Copy package files
COPY --chown=ledger:ledger package.json package-lock.json ./

# Install production dependencies only
RUN npm ci --only=production && npm cache clean --force

# =============================================================================
# Development stage
FROM base AS development

# Install dev dependencies
ENV NODE_ENV=development

# Copy package files
COPY --chown=ledger:ledger package.json package-lock.json ./

# Install all dependencies including dev
RUN npm ci && npm cache clean --force

# Copy source code
COPY --chown=ledger:ledger tsconfig.json ./
COPY --chown=ledger:ledger src ./src

# Copy migrations
COPY --chown=ledger:ledger migrations ./migrations

# Switch to non-root user
USER ledger

# Expose port (default 3000, configurable via PORT env)
EXPOSE 3000

# Development entrypoint - hot reload enabled
CMD ["npm", "run", "dev"]

# =============================================================================
# Testing stage
FROM development AS testing

# Run tests by default
CMD ["npm", "test"]

# =============================================================================
# Builder stage - compile TypeScript
FROM base AS builder

# Copy package files and install all dependencies (need devDependencies for build)
COPY --chown=ledger:ledger package.json package-lock.json ./
# NOTE: --include=dev is required because base stage sets NODE_ENV=production
# which would otherwise skip devDependencies (TypeScript compiler needed for build)
RUN npm ci --include=dev && npm cache clean --force

# Copy source code
COPY --chown=ledger:ledger tsconfig.json ./
COPY --chown=ledger:ledger src ./src

# Build TypeScript to JavaScript
RUN npm run build

# =============================================================================
# Production runtime stage
FROM base AS production

# Set production environment
ENV NODE_ENV=production \
    PORT=3000

# Copy production dependencies from dependencies stage
COPY --from=dependencies --chown=ledger:ledger /app/node_modules ./node_modules

# Copy built JavaScript from builder stage
COPY --from=builder --chown=ledger:ledger /app/dist ./dist

# Copy package.json for version info
COPY --chown=ledger:ledger package.json ./

# Switch to non-root user
USER ledger

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT:-3000}/health || exit 1

# Expose port
EXPOSE 3000

# Production entrypoint
CMD ["node", "dist/main/server.js"]

# =============================================================================
# Lightweight production stage (Alpine alternative)
FROM node:20-alpine AS production-alpine

# Set environment variables
ENV NODE_ENV=production \
    PORT=3000

# Install curl for health checks
RUN apk add --no-cache curl

# Create non-root user
RUN addgroup -S ledger && adduser -S -G ledger ledger

# Set working directory
WORKDIR /app

# Copy production dependencies from dependencies stage
COPY --from=dependencies --chown=ledger:ledger /app/node_modules ./node_modules

# Copy built JavaScript from builder stage
COPY --from=builder --chown=ledger:ledger /app/dist ./dist

# Copy package.json for version info
COPY --chown=ledger:ledger package.json ./

# Switch to non-root user
USER ledger

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT:-3000}/health || exit 1

# Expose port
EXPOSE 3000

# Production entrypoint
CMD ["node", "dist/main/server.js"]
