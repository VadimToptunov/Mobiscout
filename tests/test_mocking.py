"""
Tests for API Mocking functionality
"""

import pytest

from framework.mocking import APIMocker, MockSession
from framework.mocking.api_mocker import MockMode
from framework.mocking.storage import MockStorage, MockEntry, MockRequest, MockResponse


@pytest.fixture
def temp_storage(tmp_path):
    """Create temporary storage directory"""
    return MockStorage(storage_dir=tmp_path / "mock_data")


@pytest.fixture
def mocker(temp_storage):
    """Create APIMocker instance with temp storage"""
    return APIMocker(storage_dir=temp_storage.storage_dir)


class TestMockStorage:
    """Test mock storage functionality"""

    def test_save_and_load_session(self, temp_storage):
        """Test saving and loading a mock session"""
        session_id = "test-session"

        request = MockRequest(
            method="GET",
            url="https://api.example.com/users",
            headers={"Authorization": "Bearer token"}
        )

        response = MockResponse(
            status_code=200,
            headers={"Content-Type": "application/json"},
            body='{"users": []}'
        )

        mock_entry = MockEntry(
            request=request,
            response=response,
            session_id=session_id
        )

        # Save
        temp_storage.save_session(session_id, [mock_entry])

        # Load
        loaded_mocks = temp_storage.load_session(session_id)

        assert len(loaded_mocks) == 1
        assert loaded_mocks[0].request.method == "GET"
        assert loaded_mocks[0].request.url == "https://api.example.com/users"
        assert loaded_mocks[0].response.status_code == 200

    def test_list_sessions(self, temp_storage):
        """Test listing mock sessions"""
        # Create multiple sessions
        for i in range(3):
            session_id = f"session-{i}"
            mock = MockEntry(
                request=MockRequest(method="GET", url="/test", headers={}),
                response=MockResponse(status_code=200, headers={}, body="{}"),
                session_id=session_id
            )
            temp_storage.save_session(session_id, [mock])

        sessions = temp_storage.list_sessions()

        assert len(sessions) == 3
        assert all("session_id" in s for s in sessions)
        assert all("mock_count" in s for s in sessions)

    def test_delete_session(self, temp_storage):
        """Test deleting a mock session"""
        session_id = "to-delete"
        mock = MockEntry(
            request=MockRequest(method="GET", url="/test", headers={}),
            response=MockResponse(status_code=200, headers={}, body="{}"),
            session_id=session_id
        )

        temp_storage.save_session(session_id, [mock])
        assert temp_storage.delete_session(session_id) is True

        with pytest.raises(FileNotFoundError):
            temp_storage.load_session(session_id)

    def test_export_import_session(self, temp_storage, tmp_path):
        """Test exporting and importing sessions"""
        session_id = "export-test"
        mock = MockEntry(
            request=MockRequest(method="GET", url="/test", headers={}),
            response=MockResponse(status_code=200, headers={}, body="{}"),
            session_id=session_id
        )

        temp_storage.save_session(session_id, [mock])

        export_path = tmp_path / "exported.json"
        temp_storage.export_session(session_id, export_path)

        assert export_path.exists()

        # Import to new session
        imported_id = temp_storage.import_session(export_path)
        assert imported_id == session_id


class TestMockRequest:
    """Test MockRequest matching"""

    def test_exact_match(self):
        """Test exact URL and method matching"""
        request = MockRequest(
            method="GET",
            url="https://api.example.com/users",
            headers={}
        )

        assert request.matches("GET", "https://api.example.com/users") is True
        assert request.matches("POST", "https://api.example.com/users") is False
        assert request.matches("GET", "https://api.example.com/orders") is False

    def test_trailing_slash_normalization(self):
        """Test that trailing slashes are normalized"""
        request = MockRequest(
            method="GET",
            url="https://api.example.com/users/",
            headers={}
        )

        assert request.matches("GET", "https://api.example.com/users") is True
        assert request.matches("GET", "https://api.example.com/users/") is True

    def test_strict_body_matching(self):
        """Test strict mode with body matching"""
        request = MockRequest(
            method="POST",
            url="https://api.example.com/users",
            headers={},
            body='{"name": "John"}'
        )

        # Fuzzy mode - ignores body
        assert request.matches(
            "POST",
            "https://api.example.com/users",
            body='{"name": "Jane"}',
            strict=False
        ) is True

        # Strict mode - requires exact body match
        assert request.matches(
            "POST",
            "https://api.example.com/users",
            body='{"name": "Jane"}',
            strict=True
        ) is False

        assert request.matches(
            "POST",
            "https://api.example.com/users",
            body='{"name": "John"}',
            strict=True
        ) is True


class TestAPIMocker:
    """Test APIMocker functionality"""

    def test_start_recording(self, mocker):
        """Test starting a recording session"""
        session = mocker.start_recording("test-record")

        assert session.session_id == "test-record"
        assert session.mode == MockMode.RECORD
        assert mocker.active_session is session

    def test_record_response(self, mocker):
        """Test recording an API response"""
        mocker.start_recording("test-record")

        mocker.record_response(
            method="GET",
            url="https://api.example.com/users",
            request_headers={"Auth": "token"},
            request_body=None,
            response_status=200,
            response_headers={"Content-Type": "application/json"},
            response_body='{"users": []}',
            latency_ms=100
        )

        stats = mocker.stop()

        assert stats["total_requests"] == 1
        assert stats["mode"] == "record"

    def test_replay_session(self, mocker):
        """Test replaying a recorded session"""
        # Record
        mocker.start_recording("test-replay")
        mocker.record_response(
            method="GET",
            url="https://api.example.com/users",
            request_headers={},
            request_body=None,
            response_status=200,
            response_headers={"Content-Type": "application/json"},
            response_body='{"users": ["Alice", "Bob"]}',
            latency_ms=100
        )
        mocker.stop()

        # Replay
        mocker.start_replay("test-replay")

        response = mocker.intercept_request(
            method="GET",
            url="https://api.example.com/users"
        )

        assert response is not None
        assert response["status_code"] == 200
        assert response["mocked"] is True
        assert "Alice" in response["body"]

    def test_cache_hits_and_misses(self, mocker):
        """Test cache hit/miss tracking"""
        # Record
        mocker.start_recording("test-cache")
        mocker.record_response(
            method="GET",
            url="https://api.example.com/users",
            request_headers={},
            request_body=None,
            response_status=200,
            response_headers={},
            response_body='{}',
            latency_ms=100
        )
        mocker.stop()

        # Replay
        mocker.start_replay("test-cache")

        # Hit
        response1 = mocker.intercept_request("GET", "https://api.example.com/users")
        assert response1 is not None

        # Miss
        response2 = mocker.intercept_request("GET", "https://api.example.com/orders")
        assert response2 is None

        stats = mocker.stop()

        assert stats["cache_hits"] == 1
        assert stats["cache_misses"] == 1
        assert "50.0%" in stats["hit_rate"]

    def test_generate_from_swagger(self, mocker):
        """Test generating mocks from Swagger spec"""
        swagger_spec = {
            "paths": {
                "/users": {
                    "get": {
                        "responses": {
                            "200": {
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "id": {"type": "integer", "example": 1},
                                                    "name": {"type": "string", "example": "John"}
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                },
                "/users/{id}": {
                    "get": {
                        "responses": {
                            "200": {
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "properties": {
                                                "id": {"type": "integer"},
                                                "name": {"type": "string"}
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        count = mocker.generate_from_swagger(swagger_spec, "swagger-test")

        assert count == 2

        # Verify mocks were created
        sessions = mocker.list_sessions()
        assert any(s["session_id"] == "swagger-test" for s in sessions)


class TestMockSession:
    """Test MockSession functionality"""

    def test_session_statistics(self, temp_storage):
        """Test session statistics tracking"""
        session = MockSession("stats-test", MockMode.RECORD, temp_storage)

        session.record_call(
            method="GET",
            url="/test",
            headers={},
            body=None,
            response_status=200,
            response_headers={},
            response_body="{}",
            latency_ms=100
        )

        stats = session.get_stats()

        assert stats["total_requests"] == 1
        assert stats["session_id"] == "stats-test"
        assert stats["mode"] == "record"

    def test_mock_usage_count(self, temp_storage):
        """Test that mock usage is tracked"""
        # Create and save a mock
        mock = MockEntry(
            request=MockRequest(method="GET", url="/test", headers={}),
            response=MockResponse(status_code=200, headers={}, body="{}"),
            session_id="count-test"
        )
        temp_storage.save_session("count-test", [mock])

        # Replay and use multiple times
        session = MockSession("count-test", MockMode.REPLAY, temp_storage)

        for _ in range(3):
            found_mock = session.find_mock("GET", "/test")
            assert found_mock is not None

        assert session.mocks[0].count == 3


def test_integration_record_and_replay(mocker):
    """Integration test: full record and replay cycle"""
    # Step 1: Record a session
    mocker.start_recording("integration-test")

    mocker.record_response(
        method="POST",
        url="https://api.example.com/auth/login",
        request_headers={"Content-Type": "application/json"},
        request_body='{"username": "test", "password": "pass"}',
        response_status=200,
        response_headers={"Content-Type": "application/json"},
        response_body='{"token": "abc123"}',
        latency_ms=150
    )

    mocker.record_response(
        method="GET",
        url="https://api.example.com/users/me",
        request_headers={"Authorization": "Bearer abc123"},
        request_body=None,
        response_status=200,
        response_headers={"Content-Type": "application/json"},
        response_body='{"id": 1, "name": "Test User"}',
        latency_ms=100
    )

    record_stats = mocker.stop()
    assert record_stats["total_requests"] == 2

    # Step 2: Replay the session
    mocker.start_replay("integration-test")

    # Test login
    login_response = mocker.intercept_request(
        method="POST",
        url="https://api.example.com/auth/login",
        headers={"Content-Type": "application/json"},
        body='{"username": "test", "password": "pass"}'
    )

    assert login_response is not None
    assert login_response["status_code"] == 200
    assert "abc123" in login_response["body"]

    # Test user profile
    profile_response = mocker.intercept_request(
        method="GET",
        url="https://api.example.com/users/me",
        headers={"Authorization": "Bearer abc123"}
    )

    assert profile_response is not None
    assert profile_response["status_code"] == 200
    assert "Test User" in profile_response["body"]

    replay_stats = mocker.stop()
    assert replay_stats["cache_hits"] == 2
    assert replay_stats["cache_misses"] == 0
    assert replay_stats["hit_rate"] == "100.0%"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
