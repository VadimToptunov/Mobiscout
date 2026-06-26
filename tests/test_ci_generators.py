"""
Tests for CI/CD generators

Tests for:
- GitHubActionsGenerator
- GitLabCIGenerator
"""

from pathlib import Path
from tempfile import TemporaryDirectory

import yaml

from framework.ci.github_actions import GitHubActionsGenerator
from framework.ci.gitlab_ci import GitLabCIGenerator


class TestGitHubActionsGenerator:
    """Tests for GitHub Actions workflow generator"""

    def test_init_default_project_name(self) -> None:
        """Test default project name initialization"""
        generator = GitHubActionsGenerator()
        assert generator.project_name == "Mobile Tests"

    def test_init_custom_project_name(self) -> None:
        """Test custom project name initialization"""
        generator = GitHubActionsGenerator(project_name="My App Tests")
        assert generator.project_name == "My App Tests"

    def test_generate_basic_workflow_default(self) -> None:
        """Test basic workflow generation with defaults"""
        generator = GitHubActionsGenerator()
        workflow_yaml = generator.generate_basic_workflow()

        # Parse YAML to validate structure
        workflow = yaml.safe_load(workflow_yaml)

        assert workflow["name"] == "Mobile Tests"
        assert "on" in workflow
        assert "jobs" in workflow
        assert "test-android" in workflow["jobs"]

    def test_generate_basic_workflow_multiple_platforms(self) -> None:
        """Test basic workflow with multiple platforms"""
        generator = GitHubActionsGenerator()
        workflow_yaml = generator.generate_basic_workflow(
            platforms=["android", "ios"]
        )

        workflow = yaml.safe_load(workflow_yaml)

        assert "test-android" in workflow["jobs"]
        assert "test-ios" in workflow["jobs"]

    def test_generate_basic_workflow_custom_triggers(self) -> None:
        """Test basic workflow with custom triggers"""
        generator = GitHubActionsGenerator()
        workflow_yaml = generator.generate_basic_workflow(
            triggers=["push", "schedule"]
        )

        workflow = yaml.safe_load(workflow_yaml)

        assert "push" in workflow["on"]
        assert "schedule" in workflow["on"]

    def test_generate_basic_workflow_python_version(self) -> None:
        """Test basic workflow with custom Python version"""
        generator = GitHubActionsGenerator()
        workflow_yaml = generator.generate_basic_workflow(
            python_version="3.11"
        )

        workflow = yaml.safe_load(workflow_yaml)
        steps = workflow["jobs"]["test-android"]["steps"]

        # Find Python setup step
        python_step = next(
            (s for s in steps if s.get("name") == "Set up Python"), None
        )
        assert python_step is not None
        assert python_step["with"]["python-version"] == "3.11"

    def test_generate_advanced_workflow_default(self) -> None:
        """Test advanced workflow generation with defaults"""
        generator = GitHubActionsGenerator()
        workflow_yaml = generator.generate_advanced_workflow()

        workflow = yaml.safe_load(workflow_yaml)

        assert "Advanced" in workflow["name"]
        assert "lint" in workflow["jobs"]
        assert "env" in workflow

    def test_generate_advanced_workflow_with_browserstack(self) -> None:
        """Test advanced workflow with BrowserStack enabled"""
        generator = GitHubActionsGenerator()
        workflow_yaml = generator.generate_advanced_workflow(
            use_browserstack=True
        )

        workflow = yaml.safe_load(workflow_yaml)

        assert "BROWSERSTACK_USERNAME" in workflow["env"]
        assert "BROWSERSTACK_ACCESS_KEY" in workflow["env"]

    def test_generate_advanced_workflow_with_slack(self) -> None:
        """Test advanced workflow with Slack notifications"""
        generator = GitHubActionsGenerator()
        workflow_yaml = generator.generate_advanced_workflow(
            notify_slack=True
        )

        workflow = yaml.safe_load(workflow_yaml)

        assert "notify" in workflow["jobs"]

    def test_generate_advanced_workflow_with_artifacts(self) -> None:
        """Test advanced workflow with artifact upload"""
        generator = GitHubActionsGenerator()
        workflow_yaml = generator.generate_advanced_workflow(
            upload_artifacts=True
        )

        workflow = yaml.safe_load(workflow_yaml)

        assert "report" in workflow["jobs"]

    def test_save_workflow(self) -> None:
        """Test saving workflow to file"""
        generator = GitHubActionsGenerator()
        workflow_yaml = generator.generate_basic_workflow()

        with TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            generator.save_workflow(workflow_yaml, output_dir)

            expected_path = output_dir / ".github" / "workflows" / "tests.yml"
            assert expected_path.exists()

            content = expected_path.read_text()
            assert "Mobile Tests" in content

    def test_save_workflow_custom_filename(self) -> None:
        """Test saving workflow with custom filename"""
        generator = GitHubActionsGenerator()
        workflow_yaml = generator.generate_basic_workflow()

        with TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            generator.save_workflow(
                workflow_yaml, output_dir, filename="mobile-tests.yml"
            )

            expected_path = output_dir / ".github" / "workflows" / "mobile-tests.yml"
            assert expected_path.exists()


class TestGitLabCIGenerator:
    """Tests for GitLab CI pipeline generator"""

    def test_init_default_project_name(self) -> None:
        """Test default project name initialization"""
        generator = GitLabCIGenerator()
        assert generator.project_name == "Mobile Tests"

    def test_init_custom_project_name(self) -> None:
        """Test custom project name initialization"""
        generator = GitLabCIGenerator(project_name="My App Pipeline")
        assert generator.project_name == "My App Pipeline"

    def test_generate_basic_pipeline_default(self) -> None:
        """Test basic pipeline generation with defaults"""
        generator = GitLabCIGenerator()
        pipeline_yaml = generator.generate_basic_pipeline()

        pipeline = yaml.safe_load(pipeline_yaml)

        assert "stages" in pipeline
        assert "test:android" in pipeline
        assert pipeline["image"].startswith("python:")

    def test_generate_basic_pipeline_multiple_platforms(self) -> None:
        """Test basic pipeline with multiple platforms"""
        generator = GitLabCIGenerator()
        pipeline_yaml = generator.generate_basic_pipeline(
            platforms=["android", "ios"]
        )

        pipeline = yaml.safe_load(pipeline_yaml)

        assert "test:android" in pipeline
        assert "test:ios" in pipeline

    def test_generate_basic_pipeline_python_version(self) -> None:
        """Test basic pipeline with custom Python version"""
        generator = GitLabCIGenerator()
        pipeline_yaml = generator.generate_basic_pipeline(
            python_version="3.11"
        )

        pipeline = yaml.safe_load(pipeline_yaml)

        assert pipeline["image"] == "python:3.11"

    def test_generate_advanced_pipeline_default(self) -> None:
        """Test advanced pipeline generation with defaults"""
        generator = GitLabCIGenerator()
        pipeline_yaml = generator.generate_advanced_pipeline()

        pipeline = yaml.safe_load(pipeline_yaml)

        assert "lint" in pipeline["stages"]
        assert "lint" in pipeline
        assert "variables" in pipeline
        assert "cache" in pipeline

    def test_generate_advanced_pipeline_parallel(self) -> None:
        """Test advanced pipeline with parallel execution"""
        generator = GitLabCIGenerator()
        pipeline_yaml = generator.generate_advanced_pipeline(
            parallel_count=3
        )

        pipeline = yaml.safe_load(pipeline_yaml)

        # Check that test jobs have parallel configuration
        test_job = pipeline.get("test:android", {})
        assert test_job.get("parallel") == 3

    def test_generate_advanced_pipeline_platforms(self) -> None:
        """Test advanced pipeline with specific platforms"""
        generator = GitLabCIGenerator()
        pipeline_yaml = generator.generate_advanced_pipeline(
            platforms=["android"]
        )

        pipeline = yaml.safe_load(pipeline_yaml)

        assert "test:android" in pipeline
        assert "test:ios" not in pipeline

    def test_save_pipeline(self) -> None:
        """Test saving pipeline to file"""
        generator = GitLabCIGenerator()
        pipeline_yaml = generator.generate_basic_pipeline()

        with TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            generator.save_pipeline(pipeline_yaml, output_dir)

            expected_path = output_dir / ".gitlab-ci.yml"
            assert expected_path.exists()

    def test_save_pipeline_custom_filename(self) -> None:
        """Test saving pipeline with custom filename"""
        generator = GitLabCIGenerator()
        pipeline_yaml = generator.generate_basic_pipeline()

        with TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            generator.save_pipeline(
                pipeline_yaml, output_dir, filename="ci-config.yml"
            )

            expected_path = output_dir / "ci-config.yml"
            assert expected_path.exists()


class TestCIGeneratorIntegration:
    """Integration tests for CI generators"""

    def test_github_workflow_is_valid_yaml(self) -> None:
        """Test that generated GitHub workflow is valid YAML"""
        generator = GitHubActionsGenerator()

        # Generate various workflows
        workflows = [
            generator.generate_basic_workflow(),
            generator.generate_advanced_workflow(),
            generator.generate_advanced_workflow(
                use_browserstack=True, notify_slack=True
            ),
        ]

        for workflow_yaml in workflows:
            # Should not raise
            yaml.safe_load(workflow_yaml)

    def test_gitlab_pipeline_is_valid_yaml(self) -> None:
        """Test that generated GitLab pipeline is valid YAML"""
        generator = GitLabCIGenerator()

        # Generate various pipelines
        pipelines = [
            generator.generate_basic_pipeline(),
            generator.generate_advanced_pipeline(),
            generator.generate_advanced_pipeline(parallel_count=5),
        ]

        for pipeline_yaml in pipelines:
            # Should not raise
            yaml.safe_load(pipeline_yaml)

    def test_github_workflow_has_required_structure(self) -> None:
        """Test that GitHub workflow has required structure"""
        generator = GitHubActionsGenerator()
        workflow_yaml = generator.generate_basic_workflow()
        workflow = yaml.safe_load(workflow_yaml)

        # Required top-level keys
        assert "name" in workflow
        assert "on" in workflow
        assert "jobs" in workflow

        # Jobs should have steps
        for job_name, job in workflow["jobs"].items():
            assert "steps" in job
            assert len(job["steps"]) > 0

    def test_gitlab_pipeline_has_required_structure(self) -> None:
        """Test that GitLab pipeline has required structure"""
        generator = GitLabCIGenerator()
        pipeline_yaml = generator.generate_basic_pipeline()
        pipeline = yaml.safe_load(pipeline_yaml)

        # Required top-level keys
        assert "stages" in pipeline

        # Test jobs should have stage and script
        for key, value in pipeline.items():
            if key.startswith("test:"):
                assert "stage" in value
                assert "script" in value
