"""
GitLab CI pipeline generator

Creates comprehensive GitLab CI pipelines for mobile testing.
"""

from pathlib import Path
from typing import Dict, List, Optional, Any

import yaml


class GitLabCIGenerator:
    """
    Generates GitLab CI pipelines for mobile test automation
    """

    def __init__(self, project_name: str = "Mobile Tests"):
        self.project_name = project_name

    def generate_basic_pipeline(
            self,
            platforms: Optional[List[str]] = None,
            python_version: str = '3.13'
    ) -> str:
        """
        Generate basic CI pipeline

        Args:
            platforms: List of platforms ('android', 'ios')
            python_version: Python version

        Returns:
            YAML pipeline content
        """
        if platforms is None:
            platforms = ['android']
        pipeline: Dict[str, Any] = {
            'stages': ['test', 'report'],
            'image': f'python:{python_version}',
            'before_script': [
                'pip install --upgrade pip',
                'pip install -r requirements.txt'
            ]
        }

        # Add test jobs for each platform
        for platform in platforms:
            job_name = f'test:{platform}'
            pipeline[job_name] = self._generate_test_job(platform)

        result = yaml.dump(pipeline, sort_keys=False, default_flow_style=False)
        return str(result)

    def generate_advanced_pipeline(
            self,
            platforms: Optional[List[str]] = None,
            python_version: str = '3.13',
            parallel_count: int = 2,
            use_docker: bool = True
    ) -> str:
        """
        Generate advanced pipeline with parallel execution and Docker

        Args:
            platforms: List of platforms ('android', 'ios')
            python_version: Python version
            parallel_count: Number of parallel jobs
            use_docker: Whether to use Docker
        """
        if platforms is None:
            platforms = ['android', 'ios']

        pipeline = {
            'stages': ['lint', 'test', 'report'],  # Removed 'notify' - not implemented
            'variables': {
                'PYTHON_VERSION': python_version,
                'PIP_CACHE_DIR': '$CI_PROJECT_DIR/.cache/pip'
            },
            'cache': {
                'paths': ['.cache/pip', '.venv/']
            },
            'before_script': [
                'python -m venv .venv',
                'source .venv/bin/activate',
                'pip install --upgrade pip',
                'pip install -r requirements.txt'
            ]
        }

        # Lint stage
        pipeline['lint'] = self._generate_lint_job()

        # Test jobs for each platform
        # Track job names for dependency resolution
        test_job_names = []
        for platform in platforms:
            job_name = f'test:{platform}'
            pipeline[job_name] = self._generate_test_job_advanced(
                platform, parallel_count
            )
            test_job_names.append(job_name)

        # Report job
        pipeline['report'] = self._generate_report_job(test_job_names)

        return yaml.dump(pipeline, sort_keys=False, default_flow_style=False)

    def _generate_test_job(self, platform: str) -> Dict:
        """Generate basic test job"""
        # Use appropriate Docker image
        if platform == 'android':
            image = 'androidsdk/android-30'
        else:
            image = 'macos-latest'  # GitLab doesn't have iOS images, need runners

        job = {
            'stage': 'test',
            'script': [
                f'echo "Running {platform} tests"',
                'pytest tests/ --verbose --junit-xml=reports/junit.xml'
            ],
            'artifacts': {
                'when': 'always',
                'paths': ['reports/'],
                'reports': {
                    'junit': 'reports/junit.xml'
                }
            }
        }

        if platform == 'android':
            job['image'] = image
        else:
            job['tags'] = ['macos']  # Requires macOS runner

        return job

    def _generate_test_job_advanced(self, platform: str, parallel_count: int) -> Dict:
        """Generate advanced test job with parallelization"""
        job = self._generate_test_job(platform)

        if parallel_count > 1:
            job['parallel'] = parallel_count
            job['script'] = [
                f'echo "Running {platform} tests (shard $CI_NODE_INDEX/$CI_NODE_TOTAL)"',
                'pytest tests/ --verbose --junit-xml=reports/junit-$CI_NODE_INDEX.xml --shard-id=$CI_NODE_INDEX --num-shards=$CI_NODE_TOTAL'
            ]

        return job

    def _generate_lint_job(self) -> Dict:
        """Generate linting job"""
        return {
            'stage': 'lint',
            'script': [
                'pip install flake8 black mypy',
                'flake8 tests/ --max-line-length=120',
                'black --check tests/',
                'mypy tests/ --ignore-missing-imports'
            ],
            'allow_failure': True
        }

    def _generate_report_job(self, test_job_names: List[str]) -> Dict:
        """Generate report aggregation job"""
        return {
            'stage': 'report',
            'dependencies': test_job_names,  # Dynamic dependencies based on actual test jobs
            'script': [
                'observe report generate --input reports/ --output final-report.html'
            ],
            'artifacts': {
                'paths': ['final-report.html'],
                'expose_as': 'Test Report'
            },
            'when': 'always'
        }

    def save_pipeline(self, content: str, output_dir: Path, filename: str = '.gitlab-ci.yml'):
        """
        Save pipeline to file

        Args:
            content: Pipeline YAML content
            output_dir: Output directory
            filename: Pipeline filename
        """
        pipeline_path = output_dir / filename
        pipeline_path.write_text(content)

        print(f"✓ Pipeline saved to: {pipeline_path}")
