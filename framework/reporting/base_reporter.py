"""
Base Reporter Module

Provides abstract base class for all report generators in the framework.
"""

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional


class ReportFormat(Enum):
    """Supported report output formats."""
    JSON = "json"
    HTML = "html"
    TEXT = "text"
    XML = "xml"
    MARKDOWN = "markdown"


@dataclass
class ReportMetadata:
    """
    Metadata for generated reports.

    Attributes:
        title: Report title
        generated_at: Timestamp of report generation
        generator: Name of the generator class
        version: Report format version
    """
    title: str
    generated_at: datetime
    generator: str
    version: str = "1.0"

    def to_dict(self) -> Dict[str, Any]:
        """Convert metadata to dictionary."""
        return {
            'title': self.title,
            'generated_at': self.generated_at.isoformat(),
            'generator': self.generator,
            'version': self.version,
        }


class BaseReporter(ABC):
    """
    Abstract base class for report generators.

    Provides common functionality for:
    - Writing reports in different formats (JSON, HTML, etc.)
    - Metadata management
    - Output directory creation
    - Logging

    Subclasses must implement the `generate_report` method.

    Example:
        class SecurityReporter(BaseReporter):
            def generate_report(
                self,
                output_path: Path,
                format: ReportFormat = ReportFormat.JSON
            ) -> None:
                data = self._collect_data()
                if format == ReportFormat.JSON:
                    self._write_json(data, output_path)
                elif format == ReportFormat.HTML:
                    html = self._render_html(data)
                    self._write_html(html, output_path)
    """

    def __init__(self, title: str = "Report") -> None:
        """
        Initialize the reporter.

        Args:
            title: Report title
        """
        self.title = title
        self.logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    def generate_report(
            self,
            output_path: Path,
            format: ReportFormat = ReportFormat.JSON
    ) -> None:
        """
        Generate and save a report.

        Must be implemented by subclasses.

        Args:
            output_path: Path where the report will be saved
            format: Output format (JSON, HTML, etc.)
        """
        pass

    def _create_metadata(self) -> ReportMetadata:
        """
        Create report metadata.

        Returns:
            ReportMetadata instance
        """
        return ReportMetadata(
            title=self.title,
            generated_at=datetime.now(),
            generator=self.__class__.__name__,
        )

    def _ensure_output_dir(self, path: Path) -> None:
        """
        Ensure the output directory exists.

        Args:
            path: File path (parent directory will be created)
        """
        path.parent.mkdir(parents=True, exist_ok=True)

    def _write_json(
            self,
            data: Dict[str, Any],
            path: Path,
            indent: int = 2
    ) -> None:
        """
        Write data to a JSON file.

        Args:
            data: Data to write
            path: Output file path
            indent: JSON indentation level
        """
        self._ensure_output_dir(path)
        path.write_text(
            json.dumps(data, indent=indent, default=str, ensure_ascii=False),
            encoding='utf-8'
        )
        self.logger.info(f"JSON report saved to: {path}")

    def _write_html(self, content: str, path: Path) -> None:
        """
        Write HTML content to a file.

        Args:
            content: HTML content
            path: Output file path
        """
        self._ensure_output_dir(path)
        path.write_text(content, encoding='utf-8')
        self.logger.info(f"HTML report saved to: {path}")

    def _write_text(self, content: str, path: Path) -> None:
        """
        Write plain text to a file.

        Args:
            content: Text content
            path: Output file path
        """
        self._ensure_output_dir(path)
        path.write_text(content, encoding='utf-8')
        self.logger.info(f"Text report saved to: {path}")

    def _write_xml(self, content: str, path: Path) -> None:
        """
        Write XML content to a file.

        Args:
            content: XML content
            path: Output file path
        """
        self._ensure_output_dir(path)
        path.write_text(content, encoding='utf-8')
        self.logger.info(f"XML report saved to: {path}")

    def _get_html_template(self) -> str:
        """
        Get basic HTML report template.

        Returns:
            HTML template string with {title}, {content}, {metadata} placeholders
        """
        return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background: #f5f5f5;
            color: #333;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #2c3e50;
            border-bottom: 2px solid #3498db;
            padding-bottom: 10px;
        }}
        .metadata {{
            background: #ecf0f1;
            padding: 10px;
            border-radius: 4px;
            margin-bottom: 20px;
            font-size: 0.9em;
            color: #7f8c8d;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background: #3498db;
            color: white;
        }}
        tr:hover {{
            background: #f5f5f5;
        }}
        .success {{ color: #27ae60; }}
        .warning {{ color: #f39c12; }}
        .error {{ color: #e74c3c; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{title}</h1>
        <div class="metadata">{metadata}</div>
        <div class="content">{content}</div>
    </div>
</body>
</html>"""

    def _render_html(
            self,
            content: str,
            metadata: Optional[ReportMetadata] = None
    ) -> str:
        """
        Render content using the HTML template.

        Args:
            content: Main content HTML
            metadata: Optional report metadata

        Returns:
            Complete HTML document
        """
        meta = metadata or self._create_metadata()
        meta_str = f"Generated: {meta.generated_at.strftime('%Y-%m-%d %H:%M:%S')} | Generator: {meta.generator}"

        return self._get_html_template().format(
            title=meta.title,
            metadata=meta_str,
            content=content
        )
