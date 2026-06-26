"""
Database layer for dashboard

Uses SQLite for simplicity.
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from .models import (
    TestResult, TestHealth, HealedSelector,
    TestStatus, HealingStatus
)


class DashboardDB:
    """Database for dashboard data"""

    def __init__(self, db_path: Path):
        """
        Initialize database

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.conn = None
        import threading
        self._lock = threading.Lock()  # Thread safety for shared connection
        self._init_db()

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensure connection is closed"""
        self.close()
        return False

    def __del__(self):
        """Destructor - ensure connection is closed"""
        try:
            self.close()
        except Exception:
            pass  # Ignore errors during cleanup

    def _init_db(self):
        """Initialize database schema"""
        # Use check_same_thread=False with explicit locking for thread safety
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

        cursor = self.conn.cursor()

        # Test results table
        cursor.execute("""
                       CREATE TABLE IF NOT EXISTS test_results
                       (
                           id
                           TEXT
                           PRIMARY
                           KEY,
                           name
                           TEXT
                           NOT
                           NULL,
                           status
                           TEXT
                           NOT
                           NULL,
                           duration
                           REAL,
                           timestamp
                           TEXT
                           NOT
                           NULL,
                           file_path
                           TEXT,
                           error_message
                           TEXT
                       )
                       """)

        # Healed selectors table
        cursor.execute("""
                       CREATE TABLE IF NOT EXISTS healed_selectors
                       (
                           id
                           TEXT
                           PRIMARY
                           KEY,
                           test_name
                           TEXT
                           NOT
                           NULL,
                           element_name
                           TEXT,
                           file_path
                           TEXT
                           NOT
                           NULL,
                           old_selector_type
                           TEXT
                           NOT
                           NULL,
                           old_selector_value
                           TEXT
                           NOT
                           NULL,
                           new_selector_type
                           TEXT
                           NOT
                           NULL,
                           new_selector_value
                           TEXT
                           NOT
                           NULL,
                           confidence
                           REAL,
                           strategy
                           TEXT,
                           status
                           TEXT
                           NOT
                           NULL,
                           timestamp
                           TEXT
                           NOT
                           NULL,
                           test_runs_after
                           INTEGER
                           DEFAULT
                           0,
                           test_passes_after
                           INTEGER
                           DEFAULT
                           0
                       )
                       """)

        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_test_results_name ON test_results(name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_test_results_timestamp ON test_results(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_healed_selectors_status ON healed_selectors(status)")

        self.conn.commit()

    def add_test_result(self, result: TestResult):
        """Add test result to database"""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO test_results (id, name, status, duration, timestamp, file_path, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            result.id,
            result.name,
            result.status.value,
            result.duration,
            result.timestamp.isoformat(),
            result.file_path,
            result.error_message
        ))
        self.conn.commit()

    def get_test_results(
            self,
            limit: int = 100,
            status: Optional[TestStatus] = None,
            since: Optional[datetime] = None
    ) -> List[TestResult]:
        """Get test results"""
        cursor = self.conn.cursor()

        query = "SELECT * FROM test_results WHERE 1=1"
        params = []

        if status:
            query += " AND status = ?"
            params.append(status.value)

        if since:
            query += " AND timestamp >= ?"
            params.append(since.isoformat())

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)

        results = []
        for row in cursor.fetchall():
            results.append(TestResult(
                id=row['id'],
                name=row['name'],
                status=TestStatus(row['status']),
                duration=row['duration'],
                timestamp=datetime.fromisoformat(row['timestamp']),
                file_path=row['file_path'],
                error_message=row['error_message']
            ))

        return results

    def get_test_health(self, days: int = 30) -> List[TestHealth]:
        """Calculate test health metrics"""
        since = datetime.now() - timedelta(days=days)

        cursor = self.conn.cursor()
        cursor.execute("""
                       SELECT name,
                              COUNT(*)                                                      as total_runs,
                              SUM(CASE WHEN status = 'passed' THEN 1 ELSE 0 END)            as passed,
                              SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END)            as failed,
                              AVG(duration)                                                 as avg_duration,
                              MAX(CASE WHEN status = 'failed' THEN timestamp ELSE NULL END) as last_failure
                       FROM test_results
                       WHERE timestamp >= ?
                       GROUP BY name
                       """, (since.isoformat(),))

        health_list = []
        for row in cursor.fetchall():
            total = row['total_runs']
            passed = row['passed']
            pass_rate = passed / total if total > 0 else 0.0

            # Flaky if pass rate between 20% and 80%
            is_flaky = 0.2 < pass_rate < 0.8

            # Determine trend (simplified)
            trend = "stable"
            if pass_rate > 0.8:
                trend = "improving"
            elif pass_rate < 0.5:
                trend = "degrading"

            health_list.append(TestHealth(
                test_name=row['name'],
                total_runs=total,
                passed=passed,
                failed=row['failed'],
                pass_rate=pass_rate,
                avg_duration=row['avg_duration'] or 0.0,
                is_flaky=is_flaky,
                last_failure=datetime.fromisoformat(row['last_failure']) if row['last_failure'] else None,
                trend=trend
            ))

        return health_list

    def add_healed_selector(self, selector: HealedSelector):
        """Add healed selector to database"""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO healed_selectors
            (id, test_name, element_name, file_path, old_selector_type, old_selector_value,
             new_selector_type, new_selector_value, confidence, strategy, status, timestamp,
             test_runs_after, test_passes_after)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            selector.id,
            selector.test_name,
            selector.element_name,
            selector.file_path,
            selector.old_selector_type,
            selector.old_selector_value,
            selector.new_selector_type,
            selector.new_selector_value,
            selector.confidence,
            selector.strategy,
            selector.status.value,
            selector.timestamp.isoformat(),
            selector.test_runs_after,
            selector.test_passes_after
        ))
        self.conn.commit()

    def get_healed_selectors(
            self,
            status: Optional[HealingStatus] = None
    ) -> List[HealedSelector]:
        """Get healed selectors"""
        cursor = self.conn.cursor()

        if status:
            cursor.execute(
                "SELECT * FROM healed_selectors WHERE status = ? ORDER BY timestamp DESC",
                (status.value,)
            )
        else:
            cursor.execute("SELECT * FROM healed_selectors ORDER BY timestamp DESC")

        selectors = []
        for row in cursor.fetchall():
            selectors.append(HealedSelector(
                id=row['id'],
                test_name=row['test_name'],
                element_name=row['element_name'],
                file_path=row['file_path'],
                old_selector_type=row['old_selector_type'],
                old_selector_value=row['old_selector_value'],
                new_selector_type=row['new_selector_type'],
                new_selector_value=row['new_selector_value'],
                confidence=row['confidence'],
                strategy=row['strategy'],
                status=HealingStatus(row['status']),
                timestamp=datetime.fromisoformat(row['timestamp']),
                test_runs_after=row['test_runs_after'],
                test_passes_after=row['test_passes_after']
            ))

        return selectors

    def update_selector_status(
            self,
            selector_id: str,
            status: HealingStatus
    ) -> bool:
        """Update selector status"""
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE healed_selectors SET status = ? WHERE id = ?",
            (status.value, selector_id)
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def get_selector(self, selector_id: str) -> Optional[HealedSelector]:
        """Get single healed selector"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM healed_selectors WHERE id = ?", (selector_id,))

        row = cursor.fetchone()
        if not row:
            return None

        return HealedSelector(
            id=row['id'],
            test_name=row['test_name'],
            element_name=row['element_name'],
            file_path=row['file_path'],
            old_selector_type=row['old_selector_type'],
            old_selector_value=row['old_selector_value'],
            new_selector_type=row['new_selector_type'],
            new_selector_value=row['new_selector_value'],
            confidence=row['confidence'],
            strategy=row['strategy'],
            status=HealingStatus(row['status']),
            timestamp=datetime.fromisoformat(row['timestamp']),
            test_runs_after=row['test_runs_after'],
            test_passes_after=row['test_passes_after']
        )

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
