# Multi-stage Dockerfile for SyftHub UI React Application

# Stage 1: Build environment
FROM node:20-alpine AS builder

# IMPORTANT: The directory structure must match the repository layout exactly
# because package-lock.json contains relative paths for the file: dependency.
# The @syfthub/sdk dependency is: "file:../../sdk/typescript"
# So from /app/components/frontend, ../../sdk/typescript must resolve correctly.

# Set working directory for SDK build (mirrors repo: sdk/typescript)
WORKDIR /app/sdk/typescript

# Copy and build SDK first (required for file: dependency resolution)
COPY sdk/typescript/package.json sdk/typescript/package-lock.json ./
RUN npm ci
COPY sdk/typescript/ .
RUN npm run build

# Set working directory for frontend (mirrors repo: components/frontend)
WORKDIR /app/components/frontend

# Copy frontend package files
COPY components/frontend/package.json components/frontend/package-lock.json ./

# Install dependencies with retry and timeout settings
RUN npm config set fetch-retry-mintimeout 20000 && \
    npm config set fetch-retry-maxtimeout 120000 && \
    npm ci --ignore-scripts

# Copy frontend source code
COPY components/frontend/ .

# Build arguments for Vite environment variables
ARG VITE_GOOGLE_CLIENT_ID
ENV VITE_GOOGLE_CLIENT_ID=$VITE_GOOGLE_CLIENT_ID

# Build the application
RUN npm run build

# Stage 2: Production environment with nginx
FROM nginx:1.25-alpine AS production

# Install security updates
RUN apk upgrade --no-cache

# Remove default nginx config
RUN rm -rf /etc/nginx/conf.d/*

# Copy custom nginx configuration
COPY --from=builder /app/components/frontend/nginx.conf /etc/nginx/conf.d/default.conf

# Copy built application from builder stage
COPY --from=builder /app/components/frontend/dist /usr/share/nginx/html

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost/ || exit 1

# Expose port
EXPOSE 80

# Start nginx
CMD ["nginx", "-g", "daemon off;"]
