import sqlite3
import json
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from src.cv_layer.schema import EventSchema

class StorageEngine:
    def __init__(self, db_path: str = "store_intelligence.db"):
        self.db_path = db_path
        self._init_db()
        
    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
        
    def _init_db(self):
        with self._get_conn() as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    store_id TEXT,
                    camera_id TEXT,
                    visitor_id TEXT,
                    event_type TEXT,
                    timestamp DATETIME,
                    zone_id TEXT,
                    dwell_ms INTEGER,
                    is_staff BOOLEAN,
                    confidence REAL,
                    queue_depth INTEGER,
                    session_seq INTEGER,
                    inserted_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            # Indexes for faster analytical queries
            conn.execute('CREATE INDEX IF NOT EXISTS idx_store_time ON events (store_id, timestamp)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_store_visitor ON events (store_id, visitor_id)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_event_type ON events (event_type)')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS anomalies (
                    id TEXT PRIMARY KEY,
                    store_id TEXT,
                    anomaly_type TEXT,
                    severity TEXT,
                    detected_at DATETIME,
                    description TEXT,
                    suggested_action TEXT,
                    zone_id TEXT,
                    active BOOLEAN DEFAULT 1
                )
            ''')
            
    def insert_events(self, events: List[EventSchema]) -> int:
        """Insert batch of events. Ignores duplicates (idempotent)."""
        if not events:
            return 0
            
        inserted_count = 0
        with self._get_conn() as conn:
            cursor = conn.cursor()
            for event in events:
                try:
                    cursor.execute('''
                        INSERT INTO events (
                            event_id, store_id, camera_id, visitor_id, event_type, 
                            timestamp, zone_id, dwell_ms, is_staff, confidence, 
                            queue_depth, session_seq
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        event.event_id, event.store_id, event.camera_id, event.visitor_id,
                        event.event_type.value, event.timestamp.isoformat(), event.zone_id,
                        event.dwell_ms, event.is_staff, event.confidence,
                        event.metadata.queue_depth, event.metadata.session_seq
                    ))
                    inserted_count += cursor.rowcount
                except sqlite3.IntegrityError:
                    pass # Ignore duplicate event_id
            conn.commit()
        return inserted_count

    def get_last_event_time(self, store_id: Optional[str] = None) -> Optional[datetime]:
        """Get the timestamp of the most recently received event."""
        with self._get_conn() as conn:
            query = "SELECT MAX(timestamp) as last_time FROM events"
            params = []
            if store_id:
                query += " WHERE store_id = ?"
                params.append(store_id)
            row = conn.execute(query, params).fetchone()
            if row and row['last_time']:
                return datetime.fromisoformat(row['last_time'])
        return None

    def get_metrics(self, store_id: str) -> Dict[str, Any]:
        """Compute core metrics (excluding staff)."""
        with self._get_conn() as conn:
            # 1. Unique visitors today (assuming UTC for simplicity in this demo)
            # Better approximation: rolling 24h or current date string match
            unique_v = conn.execute('''
                SELECT COUNT(DISTINCT visitor_id) as count 
                FROM events 
                WHERE store_id = ? AND is_staff = 0 
                  AND date(timestamp) = date('now')
            ''', (store_id,)).fetchone()['count']
            
            # 2. Avg dwell
            avg_dwell = conn.execute('''
                SELECT AVG(dwell_ms) as avg_dwell 
                FROM events 
                WHERE store_id = ? AND is_staff = 0 
                  AND event_type IN ('ZONE_EXIT', 'BILLING_QUEUE_ABANDON')
                  AND date(timestamp) = date('now')
            ''', (store_id,)).fetchone()['avg_dwell']
            
            # 3. Queue Depth (Current/Latest)
            q_depth = conn.execute('''
                SELECT queue_depth 
                FROM events 
                WHERE store_id = ? AND event_type = 'BILLING_QUEUE_JOIN'
                ORDER BY timestamp DESC LIMIT 1
            ''', (store_id,)).fetchone()
            q_depth_val = q_depth['queue_depth'] if q_depth else 0
            
            # 4. Conversion & Abandonment
            joins = conn.execute('''
                SELECT COUNT(DISTINCT visitor_id) as c 
                FROM events 
                WHERE store_id = ? AND is_staff = 0 AND event_type = 'BILLING_QUEUE_JOIN'
                  AND date(timestamp) = date('now')
            ''', (store_id,)).fetchone()['c']
            
            abandons = conn.execute('''
                SELECT COUNT(DISTINCT visitor_id) as c 
                FROM events 
                WHERE store_id = ? AND is_staff = 0 AND event_type = 'BILLING_QUEUE_ABANDON'
                  AND date(timestamp) = date('now')
            ''', (store_id,)).fetchone()['c']
            
            # Converted = people who exited BILLING successfully
            purchases = conn.execute('''
                SELECT COUNT(DISTINCT visitor_id) as c 
                FROM events 
                WHERE store_id = ? AND is_staff = 0 AND event_type = 'ZONE_EXIT' AND zone_id = 'BILLING'
                  AND date(timestamp) = date('now')
            ''', (store_id,)).fetchone()['c']

            cr = (purchases / unique_v) if unique_v > 0 else 0.0
            abandon_rate = (abandons / joins) if joins > 0 else 0.0

            return {
                "unique_visitors_today": unique_v,
                "conversion_rate": cr,
                "avg_dwell_ms": avg_dwell or 0.0,
                "current_queue_depth": q_depth_val,
                "abandonment_rate": abandon_rate
            }

    def get_funnel(self, store_id: str) -> Dict[str, Any]:
        """Compute the conversion funnel for the store today."""
        with self._get_conn() as conn:
            entered = conn.execute('''
                SELECT COUNT(DISTINCT visitor_id) as c 
                FROM events 
                WHERE store_id = ? AND is_staff = 0 AND event_type = 'ENTRY'
                  AND date(timestamp) = date('now')
            ''', (store_id,)).fetchone()['c']
            
            browsed = conn.execute('''
                SELECT COUNT(DISTINCT visitor_id) as c 
                FROM events 
                WHERE store_id = ? AND is_staff = 0 AND event_type = 'ZONE_ENTER' AND zone_id != 'BILLING'
                  AND date(timestamp) = date('now')
            ''', (store_id,)).fetchone()['c']
            
            queued = conn.execute('''
                SELECT COUNT(DISTINCT visitor_id) as c 
                FROM events 
                WHERE store_id = ? AND is_staff = 0 AND event_type = 'BILLING_QUEUE_JOIN'
                  AND date(timestamp) = date('now')
            ''', (store_id,)).fetchone()['c']
            
            purchased = conn.execute('''
                SELECT COUNT(DISTINCT visitor_id) as c 
                FROM events 
                WHERE store_id = ? AND is_staff = 0 AND event_type = 'ZONE_EXIT' AND zone_id = 'BILLING'
                  AND date(timestamp) = date('now')
            ''', (store_id,)).fetchone()['c']

            steps = [
                {"step": "Entered", "count": entered},
                {"step": "Browsed", "count": browsed},
                {"step": "Queued", "count": queued},
                {"step": "Purchased", "count": purchased}
            ]
            
            # Calculate drop-off
            for i in range(1, len(steps)):
                prev = steps[i-1]["count"]
                curr = steps[i]["count"]
                steps[i]["drop_off_pct"] = ((prev - curr) / prev * 100) if prev > 0 else 0.0

            return {"store_id": store_id, "funnel": steps}

    def get_heatmap(self, store_id: str) -> Dict[str, Any]:
        """Compute normalized heatmap and dwell data."""
        with self._get_conn() as conn:
            # First find max visits to normalize 0-100
            zone_visits = conn.execute('''
                SELECT zone_id, COUNT(DISTINCT visitor_id) as visits 
                FROM events 
                WHERE store_id = ? AND is_staff = 0 AND event_type = 'ZONE_ENTER'
                GROUP BY zone_id
            ''', (store_id,)).fetchall()
            
            zone_dwells = conn.execute('''
                SELECT zone_id, AVG(dwell_ms) as avg_dwell 
                FROM events 
                WHERE store_id = ? AND is_staff = 0 AND event_type IN ('ZONE_EXIT', 'BILLING_QUEUE_ABANDON')
                GROUP BY zone_id
            ''', (store_id,)).fetchall()
            
            total_sessions = conn.execute('''
                SELECT COUNT(DISTINCT visitor_id) as c 
                FROM events 
                WHERE store_id = ? AND is_staff = 0 
            ''', (store_id,)).fetchone()['c']

            dwell_map = {row['zone_id']: row['avg_dwell'] for row in zone_dwells}
            
            max_visits = max([r['visits'] for r in zone_visits]) if zone_visits else 1
            
            zones = []
            for row in zone_visits:
                z = row['zone_id']
                if not z: continue
                zones.append({
                    "zone_id": z,
                    "visit_frequency": (row['visits'] / max_visits) * 100.0,
                    "avg_dwell_ms": dwell_map.get(z, 0.0)
                })

            return {
                "store_id": store_id,
                "data_confidence": "HIGH" if total_sessions >= 20 else "LOW",
                "total_sessions": total_sessions,
                "zones": zones
            }

    # Anomaly tracking helpers
    def insert_anomaly(self, anomaly: Any) -> None:
        with self._get_conn() as conn:
            conn.execute('''
                INSERT OR IGNORE INTO anomalies (
                    id, store_id, anomaly_type, severity, detected_at, 
                    description, suggested_action, zone_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                anomaly.id, anomaly.store_id, anomaly.anomaly_type.value, anomaly.severity.value,
                anomaly.detected_at.isoformat(), anomaly.description, anomaly.suggested_action,
                anomaly.zone_id
            ))
            conn.commit()

    def get_active_anomalies(self, store_id: str) -> List[Dict]:
        with self._get_conn() as conn:
            rows = conn.execute('''
                SELECT * FROM anomalies 
                WHERE store_id = ? AND active = 1
                ORDER BY detected_at DESC
            ''', (store_id,)).fetchall()
            return [dict(row) for row in rows]
