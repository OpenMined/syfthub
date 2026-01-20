# SyftHub Deployment and Operations Guide

> A comprehensive guide to deploying, configuring, and operating SyftHub in development and production environments.

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Development Setup](#development-setup)
- [Docker Compose Configuration](#docker-compose-configuration)
- [Environment Variables](#environment-variables)
- [Database Setup](#database-setup)
- [Redis Configuration](#redis-configuration)
- [Nginx Configuration](#nginx-configuration)
- [Production Deployment](#production-deployment)
- [Monitoring and Logging](#monitoring-and-logging)
- [Health Checks](#health-checks)
- [Troubleshooting](#troubleshooting)

---

## Architecture Overview

SyftHub is deployed as a containerized microservices architecture with the following components:

### Service Topology

```
                                    Internet
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         NGINX REVERSE PROXY                                  │
│                         (Ports 80, 443)                                      │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │ SSL/TLS Termination │ Load Balancing │ Static File Serving │ Routing   │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                    │                │                │                │
         /api/*     │      /mcp/*    │    /aggregator │      /*        │
                    ▼                ▼                ▼                ▼
┌───────────────┐ ┌───────────────┐ ┌───────────────┐ ┌───────────────────────┐
│    Backend    │ │  MCP Server   │ │   Aggregator  │ │  Frontend (Static)    │
│   (FastAPI)   │ │  (OAuth 2.1)  │ │  (RAG/Chat)   │ │  (React SPA)          │
│  Port: 8000   │ │  Port: 8002   │ │  Port: 8001   │ │  Served from volume   │
└───────┬───────┘ └───────┬───────┘ └───────┬───────┘ └───────────────────────┘
        │                 │                 │
        │                 │                 │
        ▼                 ▼                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              DATA LAYER                                      │
│  ┌───────────────────────────────┐  ┌───────────────────────────────────┐  │
│  │        PostgreSQL 16          │  │            Redis 7                │  │
│  │    (Primary Database)         │  │     (Caching & Sessions)          │  │
│  │       Port: 5432              │  │         Port: 6379                │  │
│  └───────────────────────────────┘  └───────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Services and Ports

| Service | Internal Port | External Port (Dev) | External Port (Prod) | Description |
|---------|---------------|---------------------|----------------------|-------------|
| Nginx Proxy | 80, 443 | 8080 | 80, 443 | Reverse proxy with SSL termination |
| Backend API | 8000 | - | - | FastAPI application server |
| Aggregator | 8001 | - | - | RAG orchestration service |
| MCP Server | 8002 | - | - | OAuth 2.1 and MCP protocol |
| Frontend | 3000 (dev) | - | - | React SPA (dev server or static) |
| PostgreSQL | 5432 | 5432 (dev only) | - | Primary database |
| Redis | 6379 | - | - | Cache and session store |

### Service Dependencies

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Dependency Graph                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│                         ┌─────────┐                                  │
│                         │  Proxy  │                                  │
│                         └────┬────┘                                  │
│                              │                                       │
│              ┌───────────────┼───────────────┐                       │
│              │               │               │                       │
│              ▼               ▼               ▼                       │
│         ┌─────────┐    ┌─────────┐    ┌─────────────┐               │
│         │ Backend │    │   MCP   │    │ Aggregator  │               │
│         └────┬────┘    └────┬────┘    └──────┬──────┘               │
│              │               │               │                       │
│              │               │               │                       │
│              │               └───────┬───────┘                       │
│              │                       │                               │
│              │                       │                               │
│              ▼                       ▼                               │
│         ┌─────────┐            ┌─────────┐                          │
│         │   DB    │◄───────────│ Backend │                          │
│         └────┬────┘            └─────────┘                          │
│              │                                                       │
│              ▼                                                       │
│         ┌─────────┐                                                  │
│         │  Redis  │                                                  │
│         └─────────┘                                                  │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Development Setup

### Prerequisites

- Docker Engine 24.0+
- Docker Compose v2.20+
- Git

### Quick Start

```bash
# Clone the repository
git clone https://github.com/your-org/syfthub.git
cd syfthub

# Copy environment example
cp .env.example .env

# Start all services
docker compose -f docker-compose.dev.yml up -d

# Watch logs
docker compose -f docker-compose.dev.yml logs -f
```

### Accessing Services (Development)

| Service | URL | Description |
|---------|-----|-------------|
| Main Application | http://localhost:8080 | Frontend via proxy |
| API Documentation | http://localhost:8080/docs | Swagger UI |
| ReDoc | http://localhost:8080/redoc | Alternative API docs |
| Health Check | http://localhost:8080/health | Service health endpoint |
| PostgreSQL | localhost:5432 | Direct DB access for debugging |

### Development Features

The development configuration (`docker-compose.dev.yml`) includes:

1. **Hot Reload**: Source code is mounted as volumes for automatic reloading
2. **Debug Logging**: `LOG_LEVEL=debug` enabled by default
3. **Database Access**: PostgreSQL port exposed for tools like DBeaver
4. **Vite HMR**: Frontend hot module replacement via WebSocket
5. **Network Isolation**: All services communicate via Docker bridge network

### Volume Mounts (Development)

```yaml
# Backend hot reload
- ./backend/src:/app/src:cached
- ./backend/tests:/app/tests:cached

# Frontend hot reload
- ./frontend/src:/app/src:cached
- ./frontend/public:/app/public:cached

# Aggregator hot reload
- ./aggregator/src:/app/src:cached

# MCP Server hot reload
- ./mcp/server.py:/app/server.py:cached
```

---

## Docker Compose Configuration

### Development vs Production

| Aspect | Development | Production |
|--------|-------------|------------|
| Config File | `docker-compose.dev.yml` | `docker-compose.deploy.yml` |
| Image Source | Built locally | GHCR (pre-built) |
| SSL/TLS | Not enabled | Required |
| Port Exposure | Database exposed | Internal only |
| Log Format | Console (human-readable) | JSON (structured) |
| Hot Reload | Enabled | Disabled |
| Resource Limits | None | Configured |

### Production Docker Compose Overview

```yaml
# docker-compose.deploy.yml (simplified)
services:
  proxy:
    image: nginx:1.25-alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.prod.conf:/etc/nginx/conf.d/default.conf:ro
      - ./nginx/ssl:/etc/nginx/ssl:ro
      - frontend_dist:/usr/share/nginx/html:ro
    deploy:
      resources:
        limits:
          cpus: '1'
          memory: 256M

  backend:
    image: ghcr.io/${GITHUB_REPOSITORY}-backend:${IMAGE_TAG:-latest}
    expose:
      - "8000"
    environment:
      - ENVIRONMENT=production
      - DATABASE_URL=postgresql://syfthub:${DB_PASSWORD}@db:5432/syfthub
      - SECRET_KEY=${SECRET_KEY}
      - REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 1G

  aggregator:
    image: ghcr.io/${GITHUB_REPOSITORY}-aggregator:${IMAGE_TAG:-latest}
    expose:
      - "8001"
    environment:
      - AGGREGATOR_DEBUG=false
      - AGGREGATOR_SYFTHUB_URL=http://backend:8000

  mcp:
    image: ghcr.io/${GITHUB_REPOSITORY}-mcp:${IMAGE_TAG:-latest}
    expose:
      - "8002"
    environment:
      - ENVIRONMENT=production
      - OAUTH_ISSUER=https://${DOMAIN}/mcp
      - SYFTHUB_URL=http://backend:8000

  db:
    image: postgres:16-alpine
    expose:
      - "5432"
    environment:
      - POSTGRES_PASSWORD=${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes --requirepass ${REDIS_PASSWORD}
    volumes:
      - redis_data:/data

volumes:
  postgres_data:
  redis_data:
  frontend_dist:
```

### Resource Limits (Production)

| Service | CPU Limit | Memory Limit | CPU Reserved | Memory Reserved |
|---------|-----------|--------------|--------------|-----------------|
| Proxy | 1 core | 256 MB | 0.1 core | 64 MB |
| Backend | 2 cores | 1 GB | 0.5 core | 256 MB |
| Aggregator | 1 core | 512 MB | 0.25 core | 128 MB |
| MCP | 1 core | 512 MB | 0.25 core | 128 MB |
| PostgreSQL | 1 core | 512 MB | 0.25 core | 128 MB |
| Redis | 0.5 core | 256 MB | 0.1 core | 64 MB |

---

## Environment Variables

### Complete Environment Variable Reference

#### Deployment Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GITHUB_REPOSITORY` | Prod | - | GitHub repository for GHCR images (e.g., `org/syfthub`) |
| `IMAGE_TAG` | Prod | `latest` | Docker image tag to deploy |
| `DOMAIN` | Prod | `localhost` | Production domain for CORS and SSL |

#### Security Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SECRET_KEY` | Yes | - | JWT signing key (generate with `openssl rand -hex 32`) |
| `DB_PASSWORD` | Yes | - | PostgreSQL password |
| `REDIS_PASSWORD` | Prod | - | Redis authentication password |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | `30` | JWT access token lifetime |
| `REFRESH_TOKEN_EXPIRE_DAYS` | No | `7` | JWT refresh token lifetime |

#### RSA Key Configuration (Identity Provider)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `RSA_PRIVATE_KEY_PEM` | Prod | - | Base64-encoded RSA private key |
| `RSA_PUBLIC_KEY_PEM` | Prod | - | Base64-encoded RSA public key |
| `RSA_PRIVATE_KEY_PATH` | No | - | Path to RSA private key file |
| `RSA_PUBLIC_KEY_PATH` | No | - | Path to RSA public key file |

**Generating RSA Keys:**

```bash
# Generate RSA key pair
openssl genrsa -out private.pem 2048
openssl rsa -in private.pem -pubout -out public.pem

# Base64 encode for environment variables
export RSA_PRIVATE_KEY_PEM=$(base64 -w0 private.pem)
export RSA_PUBLIC_KEY_PEM=$(base64 -w0 public.pem)
```

> **IMPORTANT**: RSA keys MUST be configured in production when running multiple workers. Without shared RSA keys, each worker generates its own keys, causing satellite token verification to fail when requests are handled by different workers.

#### Logging Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LOG_LEVEL` | No | `info` | Log level: `debug`, `info`, `warning`, `error`, `critical` |
| `LOG_FORMAT` | No | `json` | Log format: `json` (structured) or `console` (human-readable) |
| `LOG_REQUEST_BODY` | No | `false` | Include request body in logs (may contain sensitive data) |
| `LOG_RESPONSE_BODY` | No | `false` | Include response body in error logs |

#### Database Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | `sqlite:///./syfthub.db` | Full database connection URL |
| `DATABASE_ECHO` | No | `false` | Echo SQL queries (debug only) |

#### Health Check Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `HEALTH_CHECK_ENABLED` | No | `true` | Enable endpoint health monitoring |
| `HEALTH_CHECK_INTERVAL_SECONDS` | No | `30` | Interval between health check cycles |
| `HEALTH_CHECK_TIMEOUT_SECONDS` | No | `5.0` | Timeout for individual health checks |
| `HEALTH_CHECK_MAX_CONCURRENT` | No | `20` | Maximum concurrent health check requests |

#### MCP Server Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MCP_PORT` | No | `8002` | MCP server port |
| `OAUTH_ISSUER` | Yes | - | OAuth issuer URL (e.g., `https://domain.com/mcp`) |
| `OAUTH_AUDIENCE` | No | `mcp-server` | OAuth audience identifier |
| `API_BASE_URL` | Yes | - | Public MCP API base URL |
| `SYFTHUB_URL` | Yes | - | Internal SyftHub backend URL |
| `SYFTHUB_PUBLIC_URL` | Yes | - | Public SyftHub URL |
| `AGGREGATOR_URL` | Yes | - | Internal aggregator URL |

#### Aggregator Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AGGREGATOR_DEBUG` | No | `false` | Enable debug mode |
| `AGGREGATOR_SYFTHUB_URL` | Yes | - | SyftHub backend URL |
| `AGGREGATOR_CORS_ORIGINS` | No | `["*"]` | Allowed CORS origins (JSON array) |
| `AGGREGATOR_LOG_LEVEL` | No | `info` | Aggregator log level |
| `AGGREGATOR_LOG_FORMAT` | No | `json` | Aggregator log format |

### Example .env File (Production)

```bash
# =============================================================================
# SyftHub Production Environment Configuration
# =============================================================================

# Deployment
GITHUB_REPOSITORY=your-org/syfthub
IMAGE_TAG=latest
DOMAIN=syfthub.example.com

# Security (generate with: openssl rand -hex 32)
SECRET_KEY=your-super-secret-key-change-this-in-production
DB_PASSWORD=your-secure-database-password
REDIS_PASSWORD=your-secure-redis-password

# RSA Keys (required for multi-worker deployments)
RSA_PRIVATE_KEY_PEM=base64-encoded-private-key
RSA_PUBLIC_KEY_PEM=base64-encoded-public-key

# Token Configuration
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# Logging
LOG_LEVEL=info
LOG_FORMAT=json
```

---

## Database Setup

### PostgreSQL Configuration

SyftHub uses PostgreSQL 16 with the Alpine variant for a minimal footprint.

#### Connection Parameters

```
Host: db (Docker internal) / localhost (external)
Port: 5432
Database: syfthub (production) / syfthub_dev (development)
User: syfthub
Password: ${DB_PASSWORD}
```

#### Health Check

```yaml
healthcheck:
  test: ["CMD-SHELL", "pg_isready -U syfthub -d syfthub"]
  interval: 10s
  timeout: 5s
  retries: 5
```

### Database Migrations

SyftHub uses Alembic for database migrations.

#### Running Migrations

```bash
# Production: Run migrations using the migrate profile
docker compose -f docker-compose.deploy.yml --profile migrate run --rm migrate

# Development: Run inside backend container
docker compose -f docker-compose.dev.yml exec backend .venv/bin/alembic upgrade head

# Create new migration
docker compose -f docker-compose.dev.yml exec backend .venv/bin/alembic revision --autogenerate -m "Description"
```

#### Migration Service Configuration

```yaml
migrate:
  image: ghcr.io/${GITHUB_REPOSITORY}-backend:${IMAGE_TAG:-latest}
  environment:
    - DATABASE_URL=postgresql://syfthub:${DB_PASSWORD}@db:5432/syfthub
  depends_on:
    db:
      condition: service_healthy
  profiles:
    - migrate
  command: [".venv/bin/alembic", "upgrade", "head"]
```

### Database Backups

#### Automatic Backup Service

```yaml
backup:
  image: postgres:16-alpine
  environment:
    - PGHOST=db
    - PGUSER=syfthub
    - PGPASSWORD=${DB_PASSWORD}
    - PGDATABASE=syfthub
  volumes:
    - ./backup:/backup
  profiles:
    - backup
  command: |
    while true; do
      echo "Starting backup at $(date)"
      pg_dump -Fc > /backup/syfthub_$(date +%Y%m%d_%H%M%S).dump
      # Keep only last 7 backups
      ls -t /backup/*.dump 2>/dev/null | tail -n +8 | xargs -r rm
      echo "Backup completed"
      sleep 86400
    done
```

#### Manual Backup Commands

```bash
# Start backup service
docker compose -f docker-compose.deploy.yml --profile backup up -d backup

# Manual backup
docker compose -f docker-compose.deploy.yml exec db \
  pg_dump -U syfthub -Fc syfthub > backup/manual_backup.dump

# Restore from backup
docker compose -f docker-compose.deploy.yml exec -T db \
  pg_restore -U syfthub -d syfthub -c < backup/syfthub_backup.dump
```

---

## Redis Configuration

### Redis Setup

SyftHub uses Redis 7 Alpine for caching and session management.

#### Configuration

```yaml
redis:
  image: redis:7-alpine
  command: redis-server --appendonly yes --requirepass ${REDIS_PASSWORD}
  volumes:
    - redis_data:/data
  healthcheck:
    test: ["CMD", "redis-cli", "--no-auth-warning", "-a", "${REDIS_PASSWORD}", "ping"]
    interval: 10s
    timeout: 5s
    retries: 5
```

#### Connection URL Format

```
redis://:${REDIS_PASSWORD}@redis:6379/0
```

### Redis Use Cases

1. **Session Storage**: User session data
2. **Rate Limiting**: API rate limit counters
3. **Caching**: Frequently accessed data
4. **Background Jobs**: Task queues (future)

### Redis Monitoring

```bash
# Connect to Redis CLI
docker compose exec redis redis-cli -a ${REDIS_PASSWORD}

# Check memory usage
INFO memory

# List all keys
KEYS *

# Monitor real-time commands
MONITOR
```

---

## Nginx Configuration

### Development Configuration

```nginx
# nginx/nginx.dev.conf
upstream frontend {
    server frontend:3000;
}

upstream backend {
    server backend:8000;
}

upstream aggregator {
    server aggregator:8001;
}

upstream mcp {
    server mcp:8002;
}

server {
    listen 80;
    server_name localhost;

    # Backend API routes
    location /api/ {
        proxy_pass http://backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # MCP Server
    location /mcp/ {
        rewrite ^/mcp/(.*) /$1 break;
        proxy_pass http://mcp;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Aggregator with SSE support
    location /aggregator/ {
        rewrite ^/aggregator/(.*) /$1 break;
        proxy_pass http://aggregator;
        proxy_buffering off;  # Required for SSE
        proxy_cache off;
        proxy_read_timeout 300s;
    }

    # Frontend (Vite dev server with HMR)
    location / {
        proxy_pass http://frontend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400s;
    }
}
```

### Production Configuration

```nginx
# nginx/nginx.prod.conf
upstream backend {
    server backend:8000;
    keepalive 32;
}

upstream aggregator {
    server aggregator:8001;
    keepalive 16;
}

upstream mcp {
    server mcp:8002;
    keepalive 16;
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name _;

    location = /health {
        proxy_pass http://backend;
    }

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

# Main HTTPS server
server {
    listen 443 ssl http2;
    server_name _;

    # SSL Configuration
    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;
    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:50m;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:...;
    ssl_prefer_server_ciphers off;

    # HSTS
    add_header Strict-Transport-Security "max-age=63072000" always;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Gzip compression
    gzip on;
    gzip_types text/plain text/css application/json application/javascript;

    # Backend API
    location /api/ {
        proxy_pass http://backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 60s;
        proxy_read_timeout 60s;
    }

    # MCP with SSE support
    location = /mcp {
        proxy_pass http://mcp/mcp;
        proxy_buffering off;
        proxy_cache off;
        chunked_transfer_encoding on;
        proxy_read_timeout 300s;
    }

    location ^~ /mcp/ {
        rewrite ^/mcp/(.*) /$1 break;
        proxy_pass http://mcp;
    }

    # Aggregator with long timeouts for LLM
    location ^~ /aggregator/ {
        rewrite ^/aggregator/(.*) /$1 break;
        proxy_pass http://aggregator;
        proxy_buffering off;
        proxy_read_timeout 300s;
    }

    # Frontend static files
    root /usr/share/nginx/html;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    # Cache static assets
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

### SSL/TLS Setup

#### Using Let's Encrypt

```bash
# Install certbot
sudo apt install certbot

# Obtain certificate
sudo certbot certonly --standalone -d syfthub.example.com

# Copy certificates
sudo cp /etc/letsencrypt/live/syfthub.example.com/fullchain.pem /opt/syfthub/nginx/ssl/cert.pem
sudo cp /etc/letsencrypt/live/syfthub.example.com/privkey.pem /opt/syfthub/nginx/ssl/key.pem

# Set up auto-renewal cron job
echo "0 0,12 * * * root certbot renew --quiet && docker compose -f /opt/syfthub/docker-compose.deploy.yml restart proxy" | sudo tee /etc/cron.d/certbot-renew
```

#### Self-Signed Certificate (Development/Testing)

```bash
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx/ssl/key.pem \
  -out nginx/ssl/cert.pem \
  -subj "/CN=localhost"
```

---

## Production Deployment

### Prerequisites

1. **VM/Server Requirements**:
   - Ubuntu 22.04+ or similar Linux distribution
   - 4 GB RAM minimum (8 GB recommended)
   - 2 CPU cores minimum
   - 50 GB disk space
   - Docker Engine 24.0+
   - Docker Compose v2.20+

2. **Network Requirements**:
   - Ports 80 and 443 accessible from internet
   - DNS configured for your domain

3. **GitHub Requirements**:
   - Repository secrets configured for CD pipeline
   - GHCR access configured

### Step-by-Step Deployment Guide

#### 1. Prepare the Server

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER

# Install Docker Compose plugin
sudo apt install docker-compose-plugin

# Create deployment directory
sudo mkdir -p /opt/syfthub
sudo chown $USER:$USER /opt/syfthub
cd /opt/syfthub

# Create necessary directories
mkdir -p nginx/ssl backup data/rsa_keys
```

#### 2. Configure Environment

```bash
# Create .env file
cat > .env << 'EOF'
# Deployment
GITHUB_REPOSITORY=your-org/syfthub
IMAGE_TAG=latest
DOMAIN=syfthub.example.com

# Secrets (generate secure values!)
SECRET_KEY=$(openssl rand -hex 32)
DB_PASSWORD=$(openssl rand -base64 24)
REDIS_PASSWORD=$(openssl rand -base64 24)

# Token Configuration
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# Logging
LOG_LEVEL=info
LOG_FORMAT=json
EOF

# Generate RSA keys
openssl genrsa -out private.pem 2048
openssl rsa -in private.pem -pubout -out public.pem
echo "RSA_PRIVATE_KEY_PEM=$(base64 -w0 private.pem)" >> .env
echo "RSA_PUBLIC_KEY_PEM=$(base64 -w0 public.pem)" >> .env
rm private.pem public.pem
```

#### 3. Copy Configuration Files

```bash
# Copy required files from repository
cp docker-compose.deploy.yml /opt/syfthub/
cp -r nginx /opt/syfthub/
```

#### 4. Setup SSL Certificates

```bash
# Option A: Let's Encrypt (production)
sudo certbot certonly --standalone -d syfthub.example.com
sudo cp /etc/letsencrypt/live/syfthub.example.com/fullchain.pem /opt/syfthub/nginx/ssl/cert.pem
sudo cp /etc/letsencrypt/live/syfthub.example.com/privkey.pem /opt/syfthub/nginx/ssl/key.pem
sudo chown $USER:$USER /opt/syfthub/nginx/ssl/*.pem

# Option B: Self-signed (testing)
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx/ssl/key.pem -out nginx/ssl/cert.pem \
  -subj "/CN=syfthub.example.com"
```

#### 5. Login to GitHub Container Registry

```bash
# Login to GHCR
echo $GITHUB_TOKEN | docker login ghcr.io -u USERNAME --password-stdin
```

#### 6. Deploy the Stack

```bash
# Pull latest images
docker compose -f docker-compose.deploy.yml pull

# Start services
docker compose -f docker-compose.deploy.yml up -d

# Run database migrations
docker compose -f docker-compose.deploy.yml --profile migrate run --rm migrate

# Verify deployment
docker compose -f docker-compose.deploy.yml ps
curl -k https://localhost/health
```

#### 7. Enable Automatic Backups

```bash
docker compose -f docker-compose.deploy.yml --profile backup up -d backup
```

### Deployment Verification Checklist

- [ ] All containers are running (`docker compose ps`)
- [ ] Health endpoint returns 200 (`curl https://domain.com/health`)
- [ ] SSL certificate is valid (`curl -I https://domain.com`)
- [ ] Database migrations completed successfully
- [ ] Frontend loads correctly
- [ ] API documentation accessible at `/docs`
- [ ] MCP OAuth discovery working (`/.well-known/oauth-authorization-server/mcp`)

---

## Monitoring and Logging

### Structured Logging

SyftHub uses structured JSON logging for production environments with the following features:

#### Log Format

```json
{
  "timestamp": "2024-01-15T10:30:45.123456Z",
  "level": "info",
  "logger": "syfthub.api.auth",
  "message": "user.login.success",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
  "user_id": 123,
  "method": "POST",
  "path": "/api/v1/auth/login",
  "duration_ms": 45
}
```

#### Log Events

| Event | Level | Description |
|-------|-------|-------------|
| `request.started` | INFO | HTTP request received |
| `request.completed` | INFO/WARN | Request completed (WARN for 4xx) |
| `request.failed` | ERROR | Request failed (5xx or exception) |
| `user.login.success` | INFO | Successful user login |
| `user.login.failed` | WARN | Failed login attempt |
| `endpoint.health.changed` | INFO | Endpoint health status changed |

### Correlation IDs

Every request is assigned a unique correlation ID for distributed tracing:

1. **Generation**: UUID v4 generated if not provided in `X-Correlation-ID` header
2. **Propagation**: Stored in context variable for async-safe access
3. **Logging**: Automatically included in all log entries
4. **Response**: Returned in `X-Correlation-ID` response header

```python
# Accessing correlation ID in code
from syfthub.observability import get_correlation_id

correlation_id = get_correlation_id()
logger.info("Processing request", correlation_id=correlation_id)
```

### Log Collection

#### Docker Logging Configuration

```yaml
logging:
  driver: json-file
  options:
    max-size: "50m"
    max-file: "3"
```

#### Viewing Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f backend

# Filter by time
docker compose logs --since 1h backend

# Search logs
docker compose logs backend 2>&1 | jq 'select(.level == "error")'
```

### Monitoring Recommendations

#### Prometheus Metrics (Future)

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'syfthub'
    static_configs:
      - targets: ['backend:8000', 'aggregator:8001', 'mcp:8002']
    metrics_path: '/metrics'
```

#### Grafana Dashboard Suggestions

1. **Request Rate**: Requests per second by endpoint
2. **Latency**: P50, P95, P99 response times
3. **Error Rate**: 4xx and 5xx responses
4. **Database**: Connection pool, query times
5. **Redis**: Hit rate, memory usage
6. **Endpoint Health**: Active vs inactive endpoints

#### External Monitoring Services

- **Uptime Robot**: External uptime monitoring
- **Datadog**: APM and infrastructure monitoring
- **Sentry**: Error tracking and alerting

---

## Health Checks

### Service Health Endpoints

| Service | Endpoint | Method | Expected Response |
|---------|----------|--------|-------------------|
| Backend | `/health` | GET | `{"status": "healthy", "version": "x.x.x"}` |
| Aggregator | `/health` | GET | `{"status": "healthy"}` |
| MCP | `/health` | GET | `{"status": "healthy"}` |
| Proxy | `/health` (proxied) | GET | Backend health response |

### Docker Health Checks

```yaml
# Backend health check
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 40s

# PostgreSQL health check
healthcheck:
  test: ["CMD-SHELL", "pg_isready -U syfthub -d syfthub"]
  interval: 10s
  timeout: 5s
  retries: 5

# Redis health check
healthcheck:
  test: ["CMD", "redis-cli", "--no-auth-warning", "-a", "${REDIS_PASSWORD}", "ping"]
  interval: 10s
  timeout: 5s
  retries: 5
```

### Endpoint Health Monitor

SyftHub includes a background task that monitors registered endpoint health:

```python
# Configuration
HEALTH_CHECK_ENABLED=true
HEALTH_CHECK_INTERVAL_SECONDS=30
HEALTH_CHECK_TIMEOUT_SECONDS=5.0
HEALTH_CHECK_MAX_CONCURRENT=20
```

**Behavior**:
- Periodically checks all registered endpoints
- Marks endpoints as inactive if unreachable
- Restores active status when endpoint becomes reachable
- Runs concurrently with configurable limits

### Monitoring Health Status

```bash
# Check all container health
docker compose ps

# Check specific service health
docker inspect --format='{{.State.Health.Status}}' syfthub-backend

# Check health history
docker inspect --format='{{json .State.Health}}' syfthub-backend | jq
```

---

## Troubleshooting

### Common Issues and Solutions

#### 1. Services Not Starting

**Symptoms**: Containers exit immediately or fail to start

**Diagnosis**:
```bash
# Check container logs
docker compose logs <service>

# Check container status
docker compose ps -a

# Check for port conflicts
sudo lsof -i :8080
```

**Solutions**:
- Ensure all required environment variables are set
- Check for port conflicts
- Verify Docker has enough resources
- Check file permissions on mounted volumes

#### 2. Database Connection Failures

**Symptoms**: Backend fails to connect to PostgreSQL

**Diagnosis**:
```bash
# Check if database is running
docker compose exec db pg_isready -U syfthub

# Check database logs
docker compose logs db

# Test connection manually
docker compose exec backend python -c "from syfthub.database.connection import db_manager; print(db_manager.get_session())"
```

**Solutions**:
- Wait for database health check to pass before starting dependent services
- Verify DATABASE_URL is correct
- Check DB_PASSWORD matches in all services
- Ensure postgres_data volume has correct permissions

#### 3. SSL/TLS Issues

**Symptoms**: HTTPS not working, certificate errors

**Diagnosis**:
```bash
# Check certificate files exist
ls -la nginx/ssl/

# Verify certificate validity
openssl x509 -in nginx/ssl/cert.pem -text -noout

# Test SSL configuration
openssl s_client -connect localhost:443 -servername domain.com
```

**Solutions**:
- Ensure cert.pem and key.pem are in the correct location
- Check file permissions (readable by nginx user)
- Verify certificate matches domain
- Renew expired certificates

#### 4. Nginx Proxy Errors

**Symptoms**: 502 Bad Gateway, 504 Gateway Timeout

**Diagnosis**:
```bash
# Check nginx logs
docker compose logs proxy

# Verify upstream services are running
docker compose exec proxy curl -f http://backend:8000/health

# Check nginx configuration
docker compose exec proxy nginx -t
```

**Solutions**:
- Ensure backend services are healthy before proxy starts
- Increase proxy timeout for long-running operations
- Check service names match upstream configuration
- Verify internal DNS resolution works

#### 5. RSA Key Mismatch (Multi-Worker)

**Symptoms**: Satellite token verification fails intermittently

**Diagnosis**:
```bash
# Check if RSA keys are configured
docker compose exec backend env | grep RSA

# Verify keys are identical across workers
docker compose logs backend | grep "RSA keys"
```

**Solutions**:
- Configure RSA_PRIVATE_KEY_PEM and RSA_PUBLIC_KEY_PEM environment variables
- Ensure all workers share the same keys
- Use persistent volume for auto-generated keys in development

#### 6. Memory Issues

**Symptoms**: Services killed by OOM, slow responses

**Diagnosis**:
```bash
# Check memory usage
docker stats

# Check container resource limits
docker inspect --format='{{.HostConfig.Memory}}' syfthub-backend
```

**Solutions**:
- Increase memory limits in deploy configuration
- Optimize database queries
- Enable Redis caching for frequently accessed data
- Scale horizontally instead of vertically

### Debug Mode

Enable debug mode for detailed logging:

```bash
# Development
docker compose -f docker-compose.dev.yml up -d

# Production (temporary)
docker compose -f docker-compose.deploy.yml exec backend env LOG_LEVEL=debug

# Or set in .env
LOG_LEVEL=debug
LOG_FORMAT=console  # Human-readable output
```

### Useful Diagnostic Commands

```bash
# View real-time logs with filtering
docker compose logs -f --tail=100 backend | jq 'select(.level == "error")'

# Execute commands in running container
docker compose exec backend .venv/bin/python -c "from syfthub.core.config import settings; print(settings.model_dump())"

# Check network connectivity
docker compose exec backend curl -v http://db:5432

# Database shell
docker compose exec db psql -U syfthub -d syfthub

# Redis CLI
docker compose exec redis redis-cli -a $REDIS_PASSWORD

# Restart single service
docker compose restart backend

# Force recreate containers
docker compose up -d --force-recreate backend

# View container resource usage
docker stats --no-stream

# Clean up unused resources
docker system prune -a --volumes
```

### Getting Help

1. **Check Logs First**: Most issues are revealed in container logs
2. **Verify Environment**: Ensure all required variables are set correctly
3. **Test Health Endpoints**: Confirm services respond to health checks
4. **Check Dependencies**: Verify database and Redis are accessible
5. **Review Configuration**: Compare with example configurations

---

## Appendix

### Quick Reference Commands

```bash
# Development
docker compose -f docker-compose.dev.yml up -d          # Start
docker compose -f docker-compose.dev.yml down           # Stop
docker compose -f docker-compose.dev.yml logs -f        # Logs

# Production
docker compose -f docker-compose.deploy.yml pull       # Pull images
docker compose -f docker-compose.deploy.yml up -d      # Start
docker compose -f docker-compose.deploy.yml down       # Stop

# Migrations
docker compose -f docker-compose.deploy.yml --profile migrate run --rm migrate

# Backups
docker compose -f docker-compose.deploy.yml --profile backup up -d backup
```

### File Structure

```
/opt/syfthub/
├── docker-compose.deploy.yml
├── .env
├── nginx/
│   ├── nginx.prod.conf
│   └── ssl/
│       ├── cert.pem
│       └── key.pem
├── backup/
│   └── syfthub_YYYYMMDD_HHMMSS.dump
└── data/
    └── rsa_keys/
```

### Port Reference

| Port | Protocol | Service | Environment |
|------|----------|---------|-------------|
| 80 | HTTP | Nginx | Production |
| 443 | HTTPS | Nginx | Production |
| 8080 | HTTP | Nginx | Development |
| 8000 | HTTP | Backend | Internal |
| 8001 | HTTP | Aggregator | Internal |
| 8002 | HTTP | MCP | Internal |
| 5432 | TCP | PostgreSQL | Internal (dev: external) |
| 6379 | TCP | Redis | Internal |
