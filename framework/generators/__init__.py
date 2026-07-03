"""
Code generators for test artifacts.

Page Object generation moved to framework.codegen.page_object (the IR-based
pipeline). The API-client and BDD-feature generators remain here until they
migrate too.
"""

from framework.generators.api_client_gen import generate_api_client
from framework.generators.bdd_gen import generate_feature_file, generate_step_definitions

__all__ = [
    "generate_api_client",
    "generate_feature_file",
    "generate_step_definitions",
]
