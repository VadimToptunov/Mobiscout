# Mobile Test Recorder Protocol Specification

## Overview

The Mobile Test Recorder uses a **JSON-RPC 2.0** protocol for communication between the JetBrains IDE plugin (client)
and the CLI backend (server). This ensures a clean separation of concerns and allows for future extensibility.

## Transport

- **Standard I/O**: Plugin spawns CLI process and communicates via stdin/stdout
- **Alternative**: TCP socket for debugging (port 33333)

## Message Format

All messages follow JSON-RPC 2.0 specification:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "methodName",
  "params": {}
}
```

Response:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {}
}
```

Error:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32603,
    "message": "Internal error",
    "data": {}
  }
}
```

## Error Codes

| Code   | Message          | Description                |
|--------|------------------|----------------------------|
| -32700 | Parse error      | Invalid JSON               |
| -32600 | Invalid request  | Invalid JSON-RPC           |
| -32601 | Method not found | Unknown method             |
| -32602 | Invalid params   | Invalid parameters         |
| -32603 | Internal error   | Server error               |
| -32000 | Device not found | Device/simulator not found |
| -32001 | Session error    | Automation session error   |
| -32002 | Backend error    | Backend adapter error      |

## Core Methods

### 1. Health Check

#### `health/check`

Check if CLI is running and responsive.

**Request**:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "health/check",
  "params": {}
}
```

**Response**:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "status": "ok",
    "version": "0.5.0",
    "rust_core": true,
    "uptime_seconds": 123
  }
}
```

---

### 2. Environment Detection

#### `environment/detect`

Detect installed tools and versions.

**Request**:

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "environment/detect",
  "params": {}
}
```

**Response**:

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "appium": {
      "installed": true,
      "version": "2.4.1",
      "path": "/usr/local/bin/appium",
      "latest_available": "2.6.0"
    },
    "plugins": [
      {
        "name": "images",
        "version": "2.1.0",
        "outdated": false
      },
      {
        "name": "relaxed-caps",
        "version": "1.2.0",
        "outdated": true,
        "latest": "1.5.0"
      }
    ],
    "android": {
      "sdk_path": "/Users/user/Android/sdk",
      "build_tools": "34.0.0",
      "adb_version": "1.0.41"
    },
    "ios": {
      "xcode_path": "/Applications/Xcode.app",
      "xcode_version": "15.2",
      "simctl_available": true
    }
  }
}
```

---

### 3. Device Management

#### `device/list`

List available devices and simulators.

**Request**:

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "device/list",
  "params": {
    "platform": "all"  // "all", "android", "ios"
  }
}
```

**Response**:

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": {
    "devices": [
      {
        "id": "emulator-5554",
        "name": "Pixel_7_API_34",
        "platform": "android",
        "status": "online",
        "api_level": 34,
        "resolution": "1080x2400"
      },
      {
        "id": "123ABC-456DEF",
        "name": "iPhone 15 Pro",
        "platform": "ios",
        "status": "booted",
        "ios_version": "17.2",
        "resolution": "1179x2556"
      }
    ]
  }
}
```

#### `device/start`

Start emulator/simulator.

**Request**:

```json
{
  "jsonrpc": "2.0",
  "id": 4,
  "method": "device/start",
  "params": {
    "device_id": "Pixel_7_API_34",
    "platform": "android"
  }
}
```

**Response**:

```json
{
  "jsonrpc": "2.0",
  "id": 4,
  "result": {
    "status": "starting",
    "device_id": "emulator-5554",
    "estimated_seconds": 30
  }
}
```

#### `device/stop`

Stop emulator/simulator.

**Request**:

```json
{
  "jsonrpc": "2.0",
  "id": 5,
  "method": "device/stop",
  "params": {
    "device_id": "emulator-5554"
  }
}
```

**Response**:

```json
{
  "jsonrpc": "2.0",
  "id": 5,
  "result": {
    "status": "stopped"
  }
}
```

---

### 4. Session Management

#### `session/start`

Start automation session.

**Request**:

```json
{
  "jsonrpc": "2.0",
  "id": 6,
  "method": "session/start",
  "params": {
    "backend": "appium",  // "appium", "espresso", "xctest"
    "device_id": "emulator-5554",
    "app_path": "/path/to/app.apk",
    "capabilities": {
      "platformName": "Android",
      "automationName": "UiAutomator2",
      "noReset": true
    }
  }
}
```

**Response**:

```json
{
  "jsonrpc": "2.0",
  "id": 6,
  "result": {
    "session_id": "abc123-def456",
    "backend": "appium",
    "capabilities": {
      "platformName": "Android",
      "platformVersion": "14",
      "deviceName": "emulator-5554"
    }
  }
}
```

#### `session/stop`

Stop automation session.

**Request**:

```json
{
  "jsonrpc": "2.0",
  "id": 7,
  "method": "session/stop",
  "params": {
    "session_id": "abc123-def456"
  }
}
```

**Response**:

```json
{
  "jsonrpc": "2.0",
  "id": 7,
  "result": {
    "status": "stopped"
  }
}
```

---

### 5. UI Inspection

#### `ui/getTree`

Get UI element tree (page source).

**Request**:

```json
{
  "jsonrpc": "2.0",
  "id": 8,
  "method": "ui/getTree",
  "params": {
    "session_id": "abc123-def456"
  }
}
```

**Response**:

```json
{
  "jsonrpc": "2.0",
  "id": 8,
  "result": {
    "format": "xml",  // or "json"
    "source": "<hierarchy>...</hierarchy>",
    "elements": [
      {
        "id": "elem_001",
        "class": "android.widget.Button",
        "text": "Login",
        "resource_id": "com.example:id/login_button",
        "bounds": [100, 200, 300, 280],
        "clickable": true,
        "enabled": true
      }
    ]
  }
}
```

#### `ui/getScreenshot`

Get device screenshot.

**Request**:

```json
{
  "jsonrpc": "2.0",
  "id": 9,
  "method": "ui/getScreenshot",
  "params": {
    "session_id": "abc123-def456",
    "format": "png"  // "png", "jpg"
  }
}
```

**Response**:

```json
{
  "jsonrpc": "2.0",
  "id": 9,
  "result": {
    "format": "png",
    "data": "base64_encoded_image_data...",
    "width": 1080,
    "height": 2400
  }
}
```

---

### 6. Actions

#### `action/tap`

Tap on element or coordinates.

**Request**:

```json
{
  "jsonrpc": "2.0",
  "id": 10,
  "method": "action/tap",
  "params": {
    "session_id": "abc123-def456",
    "element_id": "elem_001",  // or use x, y
    "x": 200,  // optional if element_id provided
    "y": 240
  }
}
```

**Response**:

```json
{
  "jsonrpc": "2.0",
  "id": 10,
  "result": {
    "status": "success",
    "element_id": "elem_001"
  }
}
```

#### `action/swipe`

Swipe gesture.

**Request**:

```json
{
  "jsonrpc": "2.0",
  "id": 11,
  "method": "action/swipe",
  "params": {
    "session_id": "abc123-def456",
    "start_x": 500,
    "start_y": 1000,
    "end_x": 500,
    "end_y": 300,
    "duration_ms": 300
  }
}
```

**Response**:

```json
{
  "jsonrpc": "2.0",
  "id": 11,
  "result": {
    "status": "success"
  }
}
```

#### `action/type`

Type text into element.

**Request**:

```json
{
  "jsonrpc": "2.0",
  "id": 12,
  "method": "action/type",
  "params": {
    "session_id": "abc123-def456",
    "element_id": "elem_002",
    "text": "test@example.com"
  }
}
```

**Response**:

```json
{
  "jsonrpc": "2.0",
  "id": 12,
  "result": {
    "status": "success"
  }
}
```

---

### 7. Logs

#### `logs/stream`

Start streaming device logs.

**Request**:

```json
{
  "jsonrpc": "2.0",
  "id": 13,
  "method": "logs/stream",
  "params": {
    "device_id": "emulator-5554",
    "filter": "MyApp",  // optional
    "level": "info"  // "verbose", "debug", "info", "warn", "error"
  }
}
```

**Response** (notification stream):

```json
{
  "jsonrpc": "2.0",
  "method": "logs/message",
  "params": {
    "timestamp": "2026-01-13T10:30:00Z",
    "level": "info",
    "tag": "ActivityManager",
    "message": "START u0 {act=android.intent.action.MAIN}"
  }
}
```

#### `logs/stop`

Stop log streaming.

**Request**:

```json
{
  "jsonrpc": "2.0",
  "id": 14,
  "method": "logs/stop",
  "params": {
    "device_id": "emulator-5554"
  }
}
```

**Response**:

```json
{
  "jsonrpc": "2.0",
  "id": 14,
  "result": {
    "status": "stopped"
  }
}
```

---

### 8. Selector Engine

#### `selector/generate`

Generate optimal selector for element.

**Request**:

```json
{
  "jsonrpc": "2.0",
  "id": 15,
  "method": "selector/generate",
  "params": {
    "session_id": "abc123-def456",
    "element_id": "elem_001",
    "strategy": "smart"  // "smart", "simple", "robust"
  }
}
```

**Response**:

```json
{
  "jsonrpc": "2.0",
  "id": 15,
  "result": {
    "primary": {
      "strategy": "accessibility_id",
      "value": "login_button",
      "stability_score": 95
    },
    "fallbacks": [
      {
        "strategy": "id",
        "value": "com.example:id/login_button",
        "stability_score": 90
      },
      {
        "strategy": "xpath",
        "value": "//android.widget.Button[@text='Login']",
        "stability_score": 60
      }
    ]
  }
}
```

---

### 9. Flow Analysis

#### `flow/getGraph`

Get flow graph for recorded session.

**Request**:

```json
{
  "jsonrpc": "2.0",
  "id": 16,
  "method": "flow/getGraph",
  "params": {
    "session_id": "abc123-def456"
  }
}
```

**Response**:

```json
{
  "jsonrpc": "2.0",
  "id": 16,
  "result": {
    "nodes": [
      {
        "id": "screen_login",
        "type": "screen",
        "name": "LoginScreen",
        "elements": ["email_input", "password_input", "login_button"]
      },
      {
        "id": "screen_home",
        "type": "screen",
        "name": "HomeScreen",
        "elements": ["profile_button", "settings_button"]
      }
    ],
    "edges": [
      {
        "from": "screen_login",
        "to": "screen_home",
        "action": "tap",
        "element": "login_button",
        "condition": "authenticated"
      }
    ]
  }
}
```

---

### 10. Code Generation

#### `codegen/generate`

Generate test code from session.

**Request**:

```json
{
  "jsonrpc": "2.0",
  "id": 17,
  "method": "codegen/generate",
  "params": {
    "session_id": "abc123-def456",
    "language": "python",  // "python", "java", "kotlin", "javascript", "go", "ruby"
    "framework": "pytest",  // language-specific: "pytest", "unittest", "junit", "testng", etc.
    "pattern": "pom"  // "pom" (Page Object Model), "linear", "bdd"
  }
}
```

**Response**:

```json
{
  "jsonrpc": "2.0",
  "id": 17,
  "result": {
    "files": [
      {
        "path": "tests/test_login.py",
        "content": "# Generated test code..."
      },
      {
        "path": "page_objects/login_page.py",
        "content": "# Page object code..."
      }
    ]
  }
}
```

---

## Notifications (Server → Client)

The server can send notifications (no `id` field) to the client:

### `notification/event`

Generic event notification.

```json
{
  "jsonrpc": "2.0",
  "method": "notification/event",
  "params": {
    "type": "device_connected",
    "device_id": "emulator-5554",
    "timestamp": "2026-01-13T10:30:00Z"
  }
}
```

### `notification/progress`

Progress update for long-running operations.

```json
{
  "jsonrpc": "2.0",
  "method": "notification/progress",
  "params": {
    "operation": "session/start",
    "request_id": 6,
    "progress": 50,
    "message": "Installing app..."
  }
}
```

---

## Implementation Notes

### Server (CLI)

- Run in daemon mode: `mtr daemon --stdio` or `mtr daemon --tcp 33333`
- Parse JSON-RPC from stdin, write to stdout
- Use structured logging to stderr (won't interfere with protocol)
- Maintain session state in memory

### Client (Plugin)

- Spawn CLI process: `mtr daemon --stdio`
- Send requests via stdin
- Parse responses from stdout
- Handle notifications asynchronously
- Reconnect on error

### Future Extensions

- **Batch requests**: Multiple methods in one request
- **Streaming**: For video/logs
- **Compression**: gzip for large payloads (screenshots)
- **Authentication**: For multi-user scenarios (future)

---

## Example Session Flow

1. **Plugin starts CLI**:
   ```bash
   mtr daemon --stdio
   ```

2. **Health check**:
   ```json
   {"jsonrpc":"2.0","id":1,"method":"health/check","params":{}}
   ```

3. **Detect environment**:
   ```json
   {"jsonrpc":"2.0","id":2,"method":"environment/detect","params":{}}
   ```

4. **List devices**:
   ```json
   {"jsonrpc":"2.0","id":3,"method":"device/list","params":{"platform":"all"}}
   ```

5. **Start session**:
   ```json
   {"jsonrpc":"2.0","id":4,"method":"session/start","params":{"backend":"appium","device_id":"emulator-5554","app_path":"/path/to/app.apk","capabilities":{}}}
   ```

6. **Get UI tree**:
   ```json
   {"jsonrpc":"2.0","id":5,"method":"ui/getTree","params":{"session_id":"abc123"}}
   ```

7. **Get screenshot**:
   ```json
   {"jsonrpc":"2.0","id":6,"method":"ui/getScreenshot","params":{"session_id":"abc123"}}
   ```

8. **Tap element**:
   ```json
   {"jsonrpc":"2.0","id":7,"method":"action/tap","params":{"session_id":"abc123","x":200,"y":240}}
   ```

9. **Stop session**:
   ```json
   {"jsonrpc":"2.0","id":8,"method":"session/stop","params":{"session_id":"abc123"}}
   ```

---

## Testing

Use `mtr protocol-test` command to test protocol implementation:

```bash
# Start interactive REPL
mtr protocol-test --interactive

# Run test suite
mtr protocol-test --suite basic

# Test specific method
mtr protocol-test --method health/check
```

---

This protocol provides a solid foundation for Phase 1-11 of the roadmap and can be extended as needed without breaking
changes.
