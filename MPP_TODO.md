
### 5. Propagate MPP payment context through NATS tunnel path

**Files**: `components/aggregator/src/aggregator/services/generation.py`, `retrieval.py`

**Current state**: The NATS tunneling code path still forwards only the legacy `transaction_token` and drops `user_token`/`syfthub_url`. The MPP 402 handler lives in the HTTP clients only, so paid requests over NATS tunnels have no way to obtain an `X-Payment` credential.

**Fix**: Either implement MPP payment handling in the NATS transport layer, or fall back to HTTP for paid endpoints.

### 6. PAT-authenticated calls can't get user_token for MPP

**File**: `sdk/typescript/src/resources/auth.ts`

**Current state**: When the SDK is initialized with `apiToken` (Personal Access Token), `HTTPClient.getTokens()` returns `null`, so `getAccessToken()` returns `null`. The chat flow omits `user_token`, and paid queries through the aggregator fail because the Hub `/pay` callback can't authenticate the user.

**Fix**: `getAccessToken()` should return the PAT when JWT tokens are not available. Or the chat flow should pass the PAT directly as `user_token`.
