"""
Mock Storage Module

Handles persistent storage of recorded API mocks.
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any


@dataclass
class MockRequest:
    """Recorded API request"""

    method: str
    url: str
    headers: Dict[str, str]
    body: Optional[str] = None
    query_params: Dict[str, str] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def matches(self, method: str, url: str, body: Optional[str] = None, strict: bool = False) -> bool:
        """Check if this mock matches the given request"""
        # Basic match
        if self.method != method:
            return False

        # URL matching (normalize trailing slashes)
        if self.url.rstrip("/") != url.rstrip("/"):
            return False

        # Strict mode: also match body
        if strict and body is not None:
            return self.body == body

        return True


@dataclass
class MockResponse:
    """Recorded API response"""

    status_code: int
    headers: Dict[str, str]
    body: str
    latency_ms: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class MockEntry:
    """Complete mock entry (request + response)"""

    request: MockRequest
    response: MockResponse
    session_id: str
    count: int = 0  # How many times this mock has been used

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "request": asdict(self.request),
            "response": asdict(self.response),
            "session_id": self.session_id,
            "count": self.count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MockEntry":
        """Create from dictionary"""
        return cls(
            request=MockRequest(**data["request"]),
            response=MockResponse(**data["response"]),
            session_id=data["session_id"],
            count=data.get("count", 0),
        )


class MockStorage:
    """Persistent storage for API mocks"""

    def __init__(self, storage_dir: Path = Path("mock_data")):
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def save_session(self, session_id: str, mocks: List[MockEntry]) -> None:
        """Save a mock session to disk"""
        session_file = self.storage_dir / f"{session_id}.json"

        data = {
            "session_id": session_id,
            "created_at": datetime.now().isoformat(),
            "mock_count": len(mocks),
            "mocks": [mock.to_dict() for mock in mocks],
        }

        with open(session_file, "w") as f:
            json.dump(data, f, indent=2)

    def load_session(self, session_id: str) -> List[MockEntry]:
        """Load a mock session from disk"""
        session_file = self.storage_dir / f"{session_id}.json"

        if not session_file.exists():
            raise FileNotFoundError(f"Mock session '{session_id}' not found")

        with open(session_file, "r") as f:
            data = json.load(f)

        return [MockEntry.from_dict(mock_data) for mock_data in data["mocks"]]

    def list_sessions(self) -> List[Dict[str, Any]]:
        """List all available mock sessions"""
        sessions = []

        for session_file in self.storage_dir.glob("*.json"):
            try:
                with open(session_file, "r") as f:
                    data = json.load(f)
                    sessions.append(
                        {
                            "session_id": data["session_id"],
                            "created_at": data.get("created_at", "unknown"),
                            "mock_count": data.get("mock_count", 0),
                        }
                    )
            except (OSError, json.JSONDecodeError, KeyError):
                continue

        return sorted(sessions, key=lambda x: x["created_at"], reverse=True)

    def delete_session(self, session_id: str) -> bool:
        """Delete a mock session"""
        session_file = self.storage_dir / f"{session_id}.json"

        if session_file.exists():
            session_file.unlink()
            return True

        return False

    def export_session(self, session_id: str, output_path: Path) -> None:
        """Export session to a specific location"""
        session_file = self.storage_dir / f"{session_id}.json"

        if not session_file.exists():
            raise FileNotFoundError(f"Mock session '{session_id}' not found")

        import shutil

        shutil.copy(session_file, output_path)

    def import_session(self, input_path: Path) -> str:
        """Import a session from a file"""
        with open(input_path, "r") as f:
            data = json.load(f)

        session_id = data["session_id"]
        session_file = self.storage_dir / f"{session_id}.json"

        import shutil

        shutil.copy(input_path, session_file)

        return session_id
