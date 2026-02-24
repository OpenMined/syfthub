#!/usr/bin/env python
"""Health check script for Docker containers."""

import os
import sys
import time
from urllib.parse import urlparse

import requests


def check_api_health(
    url: str = "http://localhost:8000/health", timeout: int = 5
) -> bool:
    """Check if the API is healthy."""
    try:
        response = requests.get(url, timeout=timeout)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "healthy":
                print(f"✓ API is healthy: {data}")
                return True
        print(f"✗ API returned unhealthy status: {response.status_code}")
        return False
    except requests.exceptions.RequestException as e:
        print(f"✗ API health check failed: {e}")
        return False


def check_database_health() -> bool:
    """Check if the database is accessible."""
    database_url = os.environ.get("DATABASE_URL", "")

    if not database_url:
        print("⚠ No DATABASE_URL configured, skipping database check")
        return True

    parsed = urlparse(database_url)

    if parsed.scheme in ["postgresql", "postgres"]:
        try:
            import psycopg2

            conn = psycopg2.connect(database_url)
            conn.close()
            print("✓ PostgreSQL database is healthy")
            return True
        except Exception as e:
            print(f"✗ PostgreSQL database check failed: {e}")
            return False

    elif parsed.scheme == "mysql":
        try:
            import pymysql

            conn = pymysql.connect(
                host=parsed.hostname,
                port=parsed.port or 3306,
                user=parsed.username,
                password=parsed.password,
                database=parsed.path[1:],
            )
            conn.close()
            print("✓ MySQL database is healthy")
            return True
        except Exception as e:
            print(f"✗ MySQL database check failed: {e}")
            return False

    elif parsed.scheme.startswith("sqlite"):
        print("✓ SQLite database (no connection check needed)")
        return True

    print(f"⚠ Unknown database scheme: {parsed.scheme}")
    return True


def check_redis_health() -> bool:
    """Check if Redis is accessible."""
    redis_url = os.environ.get("REDIS_URL", "")

    if not redis_url:
        print("⚠ No REDIS_URL configured, skipping Redis check")
        return True

    try:
        import redis

        r = redis.from_url(redis_url)
        r.ping()
        print("✓ Redis is healthy")
        return True
    except Exception as e:
        print(f"✗ Redis check failed: {e}")
        return False


def main():
    """Run all health checks."""
    print("Running SyftHub health checks...")
    print("-" * 40)

    checks = [
        ("API", check_api_health),
        ("Database", check_database_health),
        ("Redis", check_redis_health),
    ]

    results = []
    for name, check_func in checks:
        print(f"\nChecking {name}...")
        try:
            results.append(check_func())
        except Exception as e:
            print(f"✗ {name} check error: {e}")
            results.append(False)

    print("\n" + "-" * 40)
    if all(results):
        print("✓ All health checks passed")
        sys.exit(0)
    else:
        failed = [
            name
            for name, result in zip([c[0] for c in checks], results, strict=True)
            if not result
        ]
        print(f"✗ Health checks failed: {', '.join(failed)}")
        sys.exit(1)


if __name__ == "__main__":
    # Add retry logic for container startup
    max_retries = int(os.environ.get("HEALTH_CHECK_RETRIES", "3"))
    retry_delay = int(os.environ.get("HEALTH_CHECK_RETRY_DELAY", "5"))

    for attempt in range(max_retries):
        try:
            main()
        except SystemExit as e:
            if e.code == 0:
                sys.exit(0)
            elif attempt < max_retries - 1:
                print(
                    f"\nRetrying in {retry_delay} seconds... (attempt {attempt + 1}/{max_retries})"
                )
                time.sleep(retry_delay)
            else:
                sys.exit(1)
