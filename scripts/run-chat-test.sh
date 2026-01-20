#!/bin/bash
#
# Quick test runner with pre-configured test credentials
#

# Test credentials
export SYFTHUB_URL="https://syfthub.openmined.org"
export SYFTHUB_USERNAME="testuser_chatflow_$(date +%s)"
export SYFTHUB_EMAIL="testuser.chatflow.$(date +%s)@example.com"
export SYFTHUB_PASSWORD="TestChat2024!Secure"
export SYFTHUB_PROMPT="How much kcal has an avocado?"

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=============================================="
echo "  SyftHub Chat Workflow Test"
echo "=============================================="
echo ""
echo "Test Configuration:"
echo "  URL:      $SYFTHUB_URL"
echo "  Username: $SYFTHUB_USERNAME"
echo "  Email:    $SYFTHUB_EMAIL"
echo "  Prompt:   $SYFTHUB_PROMPT"
echo ""

# Run the main script with all arguments passed through
exec "$SCRIPT_DIR/test-chat-workflow.sh" "$@"
