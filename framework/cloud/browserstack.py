"""
BrowserStack cloud platform integration

Provides integration with BrowserStack for:
- Remote device access
- Parallel test execution
- Session management
- App upload and distribution
"""

import time
from pathlib import Path
from typing import List, Dict, Optional, Any

import requests


class BrowserStackClient:
    """
    BrowserStack API client

    Manages sessions, devices, and app uploads for BrowserStack.
    """

    BASE_URL = "https://api-cloud.browserstack.com"
    APP_AUTOMATE_URL = "https://api-cloud.browserstack.com/app-automate"

    def __init__(self, username: str, access_key: str):
        """
        Initialize BrowserStack client

        Args:
            username: BrowserStack username
            access_key: BrowserStack access key
        """
        self.username = username
        self.access_key = access_key
        self.auth = (username, access_key)
        self.session = requests.Session()
        self.session.auth = self.auth

    def get_devices(self, platform: Optional[str] = None) -> List[Dict]:
        """
        Get list of available devices on BrowserStack

        Args:
            platform: Filter by platform ("android" or "ios")

        Returns:
            List of device dictionaries
        """
        url = f"{self.APP_AUTOMATE_URL}/devices.json"
        response = self.session.get(url)
        response.raise_for_status()

        devices = response.json()

        if platform:
            platform_key = "android" if platform.lower() == "android" else "ios"
            devices = [d for d in devices if d.get('os', '').lower().startswith(platform_key)]

        return devices

    def upload_app(self, app_path: Path) -> str:
        """
        Upload app (APK/IPA) to BrowserStack

        Args:
            app_path: Path to APK or IPA file

        Returns:
            App URL for use in capabilities
        """
        url = f"{self.APP_AUTOMATE_URL}/upload"

        if not app_path.exists():
            raise FileNotFoundError(f"App file not found: {app_path}")

        print(f"Uploading {app_path.name} to BrowserStack...")

        with open(app_path, 'rb') as f:
            files = {'file': f}
            response = self.session.post(url, files=files)

        response.raise_for_status()
        data = response.json()

        app_url = data.get('app_url')
        print(f"✓ Upload complete: {app_url}")

        return app_url

    def get_sessions(self, limit: int = 10) -> List[Dict]:
        """
        Get recent test sessions

        Args:
            limit: Maximum number of sessions to retrieve

        Returns:
            List of session dictionaries
        """
        url = f"{self.APP_AUTOMATE_URL}/sessions.json"
        params = {'limit': limit}

        response = self.session.get(url, params=params)
        response.raise_for_status()

        return response.json()

    def get_session(self, session_id: str) -> Dict:
        """
        Get details of a specific session

        Args:
            session_id: BrowserStack session ID

        Returns:
            Session details dictionary
        """
        url = f"{self.APP_AUTOMATE_URL}/sessions/{session_id}.json"
        response = self.session.get(url)
        response.raise_for_status()

        return response.json()

    def delete_session(self, session_id: str):
        """
        Delete a session

        Args:
            session_id: BrowserStack session ID
        """
        url = f"{self.APP_AUTOMATE_URL}/sessions/{session_id}.json"
        response = self.session.delete(url)
        response.raise_for_status()

        print(f"✓ Deleted session: {session_id}")

    def get_build(self, build_id: str) -> Dict:
        """
        Get details of a build (collection of sessions)

        Args:
            build_id: Build ID

        Returns:
            Build details dictionary
        """
        url = f"{self.APP_AUTOMATE_URL}/builds/{build_id}.json"
        response = self.session.get(url)
        response.raise_for_status()

        return response.json()

    def get_builds(self, limit: int = 10) -> List[Dict]:
        """
        Get recent builds

        Args:
            limit: Maximum number of builds to retrieve

        Returns:
            List of build dictionaries
        """
        url = f"{self.APP_AUTOMATE_URL}/builds.json"
        params = {'limit': limit}

        response = self.session.get(url, params=params)
        response.raise_for_status()

        return response.json()

    def get_plan(self) -> Dict:
        """
        Get account plan details (parallelization limit, etc.)

        Returns:
            Plan details dictionary
        """
        url = f"{self.BASE_URL}/automate/plan.json"
        response = self.session.get(url)
        response.raise_for_status()

        return response.json()

    def generate_capabilities(
            self,
            device_name: str,
            os_version: str,
            app_url: str,
            project_name: Optional[str] = None,
            build_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate Appium capabilities for BrowserStack

        Args:
            device_name: Device name (e.g., "Google Pixel 7")
            os_version: OS version (e.g., "13.0")
            app_url: App URL from upload_app()
            project_name: Optional project name
            build_name: Optional build name

        Returns:
            Capabilities dictionary
        """
        capabilities = {
            'browserstack.user': self.username,
            'browserstack.key': self.access_key,
            'device': device_name,
            'os_version': os_version,
            'app': app_url,
            'browserstack.debug': True,
            'browserstack.networkLogs': True,
            'browserstack.video': True,
        }

        if project_name:
            capabilities['project'] = project_name

        if build_name:
            capabilities['build'] = build_name

        return capabilities


def create_client_from_env() -> BrowserStackClient:
    """
    Create BrowserStack client from environment variables

    Requires:
        BROWSERSTACK_USERNAME
        BROWSERSTACK_ACCESS_KEY

    Returns:
        Configured BrowserStackClient
    """
    import os

    username = os.getenv('BROWSERSTACK_USERNAME')
    access_key = os.getenv('BROWSERSTACK_ACCESS_KEY')

    if not username or not access_key:
        raise ValueError(
            "BrowserStack credentials not found. "
            "Set BROWSERSTACK_USERNAME and BROWSERSTACK_ACCESS_KEY environment variables."
        )

    return BrowserStackClient(username, access_key)


def wait_for_session_completion(
        client: BrowserStackClient,
        session_id: str,
        timeout: int = 3600,
        poll_interval: int = 10
) -> Dict:
    """
    Wait for a session to complete

    Args:
        client: BrowserStack client
        session_id: Session ID to monitor
        timeout: Maximum wait time in seconds
        poll_interval: How often to poll status

    Returns:
        Final session details
    """
    start_time = time.time()

    while True:
        if time.time() - start_time > timeout:
            raise TimeoutError(f"Session {session_id} did not complete within {timeout}s")

        session = client.get_session(session_id)
        status = session.get('status')

        if status in ['done', 'error', 'timeout']:
            return session

        time.sleep(poll_interval)
