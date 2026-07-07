# Deployment Runbook

> **Audience:** DevOps engineers, team leads
> **Last updated:** 2026-03-27

---

## Prerequisites

- SSH access to the deployment server
- Docker and Docker Compose installed on the server
- Access to GHCR (GitHub Container Registry) for pulling images
- `.env.deploy` file populated on the server (see [Environment Variables](#environment-variables))

---

## Development Deployment

### Start All Services

```bash
make dev
```

This runs `docker compose -f deploy/docker-compose.dev.yml up -d`, starting all 8 containers:
- nginx (:8080), backend (:8000), frontend (:3000), aggregator (:8001), mcp (:8002)
- postgres (:5432), redis (:6379), meilisearch (:7700)

### Verify

```bash
# Check all containers are running
docker compose -f deploy/docker-compose.dev.yml ps

# Check health endpoints
curl http://localhost:8080/api/v1/health
curl http://localhost:8080/aggregator/api/v1/health

# View logs
make logs
```

### Stop

```bash
make stop
```

---

## Production Deployment

### Standard Deploy

1. **SSH to the server:**
   ```bash
   ssh deploy@<server-ip>
   cd /opt/syfthub
   ```

2. **Pull latest images from GHCR:**
   ```bash
   docker compose -f deploy/docker-compose.deploy.yml pull
   ```

3. **Apply database migrations:**
   ```bash
   docker compose -f deploy/docker-compose.deploy.yml exec backend alembic upgrade head
   ```

4. **Restart services:**
   ```bash
   docker compose -f deploy/docker-compose.deploy.yml up -d
   ```

5. **Verify:**
   ```bash
   # Check containers
   docker compose -f deploy/docker-compose.deploy.yml ps

   # Check health
   curl https://<domain>/api/v1/health
   curl https://<domain>/aggregator/api/v1/health

   # Check logs for errors
   docker compose -f deploy/docker-compose.deploy.yml logs --tail=50 backend
   docker compose -f deploy/docker-compose.deploy.yml logs --tail=50 aggregator
   ```

### Emergency Local-Build Deploy

If GHCR egress is unavailable, use the local build script:

```bash
bash deploy/scripts/local-build-deploy.sh
```

This builds images locally on the server instead of pulling from GHCR.

---

## Database Migrations

Migrations are managed with Alembic:

```bash
# Generate a new migration (dev)
cd components/backend
alembic revision --autogenerate -m "description of change"

# Apply all pending migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# Check current migration state
alembic current
```

Migration files location: `components/backend/alembic/versions/`

**Production migrations:** Always run `alembic upgrade head` inside the backend container before restarting after a deploy with schema changes.

---

## Environment Variables

Populate `.env.deploy` on the production server. Critical variables:

| Variable | Required | Description |
|---|---|---|
| `DOMAIN` | Yes | Public domain (e.g., `hub.syft.com`) |
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `REDIS_URL` | Yes | Redis connection string |
| `JWT_SECRET` | Yes | HS256 signing key (generate with `openssl rand -hex 32`) |
| `JWT_PRIVATE_KEY` | Yes | RSA private key (PEM format) |
| `JWT_PUBLIC_KEY` | Yes | RSA public key (PEM format) |
| `NATS_URL` | Yes | NATS connection string |
| `MEILI_URL` | Yes | Meilisearch URL |
| `MEILI_KEY` | Yes | Meilisearch master key |
| `CORS_ORIGINS` | Yes | Allowed origins (set to your domain, not `*`) |

Full variable reference: `.env.example` in project root.

---

## Health Checks

All services expose health endpoints:

| Service | Endpoint | Expected Response |
|---|---|---|
| Backend | `GET /api/v1/health` | `{"status": "ok"}` |
| Aggregator | `GET /aggregator/api/v1/health` | `{"status": "ok"}` |
| MCP | `GET /mcp/health` | `{"status": "ok"}` |
| Nginx | `GET /` | HTTP 200 (frontend loads) |

---

## Monitoring

### Container Logs

```bash
# All services
make logs

# Specific service
docker compose -f deploy/docker-compose.deploy.yml logs --tail=100 -f backend
docker compose -f deploy/docker-compose.deploy.yml logs --tail=100 -f aggregator
```

### Health Monitor

The backend runs a background health monitor that checks registered endpoint URLs every 30 seconds. It uses PostgreSQL advisory lock ID `839201` to prevent duplicate checks across workers.

Monitor health check results:
```bash
# Check recent health check logs
docker compose -f deploy/docker-compose.deploy.yml logs --tail=200 backend | grep -i health
```

---

## Troubleshooting

### Backend won't start
1. Check `DATABASE_URL` — can the container reach PostgreSQL?
2. Check `alembic upgrade head` — are migrations applied?
3. Check logs: `docker compose logs backend`

### Frontend shows blank page
1. Check `VITE_API_BASE_URL` was set correctly at build time
2. Check Nginx is running: `docker compose ps nginx`
3. Check frontend container: `docker compose logs frontend`

### Aggregator returns 401
1. The aggregator verifies satellite tokens — check JWKS is accessible: `curl https://<domain>/.well-known/jwks.json`
2. Check that the backend's RSA keys are configured

### Meilisearch not returning results
1. Check `MEILI_URL` and `MEILI_KEY` in backend env
2. Verify the index exists: `curl http://localhost:7700/indexes`
3. Re-index if needed (endpoint create/update triggers indexing)

---

## Related

- [Rollback Runbook](rollback.md)
- [Incident Response Runbook](incident-response.md)
- [Architecture Overview](../architecture/overview.md)
