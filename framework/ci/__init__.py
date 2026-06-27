"""
CI/CD integration and workflow generation

Generates CI/CD configuration files for various platforms:
- GitHub Actions
- GitLab CI
- Jenkins
- CircleCI
- Azure Pipelines
"""

from .github_actions import GitHubActionsGenerator
from .gitlab_ci import GitLabCIGenerator

__all__ = [
    "GitHubActionsGenerator",
    "GitLabCIGenerator",
]
