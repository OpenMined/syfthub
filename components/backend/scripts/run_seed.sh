#!/bin/bash

# Seed data script runner for Syfthub
# This script sets up the environment and runs the data seeding

set -e

echo "🌱 Syfthub Data Seeding Script"
echo "=============================="

# Check if Syfthub server is running
echo "Checking if Syfthub server is running..."
if ! curl -s http://localhost:8000/health > /dev/null; then
    echo "❌ Syfthub server is not running at http://localhost:8000"
    echo "Please start the server first with 'make run' or 'docker-compose up'"
    exit 1
fi

echo "✅ Syfthub server is running"

# Check if we're in the syfthub project directory
if [[ ! -f "../pyproject.toml" ]]; then
    echo "❌ Please run this script from the syfthub project root or scripts/ directory"
    exit 1
fi

# Use uv to run the script with project dependencies
echo "Starting data seeding..."
cd "$(dirname "$0")"
cd ..
uv run python scripts/seed_data.py

echo "🎉 Data seeding completed successfully!"
echo ""
echo "You can now explore the populated data at:"
echo "  • API Documentation: http://localhost:8000/docs"
echo "  • Health Check: http://localhost:8000/health"
echo "  • User profiles: http://localhost:8000/alice_chen"
echo "  • Organizations: http://localhost:8000/tech-innovation-lab"
