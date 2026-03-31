# Rollback Runbook

> **Audience:** DevOps engineers, on-call operators
> **Last updated:** 2026-03-27

---

## When to Rollback

Rollback when a deployment causes:
- Health check failures on any service
- Error rate spike in backend/aggregator logs
- User-facing broken functionality confirmed by team
- Database migration failure (partial apply)

---

## Application Rollback (No Schema Changes)

If the deployment only changed application code (no Alembic migrations):

1. **Identify the previous image tag:**
   ```bash
   # Check what was running before
   docker compose -f deploy/docker-compose.deploy.yml ps --format json | jq '.[].Image'
   ```

2. **Update the image tags** in `.env.deploy` or `docker-compose.deploy.yml` to the previous version.

3. **Pull and restart:**
   ```bash
   docker compose -f deploy/docker-compose.deploy.yml pull
   docker compose -f deploy/docker-compose.deploy.yml up -d
   ```

4. **Verify:**
   ```bash
   curl https://<domain>/api/v1/health
   docker compose -f deploy/docker-compose.deploy.yml logs --tail=50 backend
   ```

---

## Application Rollback (With Schema Changes)

If the deployment included Alembic migrations:

1. **Rollback the migration first:**
   ```bash
   docker compose -f deploy/docker-compose.deploy.yml exec backend alembic downgrade -1
   ```

   For multiple migrations:
   ```bash
   # Downgrade to a specific revision
   docker compose -f deploy/docker-compose.deploy.yml exec backend alembic downgrade <revision_id>
   ```

2. **Then rollback the application** (same steps as above — update image tags, pull, restart).

3. **Verify migration state:**
   ```bash
   docker compose -f deploy/docker-compose.deploy.yml exec backend alembic current
   ```

**Warning:** Not all migrations are reversible. Check that the migration file has a `downgrade()` function before attempting rollback. If it doesn't, manual DB intervention may be needed.

---

## Quick Reference

```bash
# Check current deployment state
docker compose -f deploy/docker-compose.deploy.yml ps

# Check current migration
docker compose -f deploy/docker-compose.deploy.yml exec backend alembic current

# Rollback one migration
docker compose -f deploy/docker-compose.deploy.yml exec backend alembic downgrade -1

# Restart with previous images
docker compose -f deploy/docker-compose.deploy.yml pull && docker compose -f deploy/docker-compose.deploy.yml up -d

# Verify health
curl https://<domain>/api/v1/health
```

---

## Related

- [Deployment Runbook](deploy.md)
- [Incident Response Runbook](incident-response.md)
