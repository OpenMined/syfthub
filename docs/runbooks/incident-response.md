# Incident Response Runbook

> **Audience:** On-call engineers, team leads
> **Last updated:** 2026-03-27

---

## Triage — First 5 Minutes

1. **Identify the affected service(s):**
   ```bash
   # Check container status
   docker compose -f deploy/docker-compose.deploy.yml ps

   # Hit health endpoints
   curl -s https://<domain>/api/v1/health
   curl -s https://<domain>/aggregator/api/v1/health
   curl -s https://<domain>/mcp/health
   ```

2. **Check recent logs:**
   ```bash
   # Last 200 lines from each service
   docker compose -f deploy/docker-compose.deploy.yml logs --tail=200 backend
   docker compose -f deploy/docker-compose.deploy.yml logs --tail=200 aggregator
   docker compose -f deploy/docker-compose.deploy.yml logs --tail=200 nginx
   ```

3. **Check if a recent deploy caused this:**
   ```bash
   # When was the last deploy?
   docker inspect --format='{{.Created}}' $(docker compose -f deploy/docker-compose.deploy.yml ps -q backend)
   ```

---

## Common Scenarios

### Backend Down (502 from Nginx)

**Symptoms:** All `/api/v1/*` requests return 502.

**Steps:**
1. Check backend container: `docker compose ps backend`
2. If crashed, check logs: `docker compose logs --tail=100 backend`
3. Common causes:
   - Database connection failed — check PostgreSQL: `docker compose ps db`
   - Missing environment variable — check `.env.deploy`
   - Migration not applied — `docker compose exec backend alembic current`
4. Restart: `docker compose restart backend`

### Aggregator Down (RAG/Chat broken)

**Symptoms:** Chat returns errors, `/aggregator/*` returns 502.

**Steps:**
1. Check aggregator container: `docker compose ps aggregator`
2. Check logs: `docker compose logs --tail=100 aggregator`
3. Common causes:
   - ONNX model failed to load (~570 MB, needs 3 CPU / 5G memory)
   - NATS connection failed — check: `docker compose ps nats`
   - Satellite token verification failed — check JWKS: `curl https://<domain>/.well-known/jwks.json`
4. Restart: `docker compose restart aggregator`

### Database Issues

**Symptoms:** 500 errors across backend, slow responses.

**Steps:**
1. Check PostgreSQL: `docker compose ps db`
2. Check connections: `docker compose exec db psql -U syfthub -c "SELECT count(*) FROM pg_stat_activity;"`
3. Check disk space: `df -h`
4. If connection pool exhausted, restart backend: `docker compose restart backend`

### Redis Down (Auth broken)

**Symptoms:** Login works but tokens expire immediately, refresh fails.

**Steps:**
1. Check Redis: `docker compose ps redis`
2. Test connectivity: `docker compose exec redis redis-cli ping`
3. Restart: `docker compose restart redis`
4. Note: Users will need to re-login after Redis restart (refresh tokens lost).

### Search Broken (Meilisearch)

**Symptoms:** Endpoint search returns empty results.

**Steps:**
1. Check Meilisearch: `docker compose ps meilisearch`
2. Check index: `curl http://localhost:7700/indexes -H "Authorization: Bearer <MEILI_KEY>"`
3. Restart: `docker compose restart meilisearch`
4. Note: Meilisearch is indexed on endpoint create/update. Existing endpoints may need re-indexing.

### NATS Down (Tunneled data sources unreachable)

**Symptoms:** RAG chat fails for NATS-tunneled data sources, HTTP data sources still work.

**Steps:**
1. Check NATS: `docker compose ps nats`
2. Restart: `docker compose restart nats`
3. Aggregator may need restart too: `docker compose restart aggregator`

---

## Escalation

If the issue isn't resolved within 15 minutes:
1. Check if a [rollback](rollback.md) is appropriate
2. Notify the team lead
3. Document the timeline and actions taken

---

## Post-Incident

After resolving:
1. Document what happened, timeline, and root cause
2. Identify preventive measures
3. Update this runbook if the scenario wasn't covered

---

## Related

- [Deployment Runbook](deploy.md)
- [Rollback Runbook](rollback.md)
- [Architecture Overview](../architecture/overview.md) — service dependency map
