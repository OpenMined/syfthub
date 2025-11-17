# Docker Setup Guide

This guide explains how to run SyftHub using Docker in both development and production environments.

## Prerequisites

- Docker Engine 20.10+
- Docker Compose 2.0+
- 4GB RAM minimum (8GB recommended for development)
- 10GB free disk space

## Quick Start

### Development Environment

1. Clone the repository:
```bash
git clone https://github.com/IonesioJunior/syfthub.git
cd syfthub
```

2. Copy environment configuration:
```bash
cp .env.example .env
```

3. Start the development environment:
```bash
docker-compose up -d
```

4. Access the application:
- API: http://localhost:8000
- Swagger Documentation: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Adminer (database UI): http://localhost:8080 (if using `--profile tools`)

### Production Environment

1. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with production values
# IMPORTANT: Change SECRET_KEY and passwords!
```

2. Build and start production services:
```bash
docker-compose -f docker-compose.prod.yml up -d
```

3. Run database migrations:
```bash
docker-compose -f docker-compose.prod.yml run --rm migrate
```

## Docker Architecture

### Multi-Stage Dockerfile

The Dockerfile uses multi-stage builds to optimize for different environments:

```
base          → Core Python environment
dependencies  → Python packages installed
development   → Dev tools + hot reload
testing       → Test runner environment
builder       → Production build stage
production    → Optimized production runtime
```

### Available Build Targets

- `development`: Full development environment with hot reload
- `testing`: Isolated testing environment
- `production`: Optimized production build
- `production-alpine`: Lightweight Alpine-based production build

## Docker Compose Services

### Development Services (`docker-compose.yml`)

| Service | Port | Description |
|---------|------|-------------|
| api | 8000 | FastAPI application with hot reload |
| db | 5432 | PostgreSQL database |
| redis | 6379 | Redis for caching/sessions |
| adminer | 8080 | Database management UI (optional) |
| test | - | Test runner (profile: test) |
| docs | 8001 | Documentation server (profile: docs) |

### Production Services (`docker-compose.prod.yml`)

| Service | Port | Description |
|---------|------|-------------|
| api | 8000 | FastAPI application (multi-worker) |
| db | - | PostgreSQL database (internal) |
| redis | - | Redis cache (internal) |
| nginx | 80/443 | Reverse proxy |
| backup | - | Automated backups (profile: backup) |
| prometheus | 9090 | Metrics collection (profile: monitoring) |
| grafana | 3000 | Metrics visualization (profile: monitoring) |

## Common Commands

### Development

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f api

# Run tests
docker-compose run --rm test

# Access shell
docker-compose exec api bash

# Rebuild after code changes
docker-compose build api

# Run with specific profile
docker-compose --profile tools up -d

# Stop all services
docker-compose down

# Remove all data (careful!)
docker-compose down -v
```

### Production

```bash
# Start production stack
docker-compose -f docker-compose.prod.yml up -d

# Run migrations
docker-compose -f docker-compose.prod.yml run --rm migrate

# View logs
docker-compose -f docker-compose.prod.yml logs -f api

# Backup database
docker-compose -f docker-compose.prod.yml --profile backup up backup

# Start with monitoring
docker-compose -f docker-compose.prod.yml --profile monitoring up -d

# Scale API workers
docker-compose -f docker-compose.prod.yml up -d --scale api=3

# Update deployment
docker-compose -f docker-compose.prod.yml pull
docker-compose -f docker-compose.prod.yml up -d --force-recreate

# Emergency rollback
docker-compose -f docker-compose.prod.yml up -d --force-recreate api
```

## Building Images

### Development Build
```bash
docker build --target development -t syfthub:dev .
```

### Production Build
```bash
docker build --target production -t syfthub:latest .
```

### Alpine Production Build (smaller size)
```bash
docker build --target production-alpine -t syfthub:alpine .
```

### Test Build
```bash
docker build --target testing -t syfthub:test .
docker run --rm syfthub:test
```

## Environment Configuration

### Essential Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ENVIRONMENT` | Environment mode | development |
| `DATABASE_URL` | Database connection string | sqlite:///./data/syfthub.db |
| `SECRET_KEY` | JWT signing key | CHANGE THIS! |
| `API_PORT` | API server port | 8000 |
| `LOG_LEVEL` | Logging level | info |

### Database URLs

**SQLite (Development)**
```
DATABASE_URL=sqlite:///./data/syfthub.db
```

**PostgreSQL (Production)**
```
DATABASE_URL=postgresql://user:password@db:5432/syfthub
```

**MySQL**
```
DATABASE_URL=mysql://user:password@db:3306/syfthub
```

## Health Checks

The containers include health checks that verify:
- API endpoint availability
- Database connectivity
- Redis connectivity (if configured)

Check health status:
```bash
docker-compose ps
docker inspect syfthub-api --format='{{.State.Health.Status}}'
```

## Volumes and Data Persistence

### Development Volumes
- `./src:/app/src` - Source code (hot reload)
- `./tests:/app/tests` - Test files
- `./data:/app/data` - SQLite database

### Production Volumes
- `postgres_data` - PostgreSQL data
- `redis_data` - Redis persistence
- `./logs:/app/logs` - Application logs
- `./backup:/backup` - Database backups

## Networking

### Development Network
- Internal bridge network
- All services accessible via service names
- Ports exposed to host for debugging

### Production Network
- Isolated bridge network with subnet
- Only nginx ports exposed
- Internal service communication only

## Security Considerations

### Production Checklist

- [ ] Change all default passwords
- [ ] Generate strong `SECRET_KEY`
- [ ] Use environment-specific `.env` files
- [ ] Enable HTTPS in nginx
- [ ] Configure firewall rules
- [ ] Set up log rotation
- [ ] Enable monitoring and alerts
- [ ] Regular backup verification
- [ ] Use secrets management service
- [ ] Implement rate limiting

### Container Security

- Non-root user execution
- Read-only root filesystem (optional)
- Resource limits configured
- Health checks enabled
- Minimal base images
- Security scanning in CI/CD

## Troubleshooting

### Container won't start
```bash
# Check logs
docker-compose logs api

# Verify environment
docker-compose config

# Check resource usage
docker system df
```

### Database connection issues
```bash
# Test database connection
docker-compose exec db psql -U syfthub -d syfthub

# Reset database
docker-compose down -v
docker-compose up -d
```

### Permission errors
```bash
# Fix ownership
docker-compose exec api chown -R syfthub:syfthub /app

# Check user
docker-compose exec api whoami
```

### Memory issues
```bash
# Increase Docker memory limit
# Docker Desktop: Settings → Resources → Memory

# Check container resources
docker stats
```

## Performance Optimization

### API Performance
- Use multiple workers in production
- Enable response caching with Redis
- Implement connection pooling
- Use async database drivers

### Docker Performance
- Use BuildKit for faster builds
- Leverage layer caching
- Multi-stage builds for smaller images
- Volume mount optimization

### Database Performance
- Configure connection pooling
- Set appropriate resource limits
- Regular VACUUM (PostgreSQL)
- Index optimization

## Monitoring

### With Prometheus/Grafana
```bash
# Start monitoring stack
docker-compose -f docker-compose.prod.yml --profile monitoring up -d

# Access dashboards
# Prometheus: http://localhost:9090
# Grafana: http://localhost:3000
```

### Log Aggregation
```bash
# View all logs
docker-compose logs

# Follow specific service
docker-compose logs -f api

# Export logs
docker-compose logs > syfthub.log
```

## Backup and Recovery

### Manual Backup
```bash
# PostgreSQL backup
docker-compose exec db pg_dump -U syfthub syfthub > backup.sql

# Full data backup
docker run --rm -v syfthub_postgres_data:/data -v $(pwd):/backup \
    alpine tar czf /backup/postgres_backup.tar.gz /data
```

### Automated Backup
```bash
# Enable backup service
docker-compose -f docker-compose.prod.yml --profile backup up -d
```

### Recovery
```bash
# Restore PostgreSQL
docker-compose exec -T db psql -U syfthub syfthub < backup.sql

# Restore volume
docker run --rm -v syfthub_postgres_data:/data -v $(pwd):/backup \
    alpine tar xzf /backup/postgres_backup.tar.gz -C /
```

## CI/CD Integration

### GitHub Actions Example
```yaml
- name: Build and push Docker image
  run: |
    docker build --target production -t syfthub:${{ github.sha }} .
    docker tag syfthub:${{ github.sha }} syfthub:latest
    docker push syfthub:latest
```

### GitLab CI Example
```yaml
build:
  stage: build
  script:
    - docker build --target production -t $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA .
    - docker push $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA
```

## Additional Resources

- [Docker Documentation](https://docs.docker.com/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [FastAPI Deployment](https://fastapi.tiangolo.com/deployment/)
- [PostgreSQL Docker](https://hub.docker.com/_/postgres)
- [Redis Docker](https://hub.docker.com/_/redis)
