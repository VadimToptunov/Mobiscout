"""
ML Analytics Dashboard

Generates visual analytics dashboard for ML model performance,
test coverage, and selector stability trends.
"""

import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

# Check for plotly availability
try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False
    logger.warning("plotly not available - dashboard generation disabled")


class AnalyticsDashboard:
    """
    Generate visual analytics dashboards for:
    - ML model performance metrics
    - Test coverage analysis
    - Selector stability over time
    """

    def __init__(self):
        self.report_data = {}

    def generate_execution_report(self, test_results: List[Dict[str, Any]], output_path: Path):
        """
        Generate test execution report with charts.

        Args:
            test_results: List of test execution results
            output_path: Output HTML file path
        """
        if not PLOTLY_AVAILABLE:
            raise RuntimeError("plotly required for dashboard generation")

        # Calculate metrics
        total_tests = len(test_results)
        passed = sum(1 for r in test_results if r.get("status") == "passed")
        failed = sum(1 for r in test_results if r.get("status") == "failed")
        skipped = sum(1 for r in test_results if r.get("status") == "skipped")

        pass_rate = (passed / total_tests * 100) if total_tests > 0 else 0

        # Create subplots
        fig = make_subplots(
            rows=2,
            cols=2,
            subplot_titles=(
                "Test Results Distribution",
                "Pass Rate Trend",
                "Execution Time by Test",
                "Failure Categories",
            ),
            specs=[[{"type": "pie"}, {"type": "scatter"}], [{"type": "bar"}, {"type": "pie"}]],
        )

        # 1. Results pie chart
        fig.add_trace(
            go.Pie(
                labels=["Passed", "Failed", "Skipped"],
                values=[passed, failed, skipped],
                marker=dict(colors=["#28a745", "#dc3545", "#ffc107"]),
                hole=0.3,
            ),
            row=1,
            col=1,
        )

        # 2. Pass rate trend (mock data for now)
        runs = list(range(1, 11))
        pass_rates = [85, 87, 86, 90, 89, 91, 88, 92, 91, pass_rate]

        fig.add_trace(
            go.Scatter(
                x=runs, y=pass_rates, mode="lines+markers", line=dict(color="#28a745", width=2), marker=dict(size=8)
            ),
            row=1,
            col=2,
        )

        # 3. Execution time bar chart
        test_names = [r.get("name", f"Test {i}") for i, r in enumerate(test_results[:10])]
        exec_times = [r.get("duration", 0) for r in test_results[:10]]

        fig.add_trace(go.Bar(x=test_names, y=exec_times, marker=dict(color="#007bff")), row=2, col=1)

        # 4. Failure categories
        failure_reasons = defaultdict(int)
        for result in test_results:
            if result.get("status") == "failed":
                reason = result.get("failure_reason", "Unknown")
                failure_reasons[reason] += 1

        if failure_reasons:
            fig.add_trace(
                go.Pie(
                    labels=list(failure_reasons.keys()),
                    values=list(failure_reasons.values()),
                    marker=dict(colors=["#dc3545", "#fd7e14", "#ffc107"]),
                ),
                row=2,
                col=2,
            )

        # Update layout
        fig.update_layout(
            title_text=f"Test Execution Dashboard - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            showlegend=True,
            height=800,
        )

        # Generate HTML with summary metrics
        summary_html = f"""
        <div style="background: #f8f9fa; padding: 20px; margin: 20px 0; border-radius: 8px;">
            <h2>📊 Summary Metrics</h2>
            <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin-top: 20px;">
                <div style="background: white; padding: 15px; border-radius: 5px; text-align: center;">
                    <div style="font-size: 32px; font-weight: bold; color: #007bff;">{total_tests}</div>
                    <div style="color: #6c757d; margin-top: 5px;">Total Tests</div>
                </div>
                <div style="background: white; padding: 15px; border-radius: 5px; text-align: center;">
                    <div style="font-size: 32px; font-weight: bold; color: #28a745;">{passed}</div>
                    <div style="color: #6c757d; margin-top: 5px;">Passed</div>
                </div>
                <div style="background: white; padding: 15px; border-radius: 5px; text-align: center;">
                    <div style="font-size: 32px; font-weight: bold; color: #dc3545;">{failed}</div>
                    <div style="color: #6c757d; margin-top: 5px;">Failed</div>
                </div>
                <div style="background: white; padding: 15px; border-radius: 5px; text-align: center;">
                    <div style="font-size: 32px; font-weight: bold; color: #17a2b8;">{pass_rate:.1f}%</div>
                    <div style="color: #6c757d; margin-top: 5px;">Pass Rate</div>
                </div>
            </div>
        </div>
        """

        # Generate full HTML
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Test Execution Dashboard</title>
            <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                    margin: 0;
                    padding: 20px;
                    background: #f5f5f5;
                }}
                h1 {{
                    color: #333;
                }}
            </style>
        </head>
        <body>
            <h1>🚀 Test Execution Dashboard</h1>
            {summary_html}
            {fig.to_html(include_plotlyjs=False, div_id="dashboard")}
        </body>
        </html>
        """

        # Save report
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html_content)

        logger.info(f"Execution report saved to {output_path}")

    def generate_selector_stability_report(self, selector_history: List[Dict[str, Any]], output_path: Path):
        """
        Generate selector stability trend report.

        Args:
            selector_history: List of selector stability data over time
            output_path: Output HTML file path
        """
        if not PLOTLY_AVAILABLE:
            raise RuntimeError("plotly required for dashboard generation")

        # Parse history
        timestamps = [h["timestamp"] for h in selector_history]
        stability_scores = [h["avg_stability"] for h in selector_history]
        failures = [h["selector_failures"] for h in selector_history]

        # Create subplots
        fig = make_subplots(
            rows=2,
            cols=1,
            subplot_titles=("Selector Stability Trend", "Selector Failures Over Time"),
            vertical_spacing=0.15,
        )

        # Stability trend
        fig.add_trace(
            go.Scatter(
                x=timestamps,
                y=stability_scores,
                mode="lines+markers",
                name="Stability Score",
                line=dict(color="#28a745", width=2),
                marker=dict(size=6),
            ),
            row=1,
            col=1,
        )

        # Failures trend
        fig.add_trace(
            go.Scatter(
                x=timestamps,
                y=failures,
                mode="lines+markers",
                name="Failures",
                line=dict(color="#dc3545", width=2),
                marker=dict(size=6),
                fill="tozeroy",
            ),
            row=2,
            col=1,
        )

        fig.update_layout(title_text="Selector Stability Analysis", showlegend=True, height=700)

        # Generate HTML
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Selector Stability Report</title>
            <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
        </head>
        <body>
            <h1>Selector Stability Report</h1>
            {fig.to_html(include_plotlyjs=False)}
        </body>
        </html>
        """

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html_content)

        logger.info(f"Selector stability report saved to {output_path}")


def generate_ml_performance_dashboard(model_metrics: Dict[str, Any], output_path: Path):
    """
    Generate ML model performance dashboard.

    Args:
        model_metrics: Dict with accuracy, precision, recall, f1, etc.
        output_path: Output HTML file path
    """
    if not PLOTLY_AVAILABLE:
        raise RuntimeError("plotly required for dashboard generation")

    # Create metrics bar chart
    fig = go.Figure()

    metrics_names = list(model_metrics.keys())
    metrics_values = list(model_metrics.values())

    fig.add_trace(
        go.Bar(x=metrics_names, y=metrics_values, marker=dict(color=["#28a745", "#007bff", "#17a2b8", "#ffc107"]))
    )

    fig.update_layout(title="ML Model Performance Metrics", yaxis_title="Score", yaxis=dict(range=[0, 1]), height=500)

    # Generate HTML
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>ML Performance Dashboard</title>
        <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    </head>
    <body>
        <h1>ML Model Performance</h1>
        {fig.to_html(include_plotlyjs=False)}
    </body>
    </html>
    """

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_content)

    logger.info(f"ML performance dashboard saved to {output_path}")
