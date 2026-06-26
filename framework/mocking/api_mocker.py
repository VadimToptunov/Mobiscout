"""
API Mocker - Record and Replay HTTP API calls

Provides transparent recording and replay of HTTP API responses
for faster, more reliable mobile testing.
"""

import logging
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Callable, Any

from framework.mocking.storage import MockStorage, MockEntry, MockRequest, MockResponse

logger = logging.getLogger(__name__)


class MockMode(Enum):
    """Mock operation mode"""

    RECORD = "record"  # Record all API calls
    REPLAY = "replay"  # Replay from recorded mocks
    PASSTHROUGH = "passthrough"  # Pass through without recording


@dataclass
class MockStats:
    """Statistics for mock session"""

    total_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    total_latency_saved_ms: float = 0.0

    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate"""
        if self.total_requests == 0:
            return 0.0
        return (self.cache_hits / self.total_requests) * 100


class MockSession:
    """Active mock recording/replay session"""

    def __init__(self, session_id: str, mode: MockMode, storage: MockStorage, strict: bool = False):
        self.session_id = session_id
        self.mode = mode
        self.storage = storage
        self.strict = strict
        self.mocks: List[MockEntry] = []
        self.stats = MockStats()

        # Load existing mocks if in replay mode
        if mode == MockMode.REPLAY:
            try:
                self.mocks = storage.load_session(session_id)
                logger.info(f"Loaded {len(self.mocks)} mocks for session '{session_id}'")
            except FileNotFoundError:
                logger.warning(f"No mocks found for session '{session_id}', will record new ones")
                self.mode = MockMode.RECORD

    def record_call(
            self,
            method: str,
            url: str,
            headers: Dict[str, str],
            body: Optional[str],
            response_status: int,
            response_headers: Dict[str, str],
            response_body: str,
            latency_ms: float,
    ) -> None:
        """Record an API call"""
        if self.mode != MockMode.RECORD:
            return

        request = MockRequest(method=method, url=url, headers=headers, body=body)

        response = MockResponse(
            status_code=response_status, headers=response_headers, body=response_body, latency_ms=latency_ms
        )

        mock_entry = MockEntry(request=request, response=response, session_id=self.session_id)

        self.mocks.append(mock_entry)
        self.stats.total_requests += 1

        logger.debug(f"Recorded: {method} {url} -> {response_status}")

    def find_mock(self, method: str, url: str, body: Optional[str] = None) -> Optional[MockEntry]:
        """Find a matching mock for replay"""
        if self.mode != MockMode.REPLAY:
            return None

        self.stats.total_requests += 1

        for mock in self.mocks:
            if mock.request.matches(method, url, body, strict=self.strict):
                mock.count += 1
                self.stats.cache_hits += 1
                self.stats.total_latency_saved_ms += mock.response.latency_ms
                logger.debug(f"Mock hit: {method} {url} (used {mock.count} times)")
                return mock

        self.stats.cache_misses += 1
        logger.warning(f"Mock miss: {method} {url}")
        return None

    def save(self) -> None:
        """Save recorded mocks to storage"""
        if self.mode == MockMode.RECORD and self.mocks:
            self.storage.save_session(self.session_id, self.mocks)
            logger.info(f"Saved {len(self.mocks)} mocks for session '{self.session_id}'")

    def get_stats(self) -> Dict[str, Any]:
        """Get session statistics"""
        return {
            "session_id": self.session_id,
            "mode": self.mode.value,
            "total_requests": self.stats.total_requests,
            "cache_hits": self.stats.cache_hits,
            "cache_misses": self.stats.cache_misses,
            "hit_rate": f"{self.stats.hit_rate:.1f}%",
            "latency_saved_ms": f"{self.stats.total_latency_saved_ms:.1f}",
            "mocks_recorded": len(self.mocks),
        }


class APIMocker:
    """
    Main API Mocker class

    Provides record and replay functionality for HTTP API calls.
    """

    def __init__(self, storage_dir: Path = Path("mock_data")):
        self.storage = MockStorage(storage_dir)
        self.active_session: Optional[MockSession] = None
        self._intercept_handlers: List[Callable] = []

    def start_recording(self, session_id: str) -> MockSession:
        """Start recording API calls"""
        self.active_session = MockSession(session_id, MockMode.RECORD, self.storage)
        logger.info(f"Started recording session '{session_id}'")
        return self.active_session

    def start_replay(self, session_id: str, strict: bool = False) -> MockSession:
        """Start replaying recorded API calls"""
        self.active_session = MockSession(session_id, MockMode.REPLAY, self.storage, strict=strict)
        logger.info(f"Started replay session '{session_id}' (strict={strict})")
        return self.active_session

    def stop(self) -> Optional[Dict[str, Any]]:
        """Stop current session and return statistics"""
        if not self.active_session:
            return None

        stats = self.active_session.get_stats()
        self.active_session.save()
        self.active_session = None

        logger.info("Stopped mock session")
        return stats

    def intercept_request(
            self,
            method: str,
            url: str,
            headers: Optional[Dict[str, str]] = None,
            body: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Intercept an HTTP request

        Returns mocked response if available, None otherwise
        """
        if not self.active_session:
            return None

        headers = headers or {}

        # Try to find mock in replay mode
        if self.active_session.mode == MockMode.REPLAY:
            mock = self.active_session.find_mock(method, url, body)
            if mock:
                # Simulate latency (optional, scaled down)
                if mock.response.latency_ms > 0:
                    time.sleep(mock.response.latency_ms / 1000 / 10)  # 10x faster

                return {
                    "status_code": mock.response.status_code,
                    "headers": mock.response.headers,
                    "body": mock.response.body,
                    "mocked": True,
                }

        return None

    def record_response(
            self,
            method: str,
            url: str,
            request_headers: Dict[str, str],
            request_body: Optional[str],
            response_status: int,
            response_headers: Dict[str, str],
            response_body: str,
            latency_ms: float,
    ) -> None:
        """Record an API response"""
        if not self.active_session:
            return

        self.active_session.record_call(
            method=method,
            url=url,
            headers=request_headers,
            body=request_body,
            response_status=response_status,
            response_headers=response_headers,
            response_body=response_body,
            latency_ms=latency_ms,
        )

    def list_sessions(self) -> List[Dict[str, Any]]:
        """List all available mock sessions"""
        return self.storage.list_sessions()

    def delete_session(self, session_id: str) -> bool:
        """Delete a mock session"""
        return self.storage.delete_session(session_id)

    def export_session(self, session_id: str, output_path: Path) -> None:
        """Export a mock session"""
        self.storage.export_session(session_id, output_path)

    def import_session(self, input_path: Path) -> str:
        """Import a mock session"""
        return self.storage.import_session(input_path)

    def generate_from_swagger(self, swagger_spec: Dict[str, Any], session_id: str) -> int:
        """
        Generate mocks from Swagger/OpenAPI specification

        Returns number of mocks generated
        """
        mocks: List[MockEntry] = []

        # Extract paths
        paths = swagger_spec.get("paths", {})

        for path, methods in paths.items():
            for method, spec in methods.items():
                if method.upper() not in ["GET", "POST", "PUT", "DELETE", "PATCH"]:
                    continue

                # Generate sample request
                request = MockRequest(
                    method=method.upper(),
                    url=path,
                    headers={"Content-Type": "application/json"},
                    body=self._generate_sample_request_body(spec),
                )

                # Generate sample response
                responses = spec.get("responses", {})
                success_response = responses.get("200", responses.get("201", {}))

                response = MockResponse(
                    status_code=int(list(responses.keys())[0]) if responses else 200,
                    headers={"Content-Type": "application/json"},
                    body=self._generate_sample_response_body(success_response),
                    latency_ms=100.0,  # Default latency
                )

                mock_entry = MockEntry(request=request, response=response, session_id=session_id)
                mocks.append(mock_entry)

        # Save generated mocks
        self.storage.save_session(session_id, mocks)
        logger.info(f"Generated {len(mocks)} mocks from Swagger spec")

        return len(mocks)

    def _generate_sample_request_body(self, spec: Dict[str, Any]) -> Optional[str]:
        """Generate sample request body from spec"""
        request_body = spec.get("requestBody", {})
        if not request_body:
            return None

        content = request_body.get("content", {})
        json_schema = content.get("application/json", {}).get("schema", {})

        if json_schema:
            import json

            return json.dumps(self._generate_from_schema(json_schema))

        return None

    def _generate_sample_response_body(self, response_spec: Dict[str, Any]) -> str:
        """Generate sample response body from spec"""
        content = response_spec.get("content", {})
        json_schema = content.get("application/json", {}).get("schema", {})

        if json_schema:
            import json

            return json.dumps(self._generate_from_schema(json_schema))

        return "{}"

    def _generate_from_schema(self, schema: Dict[str, Any]) -> Any:
        """Generate sample data from JSON schema"""
        schema_type = schema.get("type", "object")

        if schema_type == "object":
            result = {}
            properties = schema.get("properties", {})
            for prop_name, prop_schema in properties.items():
                result[prop_name] = self._generate_from_schema(prop_schema)
            return result

        elif schema_type == "array":
            items = schema.get("items", {})
            return [self._generate_from_schema(items)]

        elif schema_type == "string":
            return schema.get("example", "sample_string")

        elif schema_type == "integer":
            return schema.get("example", 123)

        elif schema_type == "number":
            return schema.get("example", 123.45)

        elif schema_type == "boolean":
            return schema.get("example", True)

        return None
