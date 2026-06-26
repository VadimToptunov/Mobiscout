"""
Dashboard server

FastAPI-based web server for test maintenance dashboard.
"""

from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

from .database import DashboardDB
from .models import TestStatus, HealingStatus, DashboardStats


class DashboardServer:
    """
    Web server for maintenance dashboard
    """

    def __init__(self, repo_path: Path, db_path: Optional[Path] = None):
        """
        Initialize dashboard server

        Args:
            repo_path: Path to repository root
            db_path: Path to SQLite database (defaults to repo/.dashboard.db)
        """
        self.repo_path = repo_path
        self.db_path = db_path or (repo_path / '.dashboard.db')
        self.db = DashboardDB(self.db_path)

        # Create FastAPI app
        self.app = FastAPI(title="Test Maintenance Dashboard")
        self._setup_routes()

    def _setup_routes(self):
        """Setup API routes"""

        @self.app.get("/")
        async def root():
            """Serve main dashboard page"""
            return HTMLResponse(self._get_dashboard_html())

        @self.app.get("/api/stats")
        async def get_stats():
            """Get dashboard statistics"""
            health = self.db.get_test_health(days=30)

            total_tests = len(health)
            passing = len([h for h in health if h.pass_rate >= 0.8])
            failing = len([h for h in health if h.pass_rate < 0.5])
            flaky = len([h for h in health if h.is_flaky])

            pending_selectors = len(self.db.get_healed_selectors(HealingStatus.PENDING))
            approved_selectors = len(self.db.get_healed_selectors(HealingStatus.APPROVED))

            avg_pass_rate = sum(h.pass_rate for h in health) / total_tests if total_tests > 0 else 0.0

            stats = DashboardStats(
                total_tests=total_tests,
                passing_tests=passing,
                failing_tests=failing,
                flaky_tests=flaky,
                healed_selectors_pending=pending_selectors,
                healed_selectors_approved=approved_selectors,
                avg_pass_rate=avg_pass_rate
            )

            return JSONResponse(stats.to_dict())

        @self.app.get("/api/tests")
        async def get_tests(limit: int = 100, status: Optional[str] = None):
            """Get test results"""
            test_status = TestStatus(status) if status else None
            results = self.db.get_test_results(limit=limit, status=test_status)
            return JSONResponse([r.to_dict() for r in results])

        @self.app.get("/api/tests/health")
        async def get_test_health(days: int = 30):
            """Get test health metrics"""
            health = self.db.get_test_health(days=days)
            return JSONResponse([h.to_dict() for h in health])

        @self.app.get("/api/selectors")
        async def get_selectors(status: Optional[str] = None):
            """Get healed selectors"""
            selector_status = HealingStatus(status) if status else None
            selectors = self.db.get_healed_selectors(status=selector_status)
            return JSONResponse([s.to_dict() for s in selectors])

        @self.app.post("/api/selectors/{selector_id}/approve")
        async def approve_selector(selector_id: str):
            """Approve healed selector"""
            selector = self.db.get_selector(selector_id)
            if not selector:
                raise HTTPException(status_code=404, detail="Selector not found")

            # Update status
            success = self.db.update_selector_status(selector_id, HealingStatus.APPROVED)
            if not success:
                raise HTTPException(status_code=500, detail="Failed to update status")

            # In real implementation, this would trigger actual file update and git commit
            # For now, just return success
            return JSONResponse({"status": "approved", "selector_id": selector_id})

        @self.app.post("/api/selectors/{selector_id}/reject")
        async def reject_selector(selector_id: str):
            """Reject healed selector"""
            selector = self.db.get_selector(selector_id)
            if not selector:
                raise HTTPException(status_code=404, detail="Selector not found")

            success = self.db.update_selector_status(selector_id, HealingStatus.REJECTED)
            if not success:
                raise HTTPException(status_code=500, detail="Failed to update status")

            return JSONResponse({"status": "rejected", "selector_id": selector_id})

        @self.app.get("/api/selectors/{selector_id}")
        async def get_selector(selector_id: str):
            """Get single selector"""
            selector = self.db.get_selector(selector_id)
            if not selector:
                raise HTTPException(status_code=404, detail="Selector not found")

            return JSONResponse(selector.to_dict())

    def _get_dashboard_html(self) -> str:
        """Generate dashboard HTML"""
        return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Test Maintenance Dashboard</title>
    <script src="https://unpkg.com/alpinejs@3.x.x/dist/cdn.min.js" defer></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f7fa; }
        .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
        h1 { font-size: 2rem; margin-bottom: 10px; color: #2c3e50; }
        .subtitle { color: #7f8c8d; margin-bottom: 30px; }
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 40px; }
        .stat-card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .stat-value { font-size: 2.5rem; font-weight: bold; color: #3498db; }
        .stat-label { color: #7f8c8d; margin-top: 5px; }
        .tabs { display: flex; gap: 10px; margin-bottom: 20px; border-bottom: 2px solid #ecf0f1; }
        .tab { padding: 10px 20px; cursor: pointer; background: none; border: none; font-size: 1rem; color: #7f8c8d; }
        .tab.active { color: #3498db; border-bottom: 2px solid #3498db; margin-bottom: -2px; }
        .card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; }
        .table { width: 100%; border-collapse: collapse; }
        .table th { text-align: left; padding: 12px; background: #ecf0f1; font-weight: 600; }
        .table td { padding: 12px; border-bottom: 1px solid #ecf0f1; }
        .badge { display: inline-block; padding: 4px 12px; border-radius: 12px; font-size: 0.85rem; font-weight: 500; }
        .badge-success { background: #d4edda; color: #155724; }
        .badge-danger { background: #f8d7da; color: #721c24; }
        .badge-warning { background: #fff3cd; color: #856404; }
        .badge-info { background: #d1ecf1; color: #0c5460; }
        .btn { padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; font-size: 0.9rem; }
        .btn-primary { background: #3498db; color: white; }
        .btn-success { background: #27ae60; color: white; }
        .btn-danger { background: #e74c3c; color: white; }
        .btn:hover { opacity: 0.9; }
        .selector-detail { background: #f8f9fa; padding: 12px; border-radius: 4px; margin: 10px 0; font-family: monospace; }
        .confidence { font-weight: bold; }
        .confidence-high { color: #27ae60; }
        .confidence-medium { color: #f39c12; }
        .confidence-low { color: #e74c3c; }
    </style>
</head>
<body>
    <div class="container" x-data="dashboard()">
        <h1>Test Maintenance Dashboard</h1>
        <p class="subtitle">Monitor test health and review healed selectors</p>

        <!-- Stats -->
        <div class="stats">
            <div class="stat-card">
                <div class="stat-value" x-text="stats.total_tests"></div>
                <div class="stat-label">Total Tests</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" x-text="stats.passing_tests"></div>
                <div class="stat-label">Passing</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" x-text="stats.flaky_tests"></div>
                <div class="stat-label">Flaky Tests</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" x-text="stats.healed_selectors_pending"></div>
                <div class="stat-label">Pending Review</div>
            </div>
        </div>

        <!-- Tabs -->
        <div class="tabs">
            <button class="tab" :class="{ 'active': activeTab === 'health' }" @click="activeTab = 'health'">
                Test Health
            </button>
            <button class="tab" :class="{ 'active': activeTab === 'selectors' }" @click="activeTab = 'selectors'">
                Healed Selectors
            </button>
            <button class="tab" :class="{ 'active': activeTab === 'history' }" @click="activeTab = 'history'">
                History
            </button>
        </div>

        <!-- Test Health Tab -->
        <div x-show="activeTab === 'health'" class="card">
            <h2 style="margin-bottom: 20px;">Test Health (Last 30 days)</h2>
            <table class="table">
                <thead>
                    <tr>
                        <th>Test Name</th>
                        <th>Runs</th>
                        <th>Pass Rate</th>
                        <th>Avg Duration</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
                    <template x-for="test in testHealth" :key="test.test_name">
                        <tr>
                            <td x-text="test.test_name"></td>
                            <td x-text="test.total_runs"></td>
                            <td>
                                <span :class="{'badge-success': test.pass_rate >= 0.8, 'badge-danger': test.pass_rate < 0.5, 'badge-warning': test.pass_rate >= 0.5 && test.pass_rate < 0.8}"
                                      class="badge"
                                      x-text="(test.pass_rate * 100).toFixed(0) + '%'"></span>
                            </td>
                            <td x-text="test.avg_duration.toFixed(2) + 's'"></td>
                            <td>
                                <span x-show="test.is_flaky" class="badge badge-warning">Flaky</span>
                                <span x-show="!test.is_flaky && test.pass_rate >= 0.8" class="badge badge-success">Healthy</span>
                                <span x-show="!test.is_flaky && test.pass_rate < 0.5" class="badge badge-danger">Failing</span>
                            </td>
                        </tr>
                    </template>
                </tbody>
            </table>
        </div>

        <!-- Healed Selectors Tab -->
        <div x-show="activeTab === 'selectors'" class="card">
            <h2 style="margin-bottom: 20px;">Healed Selectors Pending Review</h2>
            <template x-for="selector in pendingSelectors" :key="selector.id">
                <div class="card" style="background: #f8f9fa;">
                    <div style="display: flex; justify-content: space-between; align-items: start;">
                        <div style="flex: 1;">
                            <h3 style="margin-bottom: 10px;" x-text="selector.test_name"></h3>
                            <p style="color: #7f8c8d; margin-bottom: 15px;" x-text="'Element: ' + selector.element_name"></p>

                            <div class="selector-detail">
                                <strong>Old:</strong> <span x-text="selector.old_selector.type"></span>: "<span x-text="selector.old_selector.value"></span>"
                            </div>
                            <div class="selector-detail">
                                <strong>New:</strong> <span x-text="selector.new_selector.type"></span>: "<span x-text="selector.new_selector.value"></span>"
                            </div>

                            <p style="margin-top: 10px;">
                                <span class="confidence"
                                      :class="{'confidence-high': selector.confidence >= 0.8, 'confidence-medium': selector.confidence >= 0.6, 'confidence-low': selector.confidence < 0.6}">
                                    Confidence: <span x-text="(selector.confidence * 100).toFixed(0) + '%'"></span>
                                </span>
                                <span style="margin-left: 20px; color: #7f8c8d;">Strategy: <span x-text="selector.strategy"></span></span>
                            </p>

                            <p x-show="selector.test_runs_after > 0" style="margin-top: 10px; color: #27ae60;">
                                Test runs after healing: <span x-text="selector.test_passes_after + '/' + selector.test_runs_after"></span>
                                (<span x-text="(selector.success_rate * 100).toFixed(0) + '%'"></span>)
                            </p>
                        </div>

                        <div style="display: flex; gap: 10px;">
                            <button class="btn btn-success" @click="approveSelector(selector.id)">Approve</button>
                            <button class="btn btn-danger" @click="rejectSelector(selector.id)">Reject</button>
                        </div>
                    </div>
                </div>
            </template>
            <p x-show="pendingSelectors.length === 0" style="color: #7f8c8d; text-align: center; padding: 40px;">
                No selectors pending review
            </p>
        </div>

        <!-- History Tab -->
        <div x-show="activeTab === 'history'" class="card">
            <h2 style="margin-bottom: 20px;">Recent Test Results</h2>
            <table class="table">
                <thead>
                    <tr>
                        <th>Test Name</th>
                        <th>Status</th>
                        <th>Duration</th>
                        <th>Timestamp</th>
                    </tr>
                </thead>
                <tbody>
                    <template x-for="result in testResults" :key="result.id">
                        <tr>
                            <td x-text="result.name"></td>
                            <td>
                                <span :class="{'badge-success': result.status === 'passed', 'badge-danger': result.status === 'failed', 'badge-warning': result.status === 'skipped'}"
                                      class="badge"
                                      x-text="result.status"></span>
                            </td>
                            <td x-text="result.duration.toFixed(2) + 's'"></td>
                            <td x-text="new Date(result.timestamp).toLocaleString()"></td>
                        </tr>
                    </template>
                </tbody>
            </table>
        </div>
    </div>

    <script>
        function dashboard() {
            return {
                activeTab: 'health',
                stats: {},
                testHealth: [],
                pendingSelectors: [],
                testResults: [],

                async init() {
                    await this.loadData();
                    // Refresh every 30 seconds
                    setInterval(() => this.loadData(), 30000);
                },

                async loadData() {
                    try {
                        const [statsRes, healthRes, selectorsRes, resultsRes] = await Promise.all([
                            fetch('/api/stats'),
                            fetch('/api/tests/health'),
                            fetch('/api/selectors?status=pending'),
                            fetch('/api/tests?limit=50')
                        ]);

                        this.stats = await statsRes.json();
                        this.testHealth = await healthRes.json();
                        this.pendingSelectors = await selectorsRes.json();
                        this.testResults = await resultsRes.json();
                    } catch (error) {
                        console.error('Error loading data:', error);
                    }
                },

                async approveSelector(id) {
                    try {
                        await fetch(`/api/selectors/${id}/approve`, { method: 'POST' });
                        await this.loadData();
                        alert('Selector approved!');
                    } catch (error) {
                        alert('Error approving selector');
                    }
                },

                async rejectSelector(id) {
                    if (!confirm('Are you sure you want to reject this selector?')) return;
                    try {
                        await fetch(`/api/selectors/${id}/reject`, { method: 'POST' });
                        await this.loadData();
                        alert('Selector rejected');
                    } catch (error) {
                        alert('Error rejecting selector');
                    }
                }
            }
        }
    </script>
</body>
</html>
        """

    def run(self, host: str = "0.0.0.0", port: int = 8080):
        """
        Start dashboard server

        Args:
            host: Host to bind to
            port: Port to listen on
        """
        print("\nStarting Test Maintenance Dashboard...")
        print(f"URL: http://localhost:{port}")
        print(f"Database: {self.db_path}")
        print("\nPress Ctrl+C to stop\n")

        uvicorn.run(self.app, host=host, port=port)
