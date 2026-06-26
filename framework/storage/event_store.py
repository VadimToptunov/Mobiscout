"""
Event Store - SQLite-based storage for observation events

Stores events collected by Observe SDK for later analysis and code generation.
"""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import List, Optional, Dict, Any, Generator


class EventStore:
    """
    SQLite-based event storage

    Features:
    - Store events from JSON files
    - Query events by session, screen, type
    - Support for event replay
    - Fast indexed queries
    """

    def __init__(self, db_path: str = "observe_events.db"):
        self.db_path = Path(db_path)
        self._init_database()

    def _init_database(self):
        """Initialize database schema"""
        with self._get_connection() as conn:
            conn.executescript("""
                               CREATE TABLE IF NOT EXISTS sessions
                               (
                                   session_id
                                   TEXT
                                   PRIMARY
                                   KEY,
                                   start_time
                                   INTEGER
                                   NOT
                                   NULL,
                                   device_model
                                   TEXT,
                                   os_version
                                   TEXT,
                                   app_version
                                   TEXT,
                                   created_at
                                   TIMESTAMP
                                   DEFAULT
                                   CURRENT_TIMESTAMP
                               );

                               CREATE TABLE IF NOT EXISTS events
                               (
                                   id
                                   INTEGER
                                   PRIMARY
                                   KEY
                                   AUTOINCREMENT,
                                   session_id
                                   TEXT
                                   NOT
                                   NULL,
                                   event_type
                                   TEXT
                                   NOT
                                   NULL,
                                   timestamp
                                   INTEGER
                                   NOT
                                   NULL,
                                   screen
                                   TEXT,
                                   data
                                   TEXT
                                   NOT
                                   NULL,
                                   created_at
                                   TIMESTAMP
                                   DEFAULT
                                   CURRENT_TIMESTAMP,
                                   FOREIGN
                                   KEY
                               (
                                   session_id
                               ) REFERENCES sessions
                               (
                                   session_id
                               )
                                   );

                               CREATE INDEX IF NOT EXISTS idx_session_id ON events(session_id);
                               CREATE INDEX IF NOT EXISTS idx_event_type ON events(event_type);
                               CREATE INDEX IF NOT EXISTS idx_screen ON events(screen);
                               CREATE INDEX IF NOT EXISTS idx_timestamp ON events(timestamp);

                               CREATE TABLE IF NOT EXISTS screens
                               (
                                   id
                                   INTEGER
                                   PRIMARY
                                   KEY
                                   AUTOINCREMENT,
                                   session_id
                                   TEXT
                                   NOT
                                   NULL,
                                   screen_name
                                   TEXT
                                   NOT
                                   NULL,
                                   visit_count
                                   INTEGER
                                   DEFAULT
                                   1,
                                   first_visit
                                   INTEGER
                                   NOT
                                   NULL,
                                   last_visit
                                   INTEGER
                                   NOT
                                   NULL,
                                   UNIQUE
                               (
                                   session_id,
                                   screen_name
                               ),
                                   FOREIGN KEY
                               (
                                   session_id
                               ) REFERENCES sessions
                               (
                                   session_id
                               )
                                   );

                               CREATE TABLE IF NOT EXISTS flows
                               (
                                   id
                                   INTEGER
                                   PRIMARY
                                   KEY
                                   AUTOINCREMENT,
                                   session_id
                                   TEXT
                                   NOT
                                   NULL,
                                   from_screen
                                   TEXT
                                   NOT
                                   NULL,
                                   to_screen
                                   TEXT
                                   NOT
                                   NULL,
                                   count
                                   INTEGER
                                   DEFAULT
                                   1,
                                   avg_duration
                                   REAL,
                                   UNIQUE
                               (
                                   session_id,
                                   from_screen,
                                   to_screen
                               ),
                                   FOREIGN KEY
                               (
                                   session_id
                               ) REFERENCES sessions
                               (
                                   session_id
                               )
                                   );
                               """)

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Get database connection with context manager"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def import_from_json(self, json_path: str) -> int:
        """
        Import events from JSON file (exported by EventExporter)

        Returns number of imported events
        """
        with open(json_path, 'r') as f:
            data = json.load(f)

        events = data.get('events', [])
        count = 0

        for event in events:
            self.add_event(event)
            count += 1

        return count

    def add_event(self, event: Dict[str, Any]):
        """Add single event to store"""
        # Extract common fields
        session_id = event.get('sessionId', 'unknown')
        event_type = self._get_event_type(event)
        timestamp = event.get('timestamp', 0)
        screen = event.get('screen') or event.get('toScreen') or event.get('fromScreen')

        with self._get_connection() as conn:
            # Ensure session exists
            self._ensure_session(conn, session_id, event)

            # Insert event
            conn.execute("""
                         INSERT INTO events (session_id, event_type, timestamp, screen, data)
                         VALUES (?, ?, ?, ?, ?)
                         """, (session_id, event_type, timestamp, screen, json.dumps(event)))

            # Update screens and flows
            if event_type == 'navigation':
                self._update_navigation_stats(conn, session_id, event)

    def _ensure_session(self, conn: sqlite3.Connection, session_id: str, event: Dict[str, Any]):
        """Ensure session record exists"""
        result = conn.execute(
            "SELECT session_id FROM sessions WHERE session_id = ?",
            (session_id,)
        ).fetchone()

        if not result:
            conn.execute("""
                         INSERT INTO sessions (session_id, start_time, device_model, os_version, app_version)
                         VALUES (?, ?, ?, ?, ?)
                         """, (
                             session_id,
                             event.get('timestamp', 0),
                             event.get('deviceModel', 'unknown'),
                             event.get('osVersion', 'unknown'),
                             event.get('appVersion', 'unknown')
                         ))

    def _get_event_type(self, event: Dict[str, Any]) -> str:
        """Determine event type from event data"""
        if 'actionType' in event:
            return 'ui'
        elif 'navType' in event or 'toScreen' in event:
            return 'navigation'
        elif 'method' in event and 'url' in event:
            return 'network'
        elif 'eventType' in event:
            return event['eventType']
        else:
            return 'unknown'

    def _update_navigation_stats(self, conn: sqlite3.Connection, session_id: str, event: Dict[str, Any]):
        """Update screen and flow statistics"""
        to_screen = event.get('toScreen')
        from_screen = event.get('fromScreen')
        timestamp = event.get('timestamp', 0)

        if to_screen:
            # Update screen visit
            conn.execute("""
                         INSERT INTO screens (session_id, screen_name, visit_count, first_visit, last_visit)
                         VALUES (?, ?, 1, ?, ?) ON CONFLICT(session_id, screen_name) DO
                         UPDATE SET
                             visit_count = visit_count + 1,
                             last_visit = ?
                         """, (session_id, to_screen, timestamp, timestamp, timestamp))

        if from_screen and to_screen:
            # Update flow
            conn.execute("""
                         INSERT INTO flows (session_id, from_screen, to_screen, count)
                         VALUES (?, ?, ?, 1) ON CONFLICT(session_id, from_screen, to_screen) DO
                         UPDATE SET
                             count = count + 1
                         """, (session_id, from_screen, to_screen))

    def get_sessions(self) -> List[Dict[str, Any]]:
        """Get all sessions"""
        with self._get_connection() as conn:
            rows = conn.execute("""
                                SELECT s.*, COUNT(e.id) as event_count
                                FROM sessions s
                                         LEFT JOIN events e ON s.session_id = e.session_id
                                GROUP BY s.session_id
                                ORDER BY s.start_time DESC
                                """).fetchall()

            return [dict(row) for row in rows]

    def get_events(
            self,
            session_id: Optional[str] = None,
            event_type: Optional[str] = None,
            screen: Optional[str] = None,
            limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Query events with filters"""
        query = "SELECT * FROM events WHERE 1=1"
        params = []

        if session_id:
            query += " AND session_id = ?"
            params.append(session_id)

        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)

        if screen:
            query += " AND screen = ?"
            params.append(screen)

        query += " ORDER BY timestamp ASC LIMIT ?"
        params.append(limit)

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()

            events = []
            for row in rows:
                event = dict(row)
                event['data'] = json.loads(event['data'])
                events.append(event)

            return events

    def get_screens(self, session_id: str) -> List[Dict[str, Any]]:
        """Get all screens visited in session"""
        with self._get_connection() as conn:
            rows = conn.execute("""
                                SELECT *
                                FROM screens
                                WHERE session_id = ?
                                ORDER BY visit_count DESC
                                """, (session_id,)).fetchall()

            return [dict(row) for row in rows]

    def get_flows(self, session_id: str) -> List[Dict[str, Any]]:
        """Get all navigation flows in session"""
        with self._get_connection() as conn:
            rows = conn.execute("""
                                SELECT *
                                FROM flows
                                WHERE session_id = ?
                                ORDER BY count DESC
                                """, (session_id,)).fetchall()

            return [dict(row) for row in rows]

    def get_ui_events_by_screen(self, session_id: str, screen: str) -> List[Dict[str, Any]]:
        """Get all UI events for specific screen"""
        return self.get_events(session_id=session_id, event_type='ui', screen=screen)

    def get_network_events(self, session_id: str) -> List[Dict[str, Any]]:
        """Get all network events"""
        return self.get_events(session_id=session_id, event_type='network')

    def get_event_timeline(self, session_id: str) -> List[Dict[str, Any]]:
        """Get complete event timeline for session"""
        return self.get_events(session_id=session_id, limit=10000)

    def clear_session(self, session_id: str):
        """Delete all data for session"""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM flows WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM screens WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM events WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))

    def clear_all(self):
        """Clear all data"""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM flows")
            conn.execute("DELETE FROM screens")
            conn.execute("DELETE FROM events")
            conn.execute("DELETE FROM sessions")

    def get_statistics(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Get statistics about stored events"""
        with self._get_connection() as conn:
            if session_id:
                # query_suffix =  # Unused "WHERE session_id = ?"
                params = (session_id,)
            else:
                # query_suffix =  # Unused ""
                params = ()

            # Event counts by type
            event_counts = {}
            rows = conn.execute("""
                                SELECT event_type, COUNT(*) as count
                                FROM events {query_suffix}
                                GROUP BY event_type
                                """, params).fetchall()

            for row in rows:
                event_counts[row['event_type']] = row['count']

            # Total stats
            total_events = sum(event_counts.values())
            total_sessions = conn.execute("SELECT COUNT(*) as count FROM sessions").fetchone()['count']

            return {
                'total_sessions': total_sessions,
                'total_events': total_events,
                'events_by_type': event_counts
            }
