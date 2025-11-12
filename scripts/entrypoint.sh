#!/bin/bash
set -e

# SyftHub Docker Entrypoint Script
echo "Starting SyftHub application..."

# Function to wait for database
wait_for_db() {
    echo "Waiting for database to be ready..."

    if [[ "$DATABASE_URL" == postgres* ]] || [[ "$DATABASE_URL" == postgresql* ]]; then
        # PostgreSQL
        until python -c "
import psycopg2
import os
from urllib.parse import urlparse
url = urlparse(os.environ.get('DATABASE_URL', ''))
try:
    conn = psycopg2.connect(
        host=url.hostname,
        port=url.port or 5432,
        database=url.path[1:],
        user=url.username,
        password=url.password
    )
    conn.close()
    exit(0)
except Exception as e:
    print(f'Database not ready: {e}')
    exit(1)
" 2>/dev/null; do
            echo "PostgreSQL is unavailable - sleeping"
            sleep 2
        done
        echo "PostgreSQL is ready!"

    elif [[ "$DATABASE_URL" == mysql* ]]; then
        # MySQL/MariaDB
        until python -c "
import pymysql
import os
from urllib.parse import urlparse
url = urlparse(os.environ.get('DATABASE_URL', ''))
try:
    conn = pymysql.connect(
        host=url.hostname,
        port=url.port or 3306,
        database=url.path[1:],
        user=url.username,
        password=url.password
    )
    conn.close()
    exit(0)
except Exception as e:
    print(f'Database not ready: {e}')
    exit(1)
" 2>/dev/null; do
            echo "MySQL is unavailable - sleeping"
            sleep 2
        done
        echo "MySQL is ready!"
    fi
}

# Function to run migrations
run_migrations() {
    echo "Running database migrations..."

    # Check if alembic is available and configured
    if [ -f "alembic.ini" ] && [ -d "alembic" ]; then
        echo "Running Alembic migrations..."
        .venv/bin/alembic upgrade head
    else
        echo "No Alembic configuration found, initializing database tables..."
        python -c "
from syfthub.database.connection import create_tables
create_tables()
print('Database tables created successfully')
"
    fi
}

# Function to create default admin user (optional)
create_admin_user() {
    if [ -n "$ADMIN_USERNAME" ] && [ -n "$ADMIN_PASSWORD" ] && [ -n "$ADMIN_EMAIL" ]; then
        echo "Creating default admin user..."
        python -c "
import os
from syfthub.auth.security import hash_password
from syfthub.auth.dependencies import fake_users_db, username_to_id
from syfthub.schemas.user import User
from syfthub.schemas.auth import UserRole
from datetime import datetime, timezone

username = os.environ['ADMIN_USERNAME']
if not username in username_to_id:
    user = User(
        id=len(fake_users_db) + 1,
        username=username,
        email=os.environ['ADMIN_EMAIL'],
        full_name='Administrator',
        role=UserRole.ADMIN,
        password_hash=hash_password(os.environ['ADMIN_PASSWORD']),
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    fake_users_db[user.id] = user
    username_to_id[username] = user.id
    print(f'Admin user {username} created successfully')
else:
    print(f'Admin user {username} already exists')
"
    fi
}

# Main execution based on environment
case "$ENVIRONMENT" in
    production)
        echo "Running in PRODUCTION mode"

        # Wait for database if configured
        if [ -n "$DATABASE_URL" ] && [[ "$DATABASE_URL" != sqlite* ]]; then
            wait_for_db
        fi

        # Run migrations
        run_migrations

        # Create admin user if configured
        create_admin_user

        # Start the application with multiple workers
        exec .venv/bin/uvicorn syfthub.main:app \
            --host 0.0.0.0 \
            --port ${PORT:-8000} \
            --workers ${WORKERS:-4} \
            --log-level ${LOG_LEVEL:-info} \
            --access-log \
            --use-colors
        ;;

    development)
        echo "Running in DEVELOPMENT mode"

        # Wait for database if configured
        if [ -n "$DATABASE_URL" ] && [[ "$DATABASE_URL" != sqlite* ]]; then
            wait_for_db
        fi

        # Run migrations
        run_migrations

        # Create admin user if configured
        create_admin_user

        # Start with hot reload
        exec .venv/bin/uvicorn syfthub.main:app \
            --host 0.0.0.0 \
            --port ${PORT:-8000} \
            --reload \
            --reload-dir src \
            --log-level ${LOG_LEVEL:-debug}
        ;;

    testing)
        echo "Running in TESTING mode"

        # Run tests
        exec .venv/bin/pytest "$@"
        ;;

    *)
        echo "Unknown environment: $ENVIRONMENT"
        echo "Valid options: production, development, testing"
        exit 1
        ;;
esac
