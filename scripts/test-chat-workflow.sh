#!/bin/bash
#
# SyftHub LLM Chat Workflow Test Script
# =====================================
# This script emulates the complete frontend chat workflow using curl requests.
# It tests the entire flow from user registration to making a chat request through the aggregator.
#
# Usage:
#   ./test-chat-workflow.sh                    # Interactive mode (prompts for input)
#   ./test-chat-workflow.sh --skip-register    # Skip registration, use existing user
#   ./test-chat-workflow.sh --help             # Show help
#
# Environment Variables (optional):
#   SYFTHUB_URL        - Base URL (default: https://syfthub.openmined.org)
#   SYFTHUB_USERNAME   - Username for login (skips prompt)
#   SYFTHUB_EMAIL      - Email for registration/login
#   SYFTHUB_PASSWORD   - Password (skips prompt)
#   SYFTHUB_PROMPT     - Chat prompt to use
#
# Requirements:
#   - curl
#   - jq (for JSON parsing)
#

set -e

# =============================================================================
# CONFIGURATION
# =============================================================================

BASE_URL="${SYFTHUB_URL:-https://syfthub.openmined.org}"
API_URL="${BASE_URL}/api/v1"
AGGREGATOR_URL="${BASE_URL}/aggregator/api/v1"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Default values
SKIP_REGISTER=false
VERBOSE=false
STREAM_MODE=false

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

print_header() {
    echo ""
    echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
}

print_step() {
    echo ""
    echo -e "${CYAN}► $1${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "  ${NC}$1${NC}"
}

print_json() {
    if command -v jq &> /dev/null; then
        echo "$1" | jq '.' 2>/dev/null || echo "$1"
    else
        echo "$1"
    fi
}

check_dependencies() {
    print_step "Checking dependencies..."

    if ! command -v curl &> /dev/null; then
        print_error "curl is required but not installed"
        exit 1
    fi
    print_success "curl found"

    if ! command -v jq &> /dev/null; then
        print_error "jq is required but not installed"
        print_info "Install with: apt-get install jq (Ubuntu) or brew install jq (macOS)"
        exit 1
    fi
    print_success "jq found"
}

show_help() {
    cat << EOF
SyftHub LLM Chat Workflow Test Script

Usage: $(basename "$0") [OPTIONS]

Options:
  --skip-register    Skip user registration, use existing credentials
  --stream           Use streaming endpoint instead of regular chat
  --verbose          Show detailed curl output
  --help             Show this help message

Environment Variables:
  SYFTHUB_URL        Base URL (default: https://syfthub.openmined.org)
  SYFTHUB_USERNAME   Username for login
  SYFTHUB_EMAIL      Email for registration/login
  SYFTHUB_PASSWORD   Password
  SYFTHUB_PROMPT     Chat prompt to use

Examples:
  # Interactive mode
  ./$(basename "$0")

  # With existing user
  ./$(basename "$0") --skip-register

  # With environment variables
  SYFTHUB_EMAIL=test@example.com SYFTHUB_PASSWORD=mypass ./$(basename "$0") --skip-register

  # Streaming mode
  ./$(basename "$0") --stream
EOF
}

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --skip-register)
                SKIP_REGISTER=true
                shift
                ;;
            --stream)
                STREAM_MODE=true
                shift
                ;;
            --verbose)
                VERBOSE=true
                shift
                ;;
            --help)
                show_help
                exit 0
                ;;
            *)
                print_error "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done
}

# Make HTTP request with error handling
make_request() {
    local method="$1"
    local url="$2"
    local data="$3"
    local auth_header="$4"
    local content_type="${5:-application/json}"

    local curl_args=(-s -w "\n%{http_code}")

    if [ "$VERBOSE" = true ]; then
        curl_args+=(-v)
    fi

    curl_args+=(-X "$method")
    curl_args+=("$url")

    if [ -n "$auth_header" ]; then
        curl_args+=(-H "Authorization: Bearer $auth_header")
    fi

    if [ -n "$data" ]; then
        curl_args+=(-H "Content-Type: $content_type")
        curl_args+=(-d "$data")
    fi

    local response
    response=$(curl "${curl_args[@]}" 2>&1)

    local http_code
    http_code=$(echo "$response" | tail -n1)
    local body
    body=$(echo "$response" | sed '$d')

    echo "$body"
    return 0
}

# Extract JSON field
json_get() {
    echo "$1" | jq -r "$2" 2>/dev/null
}

# =============================================================================
# WORKFLOW STEPS
# =============================================================================

# Step 1: Register User
register_user() {
    print_header "STEP 1: USER REGISTRATION"

    if [ "$SKIP_REGISTER" = true ]; then
        print_warning "Skipping registration (--skip-register flag)"
        return 0
    fi

    # Get user input
    if [ -z "$SYFTHUB_USERNAME" ]; then
        read -p "Enter username: " SYFTHUB_USERNAME
    fi
    print_info "Username: $SYFTHUB_USERNAME"

    if [ -z "$SYFTHUB_EMAIL" ]; then
        read -p "Enter email: " SYFTHUB_EMAIL
    fi
    print_info "Email: $SYFTHUB_EMAIL"

    if [ -z "$SYFTHUB_PASSWORD" ]; then
        read -s -p "Enter password: " SYFTHUB_PASSWORD
        echo ""
    fi

    read -p "Enter full name (optional): " FULL_NAME
    FULL_NAME="${FULL_NAME:-$SYFTHUB_USERNAME}"

    print_step "Registering user..."

    local register_data
    register_data=$(cat <<EOF
{
    "username": "$SYFTHUB_USERNAME",
    "email": "$SYFTHUB_EMAIL",
    "full_name": "$FULL_NAME",
    "password": "$SYFTHUB_PASSWORD"
}
EOF
)

    local response
    response=$(make_request "POST" "$API_URL/auth/register" "$register_data")

    # Check for errors
    local error_detail
    error_detail=$(json_get "$response" '.detail // empty')

    if [ -n "$error_detail" ]; then
        print_warning "Registration response: $error_detail"
        print_info "User may already exist. Will attempt login."
        return 0
    fi

    ACCESS_TOKEN=$(json_get "$response" '.access_token')
    REFRESH_TOKEN=$(json_get "$response" '.refresh_token')

    if [ -n "$ACCESS_TOKEN" ] && [ "$ACCESS_TOKEN" != "null" ]; then
        print_success "User registered successfully!"
        print_info "Access token obtained (length: ${#ACCESS_TOKEN})"
        return 0
    fi

    print_warning "Registration may have failed, will attempt login"
    return 0
}

# Step 2: Login
login_user() {
    print_header "STEP 2: USER LOGIN"

    # If we already have a token from registration, skip login
    if [ -n "$ACCESS_TOKEN" ] && [ "$ACCESS_TOKEN" != "null" ]; then
        print_info "Already have access token from registration, skipping login"
        return 0
    fi

    # Get credentials if not provided
    if [ -z "$SYFTHUB_EMAIL" ]; then
        read -p "Enter email or username: " SYFTHUB_EMAIL
    fi

    if [ -z "$SYFTHUB_PASSWORD" ]; then
        read -s -p "Enter password: " SYFTHUB_PASSWORD
        echo ""
    fi

    print_step "Logging in..."

    # Login uses form-encoded data
    local login_data="username=${SYFTHUB_EMAIL}&password=${SYFTHUB_PASSWORD}"

    local response
    response=$(make_request "POST" "$API_URL/auth/login" "$login_data" "" "application/x-www-form-urlencoded")

    ACCESS_TOKEN=$(json_get "$response" '.access_token')
    REFRESH_TOKEN=$(json_get "$response" '.refresh_token')

    if [ -z "$ACCESS_TOKEN" ] || [ "$ACCESS_TOKEN" = "null" ]; then
        print_error "Login failed!"
        print_json "$response"
        exit 1
    fi

    print_success "Login successful!"

    # Get user info
    local user_info
    user_info=$(make_request "GET" "$API_URL/auth/me" "" "$ACCESS_TOKEN")

    local username
    username=$(json_get "$user_info" '.username')
    local email
    email=$(json_get "$user_info" '.email')

    print_info "Logged in as: $username ($email)"
}

# Step 3: List Available Models
list_models() {
    print_header "STEP 3: DISCOVER AVAILABLE MODELS"

    print_step "Fetching public model endpoints..."

    local response
    response=$(make_request "GET" "$API_URL/endpoints/public?endpoint_type=model&limit=20" "" "$ACCESS_TOKEN")

    # Parse models
    MODELS_JSON="$response"
    MODEL_COUNT=$(echo "$response" | jq 'length' 2>/dev/null || echo "0")

    if [ "$MODEL_COUNT" = "0" ] || [ "$MODEL_COUNT" = "null" ]; then
        print_warning "No public models found"

        # Try trending
        print_step "Trying trending models..."
        response=$(make_request "GET" "$API_URL/endpoints/trending?endpoint_type=model&limit=20" "" "$ACCESS_TOKEN")
        MODELS_JSON="$response"
        MODEL_COUNT=$(echo "$response" | jq 'length' 2>/dev/null || echo "0")
    fi

    print_success "Found $MODEL_COUNT model(s)"

    if [ "$MODEL_COUNT" != "0" ] && [ "$MODEL_COUNT" != "null" ]; then
        echo ""
        echo "Available Models:"
        echo "─────────────────────────────────────────────────────────────"
        echo "$response" | jq -r '.[] | "  [\(.owner_username)/\(.slug)] \(.name) (★ \(.stars_count // 0))"' 2>/dev/null || true
        echo "─────────────────────────────────────────────────────────────"
    fi
}

# Step 4: List Available Data Sources
list_data_sources() {
    print_header "STEP 4: DISCOVER AVAILABLE DATA SOURCES"

    print_step "Fetching public data source endpoints..."

    local response
    response=$(make_request "GET" "$API_URL/endpoints/public?endpoint_type=data_source&limit=20" "" "$ACCESS_TOKEN")

    # Parse data sources
    DATA_SOURCES_JSON="$response"
    DS_COUNT=$(echo "$response" | jq 'length' 2>/dev/null || echo "0")

    if [ "$DS_COUNT" = "0" ] || [ "$DS_COUNT" = "null" ]; then
        print_warning "No public data sources found"

        # Try trending
        print_step "Trying trending data sources..."
        response=$(make_request "GET" "$API_URL/endpoints/trending?endpoint_type=data_source&limit=20" "" "$ACCESS_TOKEN")
        DATA_SOURCES_JSON="$response"
        DS_COUNT=$(echo "$response" | jq 'length' 2>/dev/null || echo "0")
    fi

    print_success "Found $DS_COUNT data source(s)"

    if [ "$DS_COUNT" != "0" ] && [ "$DS_COUNT" != "null" ]; then
        echo ""
        echo "Available Data Sources:"
        echo "─────────────────────────────────────────────────────────────"
        echo "$response" | jq -r '.[] | "  [\(.owner_username)/\(.slug)] \(.name) (★ \(.stars_count // 0))"' 2>/dev/null || true
        echo "─────────────────────────────────────────────────────────────"
    fi
}

# Step 5: Select Model and Data Source
select_endpoints() {
    print_header "STEP 5: SELECT MODEL AND DATA SOURCE"

    # Select Model
    print_step "Select a model endpoint..."

    if [ "$MODEL_COUNT" = "0" ] || [ "$MODEL_COUNT" = "null" ]; then
        print_error "No models available. Cannot proceed."
        exit 1
    fi

    # Show model options
    echo ""
    echo "Models:"
    local i=1
    while IFS= read -r line; do
        echo "  $i) $line"
        ((i++))
    done < <(echo "$MODELS_JSON" | jq -r '.[] | "\(.owner_username)/\(.slug) - \(.name)"' 2>/dev/null)

    read -p "Enter model number (1-$MODEL_COUNT) [1]: " MODEL_CHOICE
    MODEL_CHOICE="${MODEL_CHOICE:-1}"

    # Extract selected model (0-indexed for jq)
    local model_index=$((MODEL_CHOICE - 1))
    SELECTED_MODEL_SLUG=$(echo "$MODELS_JSON" | jq -r ".[$model_index].slug")
    SELECTED_MODEL_NAME=$(echo "$MODELS_JSON" | jq -r ".[$model_index].name")
    SELECTED_MODEL_OWNER=$(echo "$MODELS_JSON" | jq -r ".[$model_index].owner_username")
    SELECTED_MODEL_CONNECT=$(echo "$MODELS_JSON" | jq -r ".[$model_index].connect")

    # Extract URL from connect config
    SELECTED_MODEL_URL=$(echo "$SELECTED_MODEL_CONNECT" | jq -r '.[0].config.url // empty' 2>/dev/null)
    if [ -z "$SELECTED_MODEL_URL" ] || [ "$SELECTED_MODEL_URL" = "null" ]; then
        # Try alternative path
        SELECTED_MODEL_URL=$(echo "$SELECTED_MODEL_CONNECT" | jq -r '.[0].url // empty' 2>/dev/null)
    fi

    print_success "Selected model: $SELECTED_MODEL_OWNER/$SELECTED_MODEL_SLUG ($SELECTED_MODEL_NAME)"
    print_info "Model URL: ${SELECTED_MODEL_URL:-'Not specified in connect config'}"

    # Select Data Source (optional)
    print_step "Select a data source endpoint (optional)..."

    SELECTED_DS_SLUG=""
    SELECTED_DS_OWNER=""
    SELECTED_DS_URL=""

    if [ "$DS_COUNT" != "0" ] && [ "$DS_COUNT" != "null" ]; then
        echo ""
        echo "Data Sources (enter 0 to skip):"
        i=1
        while IFS= read -r line; do
            echo "  $i) $line"
            ((i++))
        done < <(echo "$DATA_SOURCES_JSON" | jq -r '.[] | "\(.owner_username)/\(.slug) - \(.name)"' 2>/dev/null)

        read -p "Enter data source number (0-$DS_COUNT) [1]: " DS_CHOICE
        DS_CHOICE="${DS_CHOICE:-1}"

        if [ "$DS_CHOICE" != "0" ]; then
            local ds_index=$((DS_CHOICE - 1))
            SELECTED_DS_SLUG=$(echo "$DATA_SOURCES_JSON" | jq -r ".[$ds_index].slug")
            SELECTED_DS_NAME=$(echo "$DATA_SOURCES_JSON" | jq -r ".[$ds_index].name")
            SELECTED_DS_OWNER=$(echo "$DATA_SOURCES_JSON" | jq -r ".[$ds_index].owner_username")
            SELECTED_DS_CONNECT=$(echo "$DATA_SOURCES_JSON" | jq -r ".[$ds_index].connect")

            # Extract URL from connect config
            SELECTED_DS_URL=$(echo "$SELECTED_DS_CONNECT" | jq -r '.[0].config.url // empty' 2>/dev/null)
            if [ -z "$SELECTED_DS_URL" ] || [ "$SELECTED_DS_URL" = "null" ]; then
                SELECTED_DS_URL=$(echo "$SELECTED_DS_CONNECT" | jq -r '.[0].url // empty' 2>/dev/null)
            fi

            print_success "Selected data source: $SELECTED_DS_OWNER/$SELECTED_DS_SLUG ($SELECTED_DS_NAME)"
            print_info "Data source URL: ${SELECTED_DS_URL:-'Not specified in connect config'}"
        else
            print_info "No data source selected (model-only chat)"
        fi
    else
        print_warning "No data sources available, proceeding with model-only chat"
    fi
}

# Step 6: Generate Satellite Tokens
generate_satellite_tokens() {
    print_header "STEP 6: GENERATE SATELLITE TOKENS"

    print_info "Satellite tokens allow the aggregator to authenticate with endpoint owners' services"

    ENDPOINT_TOKENS="{}"

    # Generate token for model owner
    print_step "Generating satellite token for model owner: $SELECTED_MODEL_OWNER"

    local model_token_response
    model_token_response=$(make_request "GET" "$API_URL/token?aud=$SELECTED_MODEL_OWNER" "" "$ACCESS_TOKEN")

    MODEL_SATELLITE_TOKEN=$(json_get "$model_token_response" '.target_token')

    if [ -n "$MODEL_SATELLITE_TOKEN" ] && [ "$MODEL_SATELLITE_TOKEN" != "null" ]; then
        print_success "Satellite token obtained for $SELECTED_MODEL_OWNER"
        print_info "Token expires in: $(json_get "$model_token_response" '.expires_in') seconds"
        ENDPOINT_TOKENS=$(echo "$ENDPOINT_TOKENS" | jq --arg owner "$SELECTED_MODEL_OWNER" --arg token "$MODEL_SATELLITE_TOKEN" '. + {($owner): $token}')
    else
        print_warning "Could not obtain satellite token for model owner"
        local error_msg=$(json_get "$model_token_response" '.detail // .message // empty')
        if [ -n "$error_msg" ]; then
            print_info "Error: $error_msg"
        fi
    fi

    # Generate token for data source owner (if different and selected)
    if [ -n "$SELECTED_DS_OWNER" ] && [ "$SELECTED_DS_OWNER" != "$SELECTED_MODEL_OWNER" ]; then
        print_step "Generating satellite token for data source owner: $SELECTED_DS_OWNER"

        local ds_token_response
        ds_token_response=$(make_request "GET" "$API_URL/token?aud=$SELECTED_DS_OWNER" "" "$ACCESS_TOKEN")

        DS_SATELLITE_TOKEN=$(json_get "$ds_token_response" '.target_token')

        if [ -n "$DS_SATELLITE_TOKEN" ] && [ "$DS_SATELLITE_TOKEN" != "null" ]; then
            print_success "Satellite token obtained for $SELECTED_DS_OWNER"
            ENDPOINT_TOKENS=$(echo "$ENDPOINT_TOKENS" | jq --arg owner "$SELECTED_DS_OWNER" --arg token "$DS_SATELLITE_TOKEN" '. + {($owner): $token}')
        else
            print_warning "Could not obtain satellite token for data source owner"
        fi
    elif [ -n "$SELECTED_DS_OWNER" ]; then
        print_info "Data source owner same as model owner, reusing token"
    fi

    print_info "Endpoint tokens: $(echo "$ENDPOINT_TOKENS" | jq -c 'to_entries | map({key: .key, value: (.value | length | tostring + " chars")}) | from_entries')"
}

# Step 7: Generate Transaction Tokens
generate_transaction_tokens() {
    print_header "STEP 7: GENERATE TRANSACTION TOKENS"

    print_info "Transaction tokens pre-authorize billing for endpoint usage"

    # Collect unique owners
    local owners=("$SELECTED_MODEL_OWNER")
    if [ -n "$SELECTED_DS_OWNER" ] && [ "$SELECTED_DS_OWNER" != "$SELECTED_MODEL_OWNER" ]; then
        owners+=("$SELECTED_DS_OWNER")
    fi

    # Build owner usernames array
    local owner_json
    owner_json=$(printf '%s\n' "${owners[@]}" | jq -R . | jq -s .)

    print_step "Requesting transaction tokens for: ${owners[*]}"

    local request_body
    request_body=$(jq -n --argjson owners "$owner_json" '{"owner_usernames": $owners}')

    local response
    response=$(make_request "POST" "$API_URL/accounting/transaction-tokens" "$request_body" "$ACCESS_TOKEN")

    TRANSACTION_TOKENS=$(json_get "$response" '.tokens // {}')
    local errors=$(json_get "$response" '.errors // {}')

    if [ "$TRANSACTION_TOKENS" != "{}" ] && [ "$TRANSACTION_TOKENS" != "null" ]; then
        print_success "Transaction tokens obtained"
        print_info "Tokens: $(echo "$TRANSACTION_TOKENS" | jq -c 'to_entries | map({key: .key, value: (.value | length | tostring + " chars")}) | from_entries')"
    else
        print_warning "Could not obtain transaction tokens (accounting may not be configured)"
        TRANSACTION_TOKENS="{}"
    fi

    if [ "$errors" != "{}" ] && [ "$errors" != "null" ]; then
        print_warning "Some token errors: $errors"
    fi
}

# Step 8: Make Chat Request
make_chat_request() {
    print_header "STEP 8: SEND CHAT REQUEST TO AGGREGATOR"

    # Get prompt
    if [ -z "$SYFTHUB_PROMPT" ]; then
        echo ""
        read -p "Enter your question/prompt: " SYFTHUB_PROMPT
    fi

    if [ -z "$SYFTHUB_PROMPT" ]; then
        SYFTHUB_PROMPT="What can you tell me about the data you have access to?"
    fi

    print_info "Prompt: $SYFTHUB_PROMPT"

    # Build model endpoint reference
    local model_ref
    model_ref=$(jq -n \
        --arg url "${SELECTED_MODEL_URL:-$BASE_URL}" \
        --arg slug "$SELECTED_MODEL_SLUG" \
        --arg name "$SELECTED_MODEL_NAME" \
        --arg owner "$SELECTED_MODEL_OWNER" \
        '{
            url: $url,
            slug: $slug,
            name: $name,
            owner_username: $owner,
            tenant_name: null
        }')

    # Build data sources array
    local data_sources="[]"
    if [ -n "$SELECTED_DS_SLUG" ]; then
        data_sources=$(jq -n \
            --arg url "${SELECTED_DS_URL:-$BASE_URL}" \
            --arg slug "$SELECTED_DS_SLUG" \
            --arg name "$SELECTED_DS_NAME" \
            --arg owner "$SELECTED_DS_OWNER" \
            '[{
                url: $url,
                slug: $slug,
                name: $name,
                owner_username: $owner,
                tenant_name: null
            }]')
    fi

    # Build complete chat request
    # Convert bash boolean to JSON boolean
    local stream_json="false"
    if [ "$STREAM_MODE" = true ]; then
        stream_json="true"
    fi

    # Ensure token variables are valid JSON (default to empty object)
    local endpoint_tokens_json="${ENDPOINT_TOKENS:-{\}}"
    local transaction_tokens_json="${TRANSACTION_TOKENS:-{\}}"

    # Validate JSON - if invalid, use empty object
    if ! echo "$endpoint_tokens_json" | jq . > /dev/null 2>&1; then
        print_warning "Invalid endpoint_tokens JSON, using empty object"
        endpoint_tokens_json="{}"
    fi
    if ! echo "$transaction_tokens_json" | jq . > /dev/null 2>&1; then
        print_warning "Invalid transaction_tokens JSON, using empty object"
        transaction_tokens_json="{}"
    fi

    local chat_request
    chat_request=$(jq -n \
        --arg prompt "$SYFTHUB_PROMPT" \
        --argjson model "$model_ref" \
        --argjson data_sources "$data_sources" \
        --argjson endpoint_tokens "$endpoint_tokens_json" \
        --argjson transaction_tokens "$transaction_tokens_json" \
        --argjson stream "$stream_json" \
        '{
            prompt: $prompt,
            model: $model,
            data_sources: $data_sources,
            endpoint_tokens: $endpoint_tokens,
            transaction_tokens: $transaction_tokens,
            top_k: 5,
            stream: $stream,
            max_tokens: 1024,
            temperature: 0.7,
            similarity_threshold: 0.5
        }')

    echo ""
    echo "Chat Request Payload:"
    echo "─────────────────────────────────────────────────────────────"
    echo "$chat_request" | jq '.'
    echo "─────────────────────────────────────────────────────────────"

    if [ "$STREAM_MODE" = true ]; then
        print_step "Sending streaming chat request to aggregator..."
        print_info "Endpoint: $AGGREGATOR_URL/chat/stream"

        echo ""
        echo "Response (SSE Stream):"
        echo "─────────────────────────────────────────────────────────────"

        # For streaming, we need to handle SSE events
        curl -s -N \
            -X POST "$AGGREGATOR_URL/chat/stream" \
            -H "Content-Type: application/json" \
            -H "Authorization: Bearer $ACCESS_TOKEN" \
            -H "Accept: text/event-stream" \
            -d "$chat_request" | while IFS= read -r line; do
                if [[ "$line" == data:* ]]; then
                    local event_data="${line#data: }"
                    if [ -n "$event_data" ]; then
                        local event_type=$(echo "$event_data" | jq -r '.type // empty' 2>/dev/null)
                        case "$event_type" in
                            "retrieval_start")
                                echo -e "${CYAN}[RETRIEVAL START]${NC} Searching $(echo "$event_data" | jq -r '.sourceCount // "?"') data sources..."
                                ;;
                            "source_complete")
                                local path=$(echo "$event_data" | jq -r '.path // "unknown"')
                                local status=$(echo "$event_data" | jq -r '.status // "unknown"')
                                local docs=$(echo "$event_data" | jq -r '.documentsRetrieved // 0')
                                echo -e "${CYAN}[SOURCE COMPLETE]${NC} $path: $status ($docs docs)"
                                ;;
                            "retrieval_complete")
                                local total=$(echo "$event_data" | jq -r '.totalDocuments // 0')
                                local time_ms=$(echo "$event_data" | jq -r '.timeMs // 0')
                                echo -e "${GREEN}[RETRIEVAL DONE]${NC} Retrieved $total documents in ${time_ms}ms"
                                ;;
                            "generation_start")
                                echo -e "${CYAN}[GENERATION START]${NC} Generating response..."
                                ;;
                            "token")
                                local content=$(echo "$event_data" | jq -r '.content // ""')
                                printf "%s" "$content"
                                ;;
                            "done")
                                echo ""
                                echo -e "${GREEN}[DONE]${NC} Response complete"
                                echo ""
                                echo "Sources:"
                                echo "$event_data" | jq -r '.sources // {}' 2>/dev/null
                                ;;
                            "error")
                                local msg=$(echo "$event_data" | jq -r '.message // "Unknown error"')
                                echo -e "${RED}[ERROR]${NC} $msg"
                                ;;
                            *)
                                echo "$event_data"
                                ;;
                        esac
                    fi
                fi
            done

        echo "─────────────────────────────────────────────────────────────"
    else
        print_step "Sending chat request to aggregator..."
        print_info "Endpoint: $AGGREGATOR_URL/chat"

        local response
        response=$(curl -s -w "\n%{http_code}" \
            -X POST "$AGGREGATOR_URL/chat" \
            -H "Content-Type: application/json" \
            -H "Authorization: Bearer $ACCESS_TOKEN" \
            -d "$chat_request")

        local http_code
        http_code=$(echo "$response" | tail -n1)
        local body
        body=$(echo "$response" | sed '$d')

        echo ""
        echo "Response (HTTP $http_code):"
        echo "─────────────────────────────────────────────────────────────"

        if [ "$http_code" = "200" ]; then
            print_success "Chat completed successfully!"
            echo ""

            # Extract and display response
            local answer=$(echo "$body" | jq -r '.response // empty')
            if [ -n "$answer" ]; then
                echo -e "${GREEN}Answer:${NC}"
                echo "$answer"
                echo ""
            fi

            # Display sources
            local sources=$(echo "$body" | jq '.sources // {}')
            if [ "$sources" != "{}" ]; then
                echo -e "${CYAN}Sources:${NC}"
                echo "$sources" | jq '.'
                echo ""
            fi

            # Display metadata
            local metadata=$(echo "$body" | jq '.metadata // {}')
            if [ "$metadata" != "{}" ]; then
                echo -e "${CYAN}Metadata:${NC}"
                echo "$metadata" | jq '.'
            fi

            # Display retrieval info
            local retrieval_info=$(echo "$body" | jq '.retrieval_info // []')
            if [ "$retrieval_info" != "[]" ]; then
                echo ""
                echo -e "${CYAN}Retrieval Info:${NC}"
                echo "$retrieval_info" | jq '.'
            fi
        else
            print_error "Chat request failed (HTTP $http_code)"
            echo "$body" | jq '.' 2>/dev/null || echo "$body"
        fi

        echo "─────────────────────────────────────────────────────────────"
    fi
}

# Step 9: Cleanup / Logout
cleanup() {
    print_header "STEP 9: CLEANUP"

    read -p "Logout and invalidate token? (y/N): " LOGOUT_CHOICE

    if [[ "$LOGOUT_CHOICE" =~ ^[Yy]$ ]]; then
        print_step "Logging out..."
        make_request "POST" "$API_URL/auth/logout" "" "$ACCESS_TOKEN" > /dev/null 2>&1
        print_success "Logged out successfully"
    else
        print_info "Keeping session active"
        print_info "Access token can be reused for: $ACCESS_TOKEN"
    fi
}

# =============================================================================
# MAIN EXECUTION
# =============================================================================

main() {
    print_header "SYFTHUB LLM CHAT WORKFLOW TEST"
    print_info "Base URL: $BASE_URL"
    print_info "API URL: $API_URL"
    print_info "Aggregator URL: $AGGREGATOR_URL"

    check_dependencies

    # Execute workflow steps
    register_user
    login_user
    list_models
    list_data_sources
    select_endpoints
    generate_satellite_tokens
    generate_transaction_tokens
    make_chat_request
    cleanup

    print_header "WORKFLOW COMPLETE"
    print_success "All steps executed successfully!"
}

# Parse arguments and run
parse_args "$@"
main
