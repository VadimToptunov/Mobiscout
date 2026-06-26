"""
Performance Profiler - CPU, memory, and execution profiling
"""

import cProfile
import io
import json
import pstats
import time
import tracemalloc
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable


@dataclass
class ProfilerConfig:
    """Configuration for performance profiling"""
    profile_cpu: bool = True
    profile_memory: bool = True
    profile_time: bool = True
    top_functions: int = 20
    memory_snapshots: int = 10
    sort_by: str = "cumulative"  # time, cumulative, calls


@dataclass
class ProfileResult:
    """Results from performance profiling"""
    test_path: str
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    cpu_profile: Optional[Dict[str, Any]] = None
    memory_profile: Optional[Dict[str, Any]] = None
    time_profile: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "test_path": self.test_path,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "duration_seconds": self.duration_seconds,
            "cpu_profile": self.cpu_profile,
            "memory_profile": self.memory_profile,
            "time_profile": self.time_profile,
        }


class PerformanceProfiler:
    """Performance profiling for tests"""

    def __init__(self, config: ProfilerConfig) -> None:
        self.config = config
        self.profiler: Optional[cProfile.Profile] = None
        self.memory_snapshots: List[tracemalloc.Snapshot] = []

    def profile_test(
            self,
            test_path: Path,
            test_function: Callable[[], Any],
            progress_callback: Optional[Callable[[str], None]] = None,
    ) -> ProfileResult:
        """Profile a test function"""
        start_time = datetime.now()

        if progress_callback:
            progress_callback(f"Starting profiling: {test_path}")

        # Start memory profiling
        if self.config.profile_memory:
            tracemalloc.start()

        # Start CPU profiling
        if self.config.profile_cpu:
            self.profiler = cProfile.Profile()
            self.profiler.enable()

        # Run test with time profiling
        test_start = time.perf_counter()
        try:
            test_function()
            success = True
        except (RuntimeError, OSError, ValueError, AttributeError, TypeError) as e:
            if progress_callback:
                progress_callback(f"Test failed: {e}")
            success = False
        test_duration = time.perf_counter() - test_start

        # Stop CPU profiling
        if self.config.profile_cpu:
            self.profiler.disable()

        # Capture memory snapshot
        if self.config.profile_memory:
            snapshot = tracemalloc.take_snapshot()
            self.memory_snapshots.append(snapshot)
            tracemalloc.stop()

        end_time = datetime.now()

        # Generate results
        cpu_profile = self._generate_cpu_profile() if self.config.profile_cpu else None
        memory_profile = self._generate_memory_profile() if self.config.profile_memory else None
        time_profile = {
            "duration_seconds": test_duration,
            "success": success,
        }

        return ProfileResult(
            test_path=str(test_path),
            start_time=start_time,
            end_time=end_time,
            duration_seconds=(end_time - start_time).total_seconds(),
            cpu_profile=cpu_profile,
            memory_profile=memory_profile,
            time_profile=time_profile,
        )

    def _generate_cpu_profile(self) -> Dict[str, Any]:
        """Generate CPU profile report"""
        if not self.profiler:
            return {}

        # Capture stats
        s = io.StringIO()
        ps = pstats.Stats(self.profiler, stream=s)
        ps.sort_stats(self.config.sort_by)
        ps.print_stats(self.config.top_functions)

        # Parse stats
        stats = ps.stats  # type: ignore[attr-defined]  # pstats.Stats has dynamic attrs
        top_functions = []

        for func, (cc, nc, tt, ct, callers) in list(stats.items())[:self.config.top_functions]:
            filename, line, name = func
            top_functions.append({
                "function": name,
                "filename": filename,
                "line": line,
                "calls": nc,
                "total_time": tt,
                "cumulative_time": ct,
                "time_per_call": tt / nc if nc > 0 else 0,
            })

        return {
            "top_functions": top_functions,
            "total_calls": ps.total_calls,  # type: ignore[attr-defined]
            "sort_by": self.config.sort_by,
            "raw_output": s.getvalue(),
        }

    def _generate_memory_profile(self) -> Dict[str, Any]:
        """Generate memory profile report"""
        if not self.memory_snapshots:
            return {}

        snapshot = self.memory_snapshots[-1]
        top_stats = snapshot.statistics("lineno")

        top_allocations = []
        for stat in top_stats[:self.config.top_functions]:
            top_allocations.append({
                "filename": stat.traceback.format()[0] if stat.traceback else "unknown",
                "size_bytes": stat.size,
                "size_mb": stat.size / 1024 / 1024,
                "count": stat.count,
            })

        # Calculate total memory
        total_size = sum(stat.size for stat in top_stats)

        return {
            "top_allocations": top_allocations,
            "total_size_bytes": total_size,
            "total_size_mb": total_size / 1024 / 1024,
            "num_allocations": len(top_stats),
        }

    def compare_profiles(
            self,
            baseline: ProfileResult,
            current: ProfileResult,
    ) -> Dict[str, Any]:
        """Compare two profile results"""
        comparison: Dict[str, Any] = {
            "baseline": {
                "test_path": baseline.test_path,
                "duration": baseline.duration_seconds,
            },
            "current": {
                "test_path": current.test_path,
                "duration": current.duration_seconds,
            },
            "changes": {},
        }

        # Compare duration
        duration_diff = current.duration_seconds - baseline.duration_seconds
        duration_pct = (duration_diff / baseline.duration_seconds * 100) if baseline.duration_seconds > 0 else 0

        comparison["changes"]["duration"] = {
            "absolute": duration_diff,
            "percentage": duration_pct,
            "regression": duration_diff > 0,
        }

        # Compare memory
        if baseline.memory_profile and current.memory_profile:
            baseline_mem = baseline.memory_profile.get("total_size_mb", 0)
            current_mem = current.memory_profile.get("total_size_mb", 0)
            mem_diff = current_mem - baseline_mem
            mem_pct = (mem_diff / baseline_mem * 100) if baseline_mem > 0 else 0

            comparison["changes"]["memory"] = {
                "absolute_mb": mem_diff,
                "percentage": mem_pct,
                "regression": mem_diff > 0,
            }

        return comparison

    def save_profile(self, result: ProfileResult, output_path: Path) -> None:
        """Save profile to file"""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            json.dump(result.to_dict(), f, indent=2)

    def generate_report(self, result: ProfileResult, output_path: Path) -> None:
        """Generate HTML report"""
        html = self._generate_html_report(result)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            f.write(html)

    def _generate_html_report(self, result: ProfileResult) -> str:
        """Generate HTML report"""
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Performance Profile - {result.test_path}</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 20px;
            background: #f5f5f5;
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
            color: #333;
            border-bottom: 2px solid #007bff;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #555;
            margin-top: 30px;
        }}
        .metric {{
            display: inline-block;
            margin: 10px 20px 10px 0;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 4px;
        }}
        .metric-label {{
            font-size: 12px;
            color: #666;
            text-transform: uppercase;
        }}
        .metric-value {{
            font-size: 24px;
            font-weight: bold;
            color: #007bff;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background: #007bff;
            color: white;
            font-weight: bold;
        }}
        tr:hover {{
            background: #f8f9fa;
        }}
        .code {{
            background: #f4f4f4;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: monospace;
            font-size: 13px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Performance Profile Report</h1>
        <p><strong>Test:</strong> {result.test_path}</p>
        <p><strong>Duration:</strong> {result.start_time.strftime('%Y-%m-%d %H:%M:%S')} - {result.end_time.strftime('%H:%M:%S')}</p>

        <div class="metrics">
            <div class="metric">
                <div class="metric-label">Total Duration</div>
                <div class="metric-value">{result.duration_seconds:.2f}s</div>
            </div>
"""

        # Memory metrics
        if result.memory_profile:
            total_mb = result.memory_profile.get("total_size_mb", 0)
            num_allocs = result.memory_profile.get("num_allocations", 0)
            html += f"""
            <div class="metric">
                <div class="metric-label">Memory Usage</div>
                <div class="metric-value">{total_mb:.2f} MB</div>
            </div>
            <div class="metric">
                <div class="metric-label">Allocations</div>
                <div class="metric-value">{num_allocs:,}</div>
            </div>
"""

        html += "</div>"

        # CPU Profile
        if result.cpu_profile:
            html += "<h2>CPU Profile - Top Functions</h2>"
            html += "<table>"
            html += "<tr><th>Function</th><th>Calls</th><th>Total Time</th><th>Time/Call</th><th>Cumulative</th></tr>"

            for func in result.cpu_profile.get("top_functions", []):
                html += f"""
                <tr>
                    <td><span class="code">{func['function']}</span><br><small>{func['filename']}:{func['line']}</small></td>
                    <td>{func['calls']:,}</td>
                    <td>{func['total_time']:.4f}s</td>
                    <td>{func['time_per_call']:.6f}s</td>
                    <td>{func['cumulative_time']:.4f}s</td>
                </tr>
"""
            html += "</table>"

        # Memory Profile
        if result.memory_profile:
            html += "<h2>Memory Profile - Top Allocations</h2>"
            html += "<table>"
            html += "<tr><th>Location</th><th>Size (MB)</th><th>Count</th></tr>"

            for alloc in result.memory_profile.get("top_allocations", []):
                html += f"""
                <tr>
                    <td><span class="code">{alloc['filename']}</span></td>
                    <td>{alloc['size_mb']:.2f}</td>
                    <td>{alloc['count']:,}</td>
                </tr>
"""
            html += "</table>"

        html += """
    </div>
</body>
</html>
"""
        return html
