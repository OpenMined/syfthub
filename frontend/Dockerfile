# Multi-stage Dockerfile for SyftHub UI React Application

# Stage 1: Build environment
FROM node:20-alpine AS builder

# Set working directory for SDK build
WORKDIR /sdk/typescript

# Copy and build SDK first (required for file: dependency resolution)
COPY sdk/typescript/package*.json ./
RUN npm ci
COPY sdk/typescript/ .
RUN npm run build

# Set working directory for frontend
WORKDIR /app

# Copy frontend package files
COPY frontend/package*.json ./

# Install dependencies with retry and timeout settings
RUN npm config set fetch-retry-mintimeout 20000 && \
    npm config set fetch-retry-maxtimeout 120000 && \
    npm ci --ignore-scripts

# Copy frontend source code
COPY frontend/ .

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
COPY --from=builder /app/nginx.conf /etc/nginx/conf.d/default.conf

# Copy built application from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost/ || exit 1

# Expose port
EXPOSE 80

# Start nginx
CMD ["nginx", "-g", "daemon off;"]
