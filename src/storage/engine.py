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
                try:
                    return datetime.fromisoformat(row['last_time'])
                except ValueError:
                    # Strip offset if exists or fallback
                    return datetime.fromisoformat(row['last_time'].replace('Z', '+00:00'))
        return None

    def _get_latest_event_date(self, conn, store_id: str) -> str:
        """Returns the date of the latest event in the store, formatted as YYYY-MM-DD. Defaults to today's date."""
        row = conn.execute(
            "SELECT date(MAX(timestamp)) as latest_date FROM events WHERE store_id = ?", 
            (store_id,)
        ).fetchone()
        if row and row['latest_date']:
            return row['latest_date']
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def get_known_zones(self, store_id: str) -> List[str]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT zone_id FROM events WHERE store_id = ? AND zone_id IS NOT NULL",
                (store_id,)
            ).fetchall()
            return [row['zone_id'] for row in rows]
            
    def get_historical_average_cr(self, store_id: str, current_time: datetime) -> float:
        """Computes the overall conversion rate in the 7 days prior to current_time."""
        from datetime import timedelta
        with self._get_conn() as conn:
            end_date = (current_time - timedelta(days=1)).strftime("%Y-%m-%d")
            start_date = (current_time - timedelta(days=7)).strftime("%Y-%m-%d")
            
            unique_v = conn.execute('''
                SELECT COUNT(DISTINCT visitor_id) as count 
                FROM events 
                WHERE store_id = ? AND is_staff = 0 
                  AND date(timestamp) BETWEEN ? AND ?
            ''', (store_id, start_date, end_date)).fetchone()['count']
            
            if not unique_v or unique_v == 0:
                return 0.0
                
            purchases = conn.execute('''
                SELECT COUNT(DISTINCT visitor_id) as c 
                FROM events 
                WHERE store_id = ? AND is_staff = 0 AND event_type = 'ZONE_EXIT' AND zone_id = 'BILLING'
                  AND date(timestamp) BETWEEN ? AND ?
            ''', (store_id, start_date, end_date)).fetchone()['c']
            
            return (purchases / unique_v) if unique_v > 0 else 0.0

    def resolve_dead_zones(self, store_id: str, resolved_zones: List[str]) -> None:
        if not resolved_zones:
            return
        with self._get_conn() as conn:
            placeholders = ",".join("?" for _ in resolved_zones)
            conn.execute(f'''
                UPDATE anomalies 
                SET active = 0 
                WHERE store_id = ? AND anomaly_type = 'DEAD_ZONE' AND active = 1 AND zone_id IN ({placeholders})
            ''', [store_id] + resolved_zones)
            conn.commit()
            
    def resolve_conversion_drop(self, store_id: str) -> None:
        with self._get_conn() as conn:
            conn.execute('''
                UPDATE anomalies 
                SET active = 0 
                WHERE store_id = ? AND anomaly_type = 'CONVERSION_DROP' AND active = 1
            ''', (store_id,))
            conn.commit()

    def get_metrics(self, store_id: str) -> Dict[str, Any]:
        """Compute core metrics (excluding staff)."""
        with self._get_conn() as conn:
            latest_date = self._get_latest_event_date(conn, store_id)

            # 1. Unique visitors today (using latest event date)
            unique_v = conn.execute('''
                SELECT COUNT(DISTINCT visitor_id) as count 
                FROM events 
                WHERE store_id = ? AND is_staff = 0 
                  AND date(timestamp) = ?
            ''', (store_id, latest_date)).fetchone()['count']
            
            # 2. Avg dwell
            avg_dwell = conn.execute('''
                SELECT AVG(dwell_ms) as avg_dwell 
                FROM events 
                WHERE store_id = ? AND is_staff = 0 
                  AND event_type IN ('ZONE_EXIT', 'BILLING_QUEUE_ABANDON')
                  AND date(timestamp) = ?
            ''', (store_id, latest_date)).fetchone()['avg_dwell']

            # Avg dwell per zone
            dwell_per_zone_rows = conn.execute('''
                SELECT zone_id, AVG(dwell_ms) as avg_dwell 
                FROM events 
                WHERE store_id = ? AND is_staff = 0 AND zone_id IS NOT NULL
                  AND event_type IN ('ZONE_EXIT', 'BILLING_QUEUE_ABANDON')
                  AND date(timestamp) = ?
                GROUP BY zone_id
            ''', (store_id, latest_date)).fetchall()
            avg_dwell_per_zone = {row['zone_id']: row['avg_dwell'] for row in dwell_per_zone_rows}
            
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
                  AND date(timestamp) = ?
            ''', (store_id, latest_date)).fetchone()['c']
            
            abandons = conn.execute('''
                SELECT COUNT(DISTINCT visitor_id) as c 
                FROM events 
                WHERE store_id = ? AND is_staff = 0 AND event_type = 'BILLING_QUEUE_ABANDON'
                  AND date(timestamp) = ?
            ''', (store_id, latest_date)).fetchone()['c']
            
            # Converted = people who exited BILLING successfully
            purchases = conn.execute('''
                SELECT COUNT(DISTINCT visitor_id) as c 
                FROM events 
                WHERE store_id = ? AND is_staff = 0 AND event_type = 'ZONE_EXIT' AND zone_id = 'BILLING'
                  AND date(timestamp) = ?
            ''', (store_id, latest_date)).fetchone()['c']

            cr = (purchases / unique_v) if unique_v > 0 else 0.0
            abandon_rate = (abandons / joins) if joins > 0 else 0.0

            return {
                "unique_visitors_today": unique_v,
                "conversion_rate": cr,
                "avg_dwell_ms": avg_dwell or 0.0,
                "avg_dwell_per_zone": avg_dwell_per_zone,
                "current_queue_depth": q_depth_val,
                "abandonment_rate": abandon_rate
            }

    def get_funnel(self, store_id: str) -> Dict[str, Any]:
        """Compute the conversion funnel for the store today."""
        with self._get_conn() as conn:
            latest_date = self._get_latest_event_date(conn, store_id)

            entered = conn.execute('''
                SELECT COUNT(DISTINCT visitor_id) as c 
                FROM events 
                WHERE store_id = ? AND is_staff = 0 AND event_type IN ('ENTRY', 'REENTRY')
                  AND date(timestamp) = ?
            ''', (store_id, latest_date)).fetchone()['c']
            
            browsed = conn.execute('''
                SELECT COUNT(DISTINCT visitor_id) as c 
                FROM events 
                WHERE store_id = ? AND is_staff = 0 AND event_type = 'ZONE_ENTER' AND zone_id != 'BILLING'
                  AND date(timestamp) = ?
            ''', (store_id, latest_date)).fetchone()['c']
            
            queued = conn.execute('''
                SELECT COUNT(DISTINCT visitor_id) as c 
                FROM events 
                WHERE store_id = ? AND is_staff = 0 AND event_type = 'BILLING_QUEUE_JOIN'
                  AND date(timestamp) = ?
            ''', (store_id, latest_date)).fetchone()['c']
            
            purchased = conn.execute('''
                SELECT COUNT(DISTINCT visitor_id) as c 
                FROM events 
                WHERE store_id = ? AND is_staff = 0 AND event_type = 'ZONE_EXIT' AND zone_id = 'BILLING'
                  AND date(timestamp) = ?
            ''', (store_id, latest_date)).fetchone()['c']

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
            latest_date = self._get_latest_event_date(conn, store_id)

            # First find max visits to normalize 0-100
            zone_visits = conn.execute('''
                SELECT zone_id, COUNT(DISTINCT visitor_id) as visits 
                FROM events 
                WHERE store_id = ? AND is_staff = 0 AND event_type = 'ZONE_ENTER'
                  AND date(timestamp) = ?
                GROUP BY zone_id
            ''', (store_id, latest_date)).fetchall()
            
            zone_dwells = conn.execute('''
                SELECT zone_id, AVG(dwell_ms) as avg_dwell 
                FROM events 
                WHERE store_id = ? AND is_staff = 0 AND event_type IN ('ZONE_EXIT', 'BILLING_QUEUE_ABANDON')
                  AND date(timestamp) = ?
                GROUP BY zone_id
            ''', (store_id, latest_date)).fetchall()
            
            total_sessions = conn.execute('''
                SELECT COUNT(DISTINCT visitor_id) as c 
                FROM events 
                WHERE store_id = ? AND is_staff = 0 
                  AND date(timestamp) = ?
            ''', (store_id, latest_date)).fetchone()['c']

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
            # Check if there's already an active anomaly of the same type (and zone)
            query = "SELECT id FROM anomalies WHERE store_id = ? AND anomaly_type = ? AND active = 1"
            params = [anomaly.store_id, anomaly.anomaly_type.value]
            if anomaly.zone_id:
                query += " AND zone_id = ?"
                params.append(anomaly.zone_id)
            else:
                query += " AND zone_id IS NULL"
            
            exists = conn.execute(query, params).fetchone()
            if exists:
                return # Don't insert duplicate active anomaly

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

    def get_last_event_time_per_store(self) -> Dict[str, datetime]:
        with self._get_conn() as conn:
            rows = conn.execute('''
                SELECT store_id, MAX(timestamp) as last_time 
                FROM events 
                GROUP BY store_id
            ''').fetchall()
            res = {}
            for row in rows:
                if row['last_time']:
                    try:
                        res[row['store_id']] = datetime.fromisoformat(row['last_time'])
                    except ValueError:
                        res[row['store_id']] = datetime.fromisoformat(row['last_time'].replace('Z', '+00:00'))
            return res
