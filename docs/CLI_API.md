# CLI API Documentation

## Overview

This document describes how to integrate the `mobiscout` CLI (from the `mobiscout` package) with external tools (IDE plugins, CI/CD, etc.).

## Installation

```bash
pip install -e .
```

## Running as Daemon

### Stdio Mode (Recommended for IDE plugins)

```bash
mobiscout daemon --stdio
```

Communication via stdin/stdout using JSON-RPC 2.0 protocol.

### TCP Mode (For debugging)

```bash
mobiscout daemon --tcp 33333
```

Both transports use the same newline-delimited JSON-RPC 2.0 framing. TCP binds to
`127.0.0.1` and serves one client at a time (for debugging with `nc`); stdio is
the default the IDE plugin uses.

## Protocol

See [PROTOCOL.md](./PROTOCOL.md) for complete JSON-RPC 2.0 specification.

### Quick Example

**Request** (stdin):

```json
{"jsonrpc":"2.0","id":1,"method":"health/check","params":{}}
```

**Response** (stdout):

```json
{"jsonrpc":"2.0","id":1,"result":{"status":"ok","version":"0.5.0","rust_core":true,"uptime_seconds":10}}
```

## Available Methods

Every method below is implemented — this is the live handler set registered in
`framework/cli/daemon_commands.py`. See [PROTOCOL.md](./PROTOCOL.md) for the full
params/results of each.

| Method               | Description                                              |
|----------------------|----------------------------------------------------------|
| `health/check`       | Health check + version info                              |
| `environment/detect` | Detect Appium, Android SDK / ANDROID_HOME, drivers, Xcode |
| `device/list`        | List devices/simulators                                  |
| `device/start`       | Boot an emulator/simulator                               |
| `device/stop`        | Shut down a device                                       |
| `device/listAvds`    | List available Android AVDs                              |
| `backend/list`       | List available automation backends                       |
| `session/start`      | Start an automation session (runs a device-free preflight) |
| `session/stop`       | Stop a session                                           |
| `ui/getTree`         | Get the UI element tree                                  |
| `ui/getScreenshot`   | Capture a screenshot (real device dimensions)            |
| `action/tap`         | Tap element/coordinates                                  |
| `action/swipe`       | Swipe gesture                                            |
| `action/type`        | Type text                                                |
| `selector/generate`  | Ranked, self-healing locator for an element              |
| `flow/getGraph`      | Interaction graph for an app                             |
| `kit/generate`       | Crawl + generate the full test kit (params: `package`, …) |
| `codegen/generate`   | Alias of `kit/generate`                                  |
| `app/install`        | Install a build (.apk/.app) on a device                  |
| `app/uninstall`      | Uninstall the app from a device                          |
| `license/status`     | Active entitlement tier + quotas (open-core is unlimited) |

> There is **no** `logs/stream` / `logs/stop` — earlier drafts of this doc listed
> them; they were never implemented.

## IDE Plugin Integration Guide

### 1. Spawn Daemon Process

```kotlin
// Kotlin example
val process = ProcessBuilder("mobiscout", "daemon", "--stdio")
    .redirectError(ProcessBuilder.Redirect.to(File("daemon.log")))
    .start()

val writer = PrintWriter(process.outputStream.bufferedWriter())
val reader = BufferedReader(InputStreamReader(process.inputStream))
```

```python
# Python example
import subprocess
import json

process = subprocess.Popen(
    ["mobiscout", "daemon", "--stdio"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    bufsize=1
)
```

### 2. Send Requests

```kotlin
fun sendRequest(method: String, params: Map<String, Any>, id: Int): String {
    val request = mapOf(
        "jsonrpc" to "2.0",
        "id" to id,
        "method" to method,
        "params" to params
    )
    val json = gson.toJson(request)
    writer.println(json)
    writer.flush()
    return reader.readLine()
}
```

### 3. Handle Responses

```kotlin
val response = gson.fromJson(responseJson, JsonRPCResponse::class.java)
if (response.error != null) {
    throw Exception("RPC Error: ${response.error.message}")
}
return response.result
```

### 4. Handle Notifications

Notifications don't have an `id` field:

```kotlin
if (message.has("method") && !message.has("id")) {
    // This is a notification
    handleNotification(message.getString("method"), message.getJSONObject("params"))
}
```

### 5. Graceful Shutdown

```kotlin
writer.close()
process.destroy()
process.waitFor(5, TimeUnit.SECONDS)
if (process.isAlive) {
    process.destroyForcibly()
}
```

## Error Handling

### Error Codes

| Code   | Meaning          | Action                                        |
|--------|------------------|-----------------------------------------------|
| -32700 | Parse error      | Check JSON formatting                         |
| -32600 | Invalid Request  | Check JSON-RPC structure                      |
| -32601 | Method not found | Check method name, may not be implemented yet |
| -32602 | Invalid params   | Check parameter types/names                   |
| -32603 | Internal error   | Check daemon logs (stderr)                    |
| -32000 | Device not found | Verify device_id                              |
| -32001 | Session error    | Check session state                           |
| -32002 | Backend error    | Check backend (Appium, etc.)                  |

### Example Error Response

```json
{
  "jsonrpc": "2.0",
  "id": 5,
  "error": {
    "code": -32601,
    "message": "Method not found: invalid/method"
  }
}
```

## Logging

Daemon logs go to **stderr** (not stdout, to avoid interfering with JSON-RPC):

```bash
mobiscout daemon --stdio 2>daemon.log
```

Log format:

```
[2026-01-14 12:30:00] INFO: Starting JSON-RPC server (stdio mode)
[2026-01-14 12:30:01] INFO: Health check requested
```

## Testing

### Manual Testing

Use `echo` and pipe:

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"health/check","params":{}}' | mobiscout daemon --stdio
```

### Interactive Testing

Use `jq` for pretty output:

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"health/check","params":{}}' | \
  mobiscout daemon --stdio 2>/dev/null | \
  jq '.'
```

### Python Test Client

```python
import subprocess
import json

def call_rpc(method, params=None, request_id=1):
    process = subprocess.Popen(
        ["mobiscout", "daemon", "--stdio"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True
    )
    
    request = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": params or {}
    }
    
    stdout, _ = process.communicate(json.dumps(request) + "\n")
    return json.loads(stdout.strip())

# Test health check
response = call_rpc("health/check")
print(response)
```

## Performance

- **Startup time**: <500ms
- **Health check**: <10ms
- **Device list**: <100ms (depends on adb/simctl)
- **Screenshot**: <200ms
- **UI tree**: <300ms

## Security

- Daemon runs with user permissions
- No authentication (local use only)
- No public network exposure — stdio, or TCP bound to `127.0.0.1`
- Future: Add authentication for TCP mode

## Troubleshooting

### Daemon won't start

```bash
# Check if mobiscout is installed
mobiscout --version

# Check Python environment
which python
python --version

# Try running directly
python -m framework.cli.main daemon --stdio
```

### No response from daemon

- Check if process is running
- Verify JSON-RPC format (use validator)
- Check stderr for errors
- Ensure one request per line

### Slow responses

- Check device connection (adb/simctl)
- Verify Appium is running
- Check system resources
- Enable debug logging

## Roadmap

The daemon protocol is complete for the current product: health, environment
detection, device + session lifecycle, UI inspection, input actions, selector +
graph generation, the full crawl→kit (`kit/generate`), app install/uninstall, and
licence status are all live (see the table above). See
[JETBRAINS_PLUGIN_ROADMAP.md](../JETBRAINS_PLUGIN_ROADMAP.md) for plugin-side plans.

## Support

- **Documentation**: [GitHub Wiki](https://github.com/VadimToptunov/Mobiscout/wiki)
- **Issues**: [GitHub Issues](https://github.com/VadimToptunov/Mobiscout/issues)
- **Discussions**: [GitHub Discussions](https://github.com/VadimToptunov/Mobiscout/discussions)

## Examples

### Complete Session Flow

```python
import subprocess
import json
import sys

class MTRClient:
    def __init__(self):
        self.process = subprocess.Popen(
            ["mobiscout", "daemon", "--stdio"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        self.request_id = 0
    
    def call(self, method, params=None):
        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params or {}
        }
        
        self.process.stdin.write(json.dumps(request) + "\n")
        self.process.stdin.flush()
        
        response_line = self.process.stdout.readline()
        response = json.loads(response_line)
        
        if "error" in response:
            raise Exception(f"RPC Error: {response['error']}")
        
        return response.get("result")
    
    def close(self):
        self.process.terminate()
        self.process.wait(timeout=5)

# Usage
client = MTRClient()

try:
    # Health check
    health = client.call("health/check")
    print(f"Health: {health}")
    
    # Any of the methods in the table above, e.g.:
    devices = client.call("device/list", {"platform": "android"})
    # session = client.call("session/start", {...})
    
finally:
    client.close()
```

---

This API is stable and will maintain backward compatibility as new methods are added in future phases.
