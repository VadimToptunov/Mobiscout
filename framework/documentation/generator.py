"""
Documentation Generator - Auto-generate documentation from code
"""

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Any

from framework.documentation.parser import CodeParser, DocstringParser, ModuleDoc


class DocFormat(str, Enum):
    """Documentation output format"""
    MARKDOWN = "markdown"
    HTML = "html"
    JSON = "json"
    SPHINX = "sphinx"


@dataclass
class DocConfig:
    """Configuration for documentation generation"""
    source_dir: Path
    output_dir: Path
    format: DocFormat = DocFormat.MARKDOWN
    include_private: bool = False
    include_source: bool = False
    include_toc: bool = True
    theme: str = "default"
    title: str = "API Documentation"


class DocGenerator:
    """Generate documentation from Python code"""

    def __init__(self, config: DocConfig) -> None:
        self.config = config
        self.parser = CodeParser()
        self.docstring_parser = DocstringParser()
        self.modules: List[ModuleDoc] = []

    def generate(self) -> None:
        """Generate documentation"""
        # Parse all Python files
        python_files = list(self.config.source_dir.rglob("*.py"))

        for file_path in python_files:
            if not self._should_process(file_path):
                continue

            try:
                module_doc = self.parser.parse_file(file_path)
                self.modules.append(module_doc)
            except Exception as e:
                print(f"Warning: Failed to parse {file_path}: {e}")

        # Generate documentation
        self.config.output_dir.mkdir(parents=True, exist_ok=True)

        if self.config.format == DocFormat.MARKDOWN:
            self._generate_markdown()
        elif self.config.format == DocFormat.HTML:
            self._generate_html()
        elif self.config.format == DocFormat.JSON:
            self._generate_json()
        elif self.config.format == DocFormat.SPHINX:
            self._generate_sphinx()

    def _should_process(self, file_path: Path) -> bool:
        """Check if file should be processed"""
        # Skip __pycache__, tests, etc.
        exclude_dirs = ["__pycache__", ".venv", "venv", "build", "dist", "tests"]

        for part in file_path.parts:
            if part in exclude_dirs:
                return False

        # Skip private modules unless configured
        if not self.config.include_private and file_path.stem.startswith("_"):
            if file_path.stem != "__init__":
                return False

        return True

    def _generate_markdown(self) -> None:
        """Generate Markdown documentation"""
        # Generate index
        index_path = self.config.output_dir / "index.md"
        with open(index_path, "w") as f:
            f.write(f"# {self.config.title}\n\n")

            if self.config.include_toc:
                f.write("## Table of Contents\n\n")
                for module in sorted(self.modules, key=lambda m: m.name):
                    f.write(f"- [{module.name}]({module.name}.md)\n")
                f.write("\n")

        # Generate module docs
        for module in self.modules:
            self._generate_module_markdown(module)

    def _generate_module_markdown(self, module: ModuleDoc) -> None:
        """Generate Markdown for a module"""
        output_path = self.config.output_dir / f"{module.name}.md"

        with open(output_path, "w") as f:
            # Module header
            f.write(f"# {module.name}\n\n")

            if module.docstring:
                f.write(f"{module.docstring}\n\n")

            # Classes
            if module.classes:
                f.write("## Classes\n\n")
                for cls in module.classes:
                    self._write_class_markdown(f, cls)

            # Functions
            if module.functions:
                f.write("## Functions\n\n")
                for func in module.functions:
                    self._write_function_markdown(f, func)

            # Constants
            if module.constants:
                f.write("## Constants\n\n")
                for name, value in module.constants.items():
                    f.write(f"### `{name}`\n\n")
                    f.write(f"```python\n{name} = {value}\n```\n\n")

    def _write_class_markdown(self, f: Any, cls: Any) -> None:
        """Write class documentation in Markdown"""
        f.write(f"### {cls.name}\n\n")

        if cls.bases:
            f.write(f"**Inherits from:** {', '.join(cls.bases)}\n\n")

        if cls.docstring:
            f.write(f"{cls.docstring}\n\n")

        # Attributes
        if cls.attributes:
            f.write("**Attributes:**\n\n")
            for attr in cls.attributes:
                type_str = f": {attr['type']}" if attr["type"] else ""
                f.write(f"- `{attr['name']}{type_str}`\n")
            f.write("\n")

        # Methods
        if cls.methods:
            f.write("**Methods:**\n\n")
            for method in cls.methods:
                # Skip private methods unless configured
                if not self.config.include_private and method.name.startswith("_"):
                    if method.name != "__init__":
                        continue

                f.write(f"#### `{method.signature}`\n\n")

                if method.docstring:
                    parsed = self.docstring_parser.parse_google_style(method.docstring)
                    f.write(f"{parsed.get('description', '')}\n\n")

                    if parsed.get("args"):
                        f.write("**Parameters:**\n\n")
                        for arg in parsed["args"]:
                            f.write(f"- {arg}\n")
                        f.write("\n")

                    if parsed.get("returns"):
                        f.write(f"**Returns:** {parsed['returns']}\n\n")

                    if parsed.get("raises"):
                        f.write("**Raises:**\n\n")
                        for exc in parsed["raises"]:
                            f.write(f"- {exc}\n")
                        f.write("\n")

    def _write_function_markdown(self, f: Any, func: Any) -> None:
        """Write function documentation in Markdown"""
        f.write(f"### `{func.signature}`\n\n")

        if func.docstring:
            parsed = self.docstring_parser.parse_google_style(func.docstring)
            f.write(f"{parsed.get('description', '')}\n\n")

            if parsed.get("args"):
                f.write("**Parameters:**\n\n")
                for arg in parsed["args"]:
                    f.write(f"- {arg}\n")
                f.write("\n")

            if parsed.get("returns"):
                f.write(f"**Returns:** {parsed['returns']}\n\n")

            if parsed.get("example"):
                f.write("**Example:**\n\n")
                f.write(f"```python\n{parsed['example']}\n```\n\n")

    def _generate_html(self) -> None:
        """Generate HTML documentation"""
        # Generate index.html
        index_path = self.config.output_dir / "index.html"

        html = self._generate_html_header()

        html += f"<h1>{self.config.title}</h1>\n"

        if self.config.include_toc:
            html += "<h2>Table of Contents</h2>\n<ul>\n"
            for module in sorted(self.modules, key=lambda m: m.name):
                html += f'<li><a href="{module.name}.html">{module.name}</a></li>\n'
            html += "</ul>\n"

        html += self._generate_html_footer()

        with open(index_path, "w") as f:
            f.write(html)

        # Generate module HTML files
        for module in self.modules:
            self._generate_module_html(module)

    def _generate_module_html(self, module: ModuleDoc) -> None:
        """Generate HTML for a module"""
        output_path = self.config.output_dir / f"{module.name}.html"

        html = self._generate_html_header()
        html += f"<h1>{module.name}</h1>\n"

        if module.docstring:
            html += f"<p>{module.docstring}</p>\n"

        # Classes
        if module.classes:
            html += "<h2>Classes</h2>\n"
            for cls in module.classes:
                html += f"<div class='class'>\n"
                html += f"<h3>{cls.name}</h3>\n"
                if cls.docstring:
                    html += f"<p>{cls.docstring}</p>\n"

                # Methods
                if cls.methods:
                    html += "<h4>Methods</h4>\n<ul>\n"
                    for method in cls.methods:
                        if not self.config.include_private and method.name.startswith("_"):
                            if method.name != "__init__":
                                continue
                        html += f"<li><code>{method.signature}</code></li>\n"
                    html += "</ul>\n"

                html += "</div>\n"

        # Functions
        if module.functions:
            html += "<h2>Functions</h2>\n"
            for func in module.functions:
                html += f"<div class='function'>\n"
                html += f"<h3><code>{func.signature}</code></h3>\n"
                if func.docstring:
                    html += f"<p>{func.docstring}</p>\n"
                html += "</div>\n"

        html += self._generate_html_footer()

        with open(output_path, "w") as f:
            f.write(html)

    def _generate_html_header(self) -> str:
        """Generate HTML header"""
        return """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>API Documentation</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            line-height: 1.6;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }
        h1 { color: #333; border-bottom: 3px solid #007bff; padding-bottom: 10px; }
        h2 { color: #555; margin-top: 30px; }
        h3 { color: #666; }
        code {
            background: #f4f4f4;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'Courier New', monospace;
        }
        .class, .function {
            background: white;
            padding: 20px;
            margin: 20px 0;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        ul { list-style: none; padding: 0; }
        li { padding: 5px 0; }
        a { color: #007bff; text-decoration: none; }
        a:hover { text-decoration: underline; }
    </style>
</head>
<body>
"""

    def _generate_html_footer(self) -> str:
        """Generate HTML footer"""
        return """
</body>
</html>
"""

    def _generate_json(self) -> None:
        """Generate JSON documentation"""
        output_path = self.config.output_dir / "api_docs.json"

        docs = []
        for module in self.modules:
            module_data = {
                "name": module.name,
                "path": str(module.path),
                "docstring": module.docstring,
                "classes": [
                    {
                        "name": cls.name,
                        "docstring": cls.docstring,
                        "bases": cls.bases,
                        "methods": [
                            {
                                "name": method.name,
                                "signature": method.signature,
                                "docstring": method.docstring,
                                "parameters": method.parameters,
                                "return_type": method.return_type,
                            }
                            for method in cls.methods
                        ],
                        "attributes": cls.attributes,
                    }
                    for cls in module.classes
                ],
                "functions": [
                    {
                        "name": func.name,
                        "signature": func.signature,
                        "docstring": func.docstring,
                        "parameters": func.parameters,
                        "return_type": func.return_type,
                    }
                    for func in module.functions
                ],
            }
            docs.append(module_data)

        with open(output_path, "w") as f:
            json.dump(docs, f, indent=2)

    def _generate_sphinx(self) -> None:
        """Generate Sphinx RST documentation"""
        # Generate conf.py
        conf_path = self.config.output_dir / "conf.py"
        with open(conf_path, "w") as f:
            f.write(f"""
project = '{self.config.title}'
html_theme = '{self.config.theme}'
extensions = ['sphinx.ext.autodoc', 'sphinx.ext.napoleon']
""")

        # Generate index.rst
        index_path = self.config.output_dir / "index.rst"
        with open(index_path, "w") as f:
            f.write(f"{self.config.title}\n")
            f.write("=" * len(self.config.title) + "\n\n")

            f.write(".. toctree::\n")
            f.write("   :maxdepth: 2\n\n")

            for module in self.modules:
                f.write(f"   {module.name}\n")

        # Generate module .rst files
        for module in self.modules:
            self._generate_module_sphinx(module)

    def _generate_module_sphinx(self, module: ModuleDoc) -> None:
        """Generate Sphinx RST for a module"""
        output_path = self.config.output_dir / f"{module.name}.rst"

        with open(output_path, "w") as f:
            f.write(f"{module.name}\n")
            f.write("=" * len(module.name) + "\n\n")

            f.write(f".. automodule:: {module.name}\n")
            f.write("   :members:\n")
            f.write("   :undoc-members:\n")
            f.write("   :show-inheritance:\n")
