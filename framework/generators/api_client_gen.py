"""
API Client Generator

Generates API client classes from App Model API calls.
"""

from pathlib import Path
from typing import List

from jinja2 import Template

from framework.model.app_model import APICall

API_CLIENT_TEMPLATE = """
import requests
from typing import Optional, Dict, Any
from pydantic import BaseModel


class APIClient:
    \"\"\"
    API Client for backend

    Generated from App Model
    \"\"\"

    def __init__(self, base_url: str, auth_token: Optional[str] = None):
        self.base_url = base_url.rstrip('/')
        self.auth_token = auth_token
        self.session = requests.Session()

        if auth_token:
            self.session.headers['Authorization'] = f'Bearer {auth_token}'

    def _request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        \"\"\"Make HTTP request\"\"\"
        url = f"{self.base_url}{endpoint}"
        response = self.session.request(method, url, **kwargs)
        response.raise_for_status()
        return response

{% for api_call in api_calls %}
    def {{ api_call.name }}(self{% for param in api_call.parameters %}, {{ param.name }}: {{ param.type }}{% if param.default %} = {{ param.default }}{% endif %}{% endfor %}) -> Dict[str, Any]:
        \"\"\"
        {{ api_call.description or api_call.name }}

        Endpoint: {{ api_call.method }} {{ api_call.endpoint }}
        \"\"\"
{% if api_call.method in ['POST', 'PUT', 'PATCH'] %}
        data = {
{% for param in api_call.parameters %}
            '{{ param.name }}': {{ param.name }},
{% endfor %}
        }
        response = self._request('{{ api_call.method }}', '{{ api_call.endpoint }}', json=data)
{% else %}
        params = {
{% for param in api_call.parameters %}
            '{{ param.name }}': {{ param.name }},
{% endfor %}
        }
        response = self._request('{{ api_call.method }}', '{{ api_call.endpoint }}', params=params)
{% endif %}
        return response.json()

{% endfor %}
"""


def generate_api_client(api_calls: List[APICall], output_file: Path) -> Path:
    """
    Generate API client from API calls

    Args:
        api_calls: List of API call models
        output_file: Output file path

    Returns:
        Path to generated file
    """
    # Render template
    template = Template(API_CLIENT_TEMPLATE)
    content = template.render(api_calls=api_calls)

    # Write to file
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(content)

    return output_file
