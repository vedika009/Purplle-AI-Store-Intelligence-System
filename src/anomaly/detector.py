import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from src.cv_layer.schema import EventSchema, EventType
from .schema import Anomaly, AnomalyType, Severity

class AnomalyDetector:
    def __init__(self, queue_threshold: int = 10, dead_zone_minutes: int = 30):
        self.queue_threshold = queue_threshold
        self.dead_zone_minutes = dead_zone_minutes
        
        # State tracking
        self.zone_last_seen: Dict[str, Dict[str, datetime]] = {} # store_id -> zone_id -> timestamp
        self.store_queue_depth: Dict[str, int] = {}
        
    def process_event(self, event: EventSchema) -> Optional[Anomaly]:
        """Process a single event and return an anomaly if one is immediately detected."""
        if event.store_id not in self.zone_last_seen:
            self.zone_last_seen[event.store_id] = {}
            
        # Update zone last seen
        if event.zone_id:
            self.zone_last_seen[event.store_id][event.zone_id] = event.timestamp
            
        # Check for Queue Spike (instantaneous based on event metadata)
        if event.event_type == EventType.BILLING_QUEUE_JOIN:
            depth = event.metadata.queue_depth or 0
            self.store_queue_depth[event.store_id] = depth
            
            if depth > self.queue_threshold:
                return Anomaly(
                    id=str(uuid.uuid4()),
                    store_id=event.store_id,
                    anomaly_type=AnomalyType.QUEUE_SPIKE,
                    severity=Severity.CRITICAL if depth > self.queue_threshold + 5 else Severity.WARN,
                    detected_at=event.timestamp,
                    description=f"Queue depth is {depth}, exceeding threshold of {self.queue_threshold}",
                    suggested_action="Open an additional checkout counter immediately.",
                    zone_id=event.zone_id
                )
        elif event.event_type == EventType.BILLING_QUEUE_ABANDON or event.event_type == EventType.ZONE_EXIT:
            if event.zone_id == "BILLING" and event.store_id in self.store_queue_depth:
                self.store_queue_depth[event.store_id] = max(0, self.store_queue_depth[event.store_id] - 1)
                
        return None

    def check_dead_zones(self, store_id: str, current_time: datetime, known_zones: List[str]) -> List[Anomaly]:
        """Periodically check for zones that haven't seen activity."""
        anomalies = []
        if store_id not in self.zone_last_seen:
            self.zone_last_seen[store_id] = {}
            
        store_zones = self.zone_last_seen[store_id]
        
        for zone in known_zones:
            last_seen = store_zones.get(zone)
            if not last_seen:
                continue # Haven't ever seen anyone, can't reliably call it dead yet without baseline
                
            idle_time = (current_time - last_seen).total_seconds() / 60.0
            
            if idle_time > self.dead_zone_minutes:
                anomalies.append(Anomaly(
                    id=str(uuid.uuid4()),
                    store_id=store_id,
                    anomaly_type=AnomalyType.DEAD_ZONE,
                    severity=Severity.INFO if idle_time < 60 else Severity.WARN,
                    detected_at=current_time,
                    description=f"Zone '{zone}' has had no visitors for {int(idle_time)} minutes.",
                    suggested_action=f"Check if {zone} displays need restocking or store layout requires adjustment.",
                    zone_id=zone
                ))
                
        return anomalies
        
    def check_conversion_drop(self, store_id: str, current_time: datetime, current_cr: float, avg_7d_cr: float) -> Optional[Anomaly]:
        """Check if current conversion rate has dropped significantly vs 7-day average."""
        # e.g., if CR is >20% lower than average
        if avg_7d_cr == 0:
            return None
            
        drop_percentage = ((avg_7d_cr - current_cr) / avg_7d_cr) * 100
        
        if drop_percentage > 20.0:
            return Anomaly(
                id=str(uuid.uuid4()),
                store_id=store_id,
                anomaly_type=AnomalyType.CONVERSION_DROP,
                severity=Severity.CRITICAL if drop_percentage > 40 else Severity.WARN,
                detected_at=current_time,
                description=f"Conversion rate dropped by {drop_percentage:.1f}% compared to 7-day average.",
                suggested_action="Investigate POS system uptime, staff availability, or immediate queue bottlenecks."
            )
        return None
