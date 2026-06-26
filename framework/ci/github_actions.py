"""
GitHub Actions workflow generator

Creates comprehensive GitHub Actions workflows for mobile testing.
"""

from pathlib import Path
from typing import Dict, List, Optional, Any

import yaml


class GitHubActionsGenerator:
    """
    Generates GitHub Actions workflows for mobile test automation
    """

    def __init__(self, project_name: str = "Mobile Tests") -> None:
        self.project_name = project_name

    def generate_basic_workflow(
            self, platforms: Optional[List[str]] = None, python_version: str = "3.13",
            triggers: Optional[List[str]] = None
    ) -> str:
        """
        Generate basic test workflow

        Args:
            platforms: List of platforms ('android', 'ios')
            python_version: Python version
            triggers: List of triggers ('push', 'pull_request', 'schedule')

        Returns:
            YAML workflow content
        """
        if platforms is None:
            platforms = ["android"]
        if triggers is None:
            triggers = ["push", "pull_request"]

        workflow: Dict[str, Any] = {"name": self.project_name, "on": self._generate_triggers(triggers), "jobs": {}}

        # Add test job for each platform
        for platform in platforms:
            job_name = f"test-{platform}"
            workflow["jobs"][job_name] = self._generate_test_job(platform, python_version)

        return yaml.dump(workflow, sort_keys=False, default_flow_style=False)

    def generate_advanced_workflow(
            self,
            platforms: Optional[List[str]] = None,
            python_version: str = "3.13",
            parallel_count: int = 2,
            use_browserstack: bool = False,
            upload_artifacts: bool = True,
            notify_slack: bool = False,
    ) -> str:
        """
        Generate advanced CI workflow with parallel testing

        Args:
            platforms: List of platforms ('android', 'ios')
            python_version: Python version
            parallel_count: Number of parallel jobs
            use_browserstack: Whether to use BrowserStack
            upload_artifacts: Whether to upload test artifacts
            notify_slack: Whether to send Slack notifications
        """
        if platforms is None:
            platforms = ["android", "ios"]

        workflow: Dict[str, Any] = {
            "name": f"{self.project_name} - Advanced",
            "on": self._generate_triggers(["push", "pull_request", "schedule"]),
            "env": {
                "PYTHON_VERSION": python_version,
            },
            "jobs": {},
        }

        # Add BrowserStack env vars if needed
        if use_browserstack:
            workflow["env"].update(
                {
                    "BROWSERSTACK_USERNAME": "${{ secrets.BROWSERSTACK_USERNAME }}",
                    "BROWSERSTACK_ACCESS_KEY": "${{ secrets.BROWSERSTACK_ACCESS_KEY }}",
                }
            )

        # Lint job
        workflow["jobs"]["lint"] = self._generate_lint_job(python_version)

        # Test jobs for each platform
        # Track job names for dependency resolution
        test_job_names = []
        for platform in platforms:
            if use_browserstack:
                job_name = f"test-{platform}-cloud"
                workflow["jobs"][job_name] = self._generate_browserstack_job(platform, python_version, parallel_count)
            else:
                job_name = f"test-{platform}"
                workflow["jobs"][job_name] = self._generate_test_job(platform, python_version, parallel_count)
            test_job_names.append(job_name)

        # Report job
        if upload_artifacts:
            workflow["jobs"]["report"] = self._generate_report_job(test_job_names)

        # Notify job
        if notify_slack:
            workflow["jobs"]["notify"] = self._generate_notify_job(test_job_names)

        return yaml.dump(workflow, sort_keys=False, default_flow_style=False)

    def _generate_triggers(self, triggers: List[str]) -> Dict[str, Any]:
        """Generate workflow triggers"""
        result: Dict[str, Any] = {}

        if "push" in triggers:
            result["push"] = {"branches": ["main", "develop"]}

        if "pull_request" in triggers:
            result["pull_request"] = {"branches": ["main", "develop"]}

        if "schedule" in triggers:
            result["schedule"] = [{"cron": "0 2 * * *"}]  # Daily at 2 AM

        if "workflow_dispatch" in triggers or len(triggers) == 0:
            result["workflow_dispatch"] = {}

        return result

    def _generate_test_job(self, platform: str, python_version: str, parallel_count: int = 1) -> Dict[str, Any]:
        """Generate test job for platform"""
        # Choose runner based on platform
        runner = "macos-latest" if platform == "ios" else "ubuntu-latest"

        job: Dict[str, Any] = {
            "name": f"Test {platform.capitalize()}",
            "runs-on": runner,
            "strategy": (
                {"fail-fast": False, "matrix": {"shard": list(range(1, parallel_count + 1))}}
                if parallel_count > 1
                else {}
            ),
            "steps": [
                {"name": "Checkout code", "uses": "actions/checkout@v4"},
                {
                    "name": "Set up Python",
                    "uses": "actions/setup-python@v5",
                    "with": {"python-version": python_version},
                },
                {
                    "name": "Cache dependencies",
                    "uses": "actions/cache@v4",
                    "with": {
                        "path": "~/.cache/pip",
                        "key": "${{ runner.os }}-pip-${{ hashFiles('**/requirements.txt') }}",
                        "restore-keys": "${{ runner.os }}-pip-",
                    },
                },
                {"name": "Install dependencies", "run": "pip install -r requirements.txt"},
            ],
        }

        # Platform-specific setup
        if platform == "android":
            job["steps"].extend(
                [
                    {
                        "name": "Set up JDK",
                        "uses": "actions/setup-java@v4",
                        "with": {"java-version": "11", "distribution": "temurin"},
                    },
                    {"name": "Setup Android SDK", "uses": "android-actions/setup-android@v3"},
                    {
                        "name": "Create AVD and start emulator",
                        "run": "\n".join(
                            [
                                'avdmanager create avd -n test -k "system-images;android-33;google_apis;x86_64"',
                                "emulator -avd test -no-window -no-audio -no-boot-anim &",
                                'adb wait-for-device shell "while [[ -z $(getprop sys.boot_completed) ]]; do sleep 1; done"',
                            ]
                        ),
                    },
                ]
            )
        elif platform == "ios":
            job["steps"].extend(
                [
                    {"name": "List available simulators", "run": "xcrun simctl list devices available"},
                    {
                        "name": "Boot simulator",
                        "run": "\n".join(
                            ['UDID=$(xcrun simctl create TestDevice "iPhone 15")', "xcrun simctl boot $UDID"]
                        ),
                    },
                ]
            )

        # Test execution
        test_cmd = "pytest tests/ --verbose --junit-xml=reports/junit.xml --html=reports/report.html"
        if parallel_count > 1:
            test_cmd += " --shard-id=${{ matrix.shard }} --num-shards=" + str(parallel_count)

        job["steps"].extend(
            [
                {"name": "Run tests", "run": test_cmd},
                {
                    "name": "Upload test results",
                    "if": "always()",
                    "uses": "actions/upload-artifact@v4",
                    "with": {
                        "name": (
                            f"test-results-{platform}-${{{{ matrix.shard }}}}"
                            if parallel_count > 1
                            else f"test-results-{platform}"
                        ),
                        "path": "reports/",
                    },
                },
            ]
        )

        return job

    def _generate_browserstack_job(self, platform: str, python_version: str, parallel_count: int) -> Dict[str, Any]:
        """Generate BrowserStack cloud test job"""
        job = {
            "name": f"Test {platform.capitalize()} on BrowserStack",
            "runs-on": "ubuntu-latest",
            "strategy": {"fail-fast": False, "matrix": {"device": self._get_browserstack_devices(platform)}},
            "steps": [
                {"name": "Checkout code", "uses": "actions/checkout@v4"},
                {
                    "name": "Set up Python",
                    "uses": "actions/setup-python@v5",
                    "with": {"python-version": python_version},
                },
                {"name": "Install dependencies", "run": "pip install -r requirements.txt"},
                {"name": "Upload app to BrowserStack", "run": "observe browserstack upload --app app-debug.apk"},
                {
                    "name": "Run tests on BrowserStack",
                    "run": 'pytest tests/ --browserstack --device="${{ matrix.device }}" --junit-xml=reports/junit.xml',
                },
                {
                    "name": "Upload test results",
                    "if": "always()",
                    "uses": "actions/upload-artifact@v4",
                    "with": {"name": "test-results-${{ matrix.device }}", "path": "reports/"},
                },
            ],
        }

        return job

    def _get_browserstack_devices(self, platform: str) -> List[str]:
        """Get list of BrowserStack devices for testing"""
        if platform == "android":
            return ["Google Pixel 7", "Samsung Galaxy S23"]
        else:  # ios
            return ["iPhone 15", "iPhone 14 Pro"]

    def _generate_lint_job(self, python_version: str) -> Dict[str, Any]:
        """Generate linting job"""
        return {
            "name": "Lint",
            "runs-on": "ubuntu-latest",
            "steps": [
                {"name": "Checkout code", "uses": "actions/checkout@v4"},
                {
                    "name": "Set up Python",
                    "uses": "actions/setup-python@v5",
                    "with": {"python-version": python_version},
                },
                {"name": "Install linters", "run": "pip install flake8 black mypy"},
                {"name": "Run flake8", "run": "flake8 tests/ --max-line-length=120"},
                {"name": "Run black", "run": "black --check tests/"},
                {"name": "Run mypy", "run": "mypy tests/ --ignore-missing-imports"},
            ],
        }

    def _generate_report_job(self, test_job_names: List[str]) -> Dict[str, Any]:
        """Generate report aggregation job"""
        return {
            "name": "Generate Report",
            "runs-on": "ubuntu-latest",
            "needs": test_job_names,  # Dynamic dependencies based on actual test jobs
            "if": "always()",
            "steps": [
                {
                    "name": "Download all artifacts",
                    "uses": "actions/download-artifact@v4",
                    "with": {"path": "all-results"},
                },
                {
                    "name": "Aggregate results",
                    "run": "observe report generate --input all-results/ --output final-report.html",
                },
                {
                    "name": "Upload final report",
                    "uses": "actions/upload-artifact@v4",
                    "with": {"name": "final-report", "path": "final-report.html"},
                },
                {
                    "name": "Comment on PR",
                    "if": "github.event_name == 'pull_request'",
                    "run": "observe ci comment --report final-report.html",
                },
            ],
        }

    def _generate_notify_job(self, test_job_names: List[str]) -> Dict[str, Any]:
        """Generate notification job"""
        return {
            "name": "Notify",
            "runs-on": "ubuntu-latest",
            "needs": test_job_names,  # Dynamic dependencies based on actual test jobs
            "if": "always()",
            "steps": [
                {
                    "name": "Send Slack notification",
                    "uses": "slackapi/slack-github-action@v1",
                    "with": {"payload": '{"text": "Tests completed: ${{ job.status }}"}'},
                    "env": {"SLACK_WEBHOOK_URL": "${{ secrets.SLACK_WEBHOOK_URL }}"},
                }
            ],
        }

    def save_workflow(self, content: str, output_dir: Path, filename: str = "tests.yml") -> None:
        """
        Save workflow to file

        Args:
            content: Workflow YAML content
            output_dir: Output directory (will create .github/workflows/)
            filename: Workflow filename
        """
        workflow_dir = output_dir / ".github" / "workflows"
        workflow_dir.mkdir(parents=True, exist_ok=True)

        workflow_path = workflow_dir / filename
        workflow_path.write_text(content)

        print(f"✓ Workflow saved to: {workflow_path}")
