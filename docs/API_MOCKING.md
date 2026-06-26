# API Mocking & Replay

Record and replay HTTP API responses for faster, more reliable mobile testing.

## Overview

API Mocking allows you to:

- **Record** real API responses during test execution
- **Replay** recorded responses without hitting real servers
- **Generate** mocks from Swagger/OpenAPI specifications
- **Speed up** test execution by 10-100x
- **Test offline** without network dependencies
- **Isolate** tests from backend changes

## Quick Start

### 1. Record API Calls

Record all API calls during a test session:

```bash
observe mock record my-session --appium-server http://localhost:4723
```

This creates a recording session that captures all HTTP traffic.

### 2. Replay Recorded Calls

Replay the recorded session:

```bash
observe mock replay my-session
```

Your tests will now use mocked responses instead of hitting real APIs!

### 3. View Statistics

Check mock session stats:

```bash
observe mock list
observe mock inspect my-session
```

## Programmatic API

### Recording

```python
from framework.mocking import APIMocker

mocker = APIMocker()

# Start recording
session = mocker.start_recording("my-session")

# ... run your tests ...

# Your test code automatically records responses
mocker.record_response(
    method="GET",
    url="https://api.example.com/users",
    request_headers={"Authorization": "Bearer token"},
    request_body=None,
    response_status=200,
    response_headers={"Content-Type": "application/json"},
    response_body='{"users": [{"id": 1, "name": "John"}]}',
    latency_ms=150.5
)

# Stop and save
stats = mocker.stop()
print(f"Recorded {stats['total_requests']} requests")
```

### Replay

```python
from framework.mocking import APIMocker

mocker = APIMocker()

# Start replay
session = mocker.start_replay("my-session", strict=False)

# Intercept requests
response = mocker.intercept_request(
    method="GET",
    url="https://api.example.com/users",
    headers={"Authorization": "Bearer token"}
)

if response:
    print(f"Mocked! Status: {response['status_code']}")
    print(f"Body: {response['body']}")
else:
    print("No mock found, make real request")

# Stop
stats = mocker.stop()
print(f"Hit rate: {stats['hit_rate']}")
```

## Features

### 1. Flexible Matching

**Fuzzy matching** (default):

- Matches only method and URL
- Ignores request body differences
- Good for most use cases

```bash
observe mock replay my-session --fuzzy
```

**Strict matching**:

- Matches method, URL, AND request body
- Useful for POST/PUT requests with different payloads

```bash
observe mock replay my-session --strict
```

### 2. Swagger/OpenAPI Import

Generate mocks from API specifications:

```bash
observe mock from-swagger api-spec.yaml my-session
```

```python
mocker = APIMocker()
count = mocker.generate_from_swagger(swagger_spec, "my-session")
print(f"Generated {count} mocks")
```

Example Swagger:

```yaml
openapi: 3.0.0
paths:
  /users:
    get:
      responses:
        200:
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object
                  properties:
                    id:
                      type: integer
                      example: 1
                    name:
                      type: string
                      example: "John Doe"
```

### 3. URL Rewriting

Update base URLs in recorded mocks:

```bash
observe mock rewrite-urls my-session \
  https://staging.api.com \
  https://prod.api.com
```

Useful when moving between environments.

### 4. Import/Export

Share mocks between team members:

```bash
# Export
observe mock export my-session -o my-session.json

# Import
observe mock import my-session.json
```

### 5. Mock Statistics

Track mock usage and performance:

```python
stats = mocker.stop()
# {
#   "session_id": "my-session",
#   "mode": "replay",
#   "total_requests": 50,
#   "cache_hits": 48,
#   "cache_misses": 2,
#   "hit_rate": "96.0%",
#   "latency_saved_ms": "7523.5"
# }
```

## Use Cases

### 1. Fast Test Execution

**Without mocking:**

```
Test suite: 10 tests × 5 API calls × 150ms = 7.5 seconds
```

**With mocking:**

```
Test suite: 10 tests × 5 API calls × 1ms = 50ms (150x faster!)
```

### 2. Offline Testing

Test your app without network access:

- No internet required
- No backend dependencies
- Works on airplanes, trains, etc.

### 3. CI/CD Isolation

Prevent flaky tests from backend issues:

- Backend is down? Tests still pass
- API changes? Tests still work
- Network issues? No problem

### 4. Backend Not Ready

Start testing before the backend is complete:

- Generate mocks from Swagger spec
- Test UI/UX independently
- Validate integration points early

### 5. Rate Limiting

Avoid hitting API rate limits during development:

- Record once, replay unlimited times
- No more "429 Too Many Requests"
- Faster iteration cycles

## Architecture

### Storage Format

Mocks are stored as JSON files:

```json
{
  "session_id": "my-session",
  "created_at": "2026-01-12T10:30:00",
  "mock_count": 2,
  "mocks": [
    {
      "request": {
        "method": "GET",
        "url": "https://api.example.com/users",
        "headers": {"Authorization": "Bearer token"},
        "body": null,
        "timestamp": "2026-01-12T10:30:01"
      },
      "response": {
        "status_code": 200,
        "headers": {"Content-Type": "application/json"},
        "body": "{\"users\": [...]}",
        "latency_ms": 150.5,
        "timestamp": "2026-01-12T10:30:01"
      },
      "session_id": "my-session",
      "count": 3
    }
  ]
}
```

### Mock Matching Algorithm

1. **Method match**: Request method must match exactly
2. **URL match**: URLs must match (trailing slashes normalized)
3. **Body match** (strict mode only): Request bodies must match exactly

### Latency Simulation

Mocks can simulate original API latency (scaled 10x faster by default):

```python
# Original request took 100ms
# Mock replays in 10ms (10x faster)
# Configurable via latency_ms field
```

## Best Practices

### 1. Session Naming

Use descriptive session names:

```bash
# Good
observe mock record user-login-flow
observe mock record checkout-success
observe mock record error-scenarios

# Bad
observe mock record test1
observe mock record temp
```

### 2. Update Regularly

Re-record mocks when APIs change:

```bash
# Re-record monthly or after API updates
observe mock record my-session  # Overwrites existing
```

### 3. Version Control

Commit mocks to Git for team sharing:

```bash
git add mock_data/
git commit -m "Add API mocks for user flow"
```

### 4. Hybrid Testing

Combine mocking with real requests:

- **Development**: Use mocks (fast iteration)
- **CI/CD**: Use mocks (reliable, fast)
- **Nightly tests**: Use real APIs (catch regressions)

### 5. Sensitive Data

Filter sensitive data before recording:

```python
# Don't record
- Passwords
- API keys
- Personal information
- Credit card numbers

# Consider scrubbing recorded data
def scrub_response(response_body):
    data = json.loads(response_body)
    if 'password' in data:
        data['password'] = '***'
    return json.dumps(data)
```

## CLI Reference

### Commands

| Command                                         | Description               |
|-------------------------------------------------|---------------------------|
| `observe mock record <session>`                 | Start recording API calls |
| `observe mock replay <session>`                 | Replay recorded calls     |
| `observe mock list`                             | List all sessions         |
| `observe mock inspect <session>`                | View session details      |
| `observe mock delete <session>`                 | Delete a session          |
| `observe mock export <session> -o file.json`    | Export session            |
| `observe mock import file.json`                 | Import session            |
| `observe mock from-swagger spec.yaml <session>` | Generate from Swagger     |
| `observe mock rewrite-urls <session> old new`   | Rewrite URLs              |

### Options

| Option                  | Description                       |
|-------------------------|-----------------------------------|
| `--strict/--fuzzy`      | Strict or fuzzy matching (replay) |
| `--port <port>`         | Mock server port (default: 8888)  |
| `--appium-server <url>` | Appium server to proxy            |
| `--output/-o <path>`    | Output file path (export)         |

## Roadmap

### Phase 1 (Current)

- ✅ Core recording/replay
- ✅ Storage system
- ✅ CLI commands
- ✅ Swagger import
- ✅ URL rewriting

### Phase 2 (Future)

- 🔄 HTTP proxy server
- 🔄 Appium integration
- 🔄 Charles Proxy import
- 🔄 HAR file support
- 🔄 Request/response filtering

### Phase 3 (Future)

- 📋 GraphQL support
- 📋 WebSocket mocking
- 📋 gRPC support
- 📋 Mock variations (A/B testing)
- 📋 Chaos testing (random failures)

## Examples

### Example 1: Login Flow

```python
from framework.mocking import APIMocker

mocker = APIMocker()
session = mocker.start_recording("login-flow")

# Simulate login
mocker.record_response(
    method="POST",
    url="https://api.example.com/auth/login",
    request_headers={"Content-Type": "application/json"},
    request_body='{"username": "test", "password": "***"}',
    response_status=200,
    response_headers={"Content-Type": "application/json"},
    response_body='{"token": "abc123", "user_id": 42}',
    latency_ms=200
)

# Simulate profile fetch
mocker.record_response(
    method="GET",
    url="https://api.example.com/users/42",
    request_headers={"Authorization": "Bearer abc123"},
    request_body=None,
    response_status=200,
    response_headers={"Content-Type": "application/json"},
    response_body='{"id": 42, "name": "Test User"}',
    latency_ms=100
)

stats = mocker.stop()
print(f"Recorded {stats['total_requests']} API calls")
```

### Example 2: Error Scenarios

```python
# Record error responses for testing error handling
mocker.record_response(
    method="POST",
    url="https://api.example.com/orders",
    request_body='{"item": "invalid"}',
    response_status=400,
    response_body='{"error": "Invalid item ID"}',
    latency_ms=50
)

mocker.record_response(
    method="GET",
    url="https://api.example.com/users/999",
    response_status=404,
    response_body='{"error": "User not found"}',
    latency_ms=80
)
```

## Troubleshooting

### Mock not found during replay

**Problem**: `Mock miss: GET /users`

**Solution**:

1. Check URL matches exactly (including trailing slash)
2. Use `--fuzzy` mode if request bodies differ
3. Verify session has recorded mocks: `observe mock inspect my-session`

### Slow replay

**Problem**: Replay is slow despite mocking

**Solution**:

1. Check latency simulation settings
2. Verify mocks are being hit: check `cache_hits` in stats
3. Reduce latency in mock files if needed

### Missing responses

**Problem**: Some requests not mocked

**Solution**:

1. Record a complete test session
2. Check for dynamic URLs (timestamps, IDs)
3. Use URL rewriting if base URL changed

## Support

- **Documentation**: See README.md
- **Issues**: https://github.com/VadimToptunov/mobile_test_recorder/issues
- **Examples**: See `tests/test_mocking.py`
