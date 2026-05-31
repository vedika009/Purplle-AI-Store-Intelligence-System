import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional
import supervision as sv

from src.cv_layer.schema import EventSchema, EventType, EventMetadata
from src.cv_layer.tracker import ReIDManager
from src.cv_layer.zone_mapper import ZoneManager

class VisitorState:
    def __init__(self, visitor_id: str, track_id: int):
        self.visitor_id = visitor_id
        self.track_id = track_id
        self.current_zone: Optional[str] = None
        self.zone_entry_time: Optional[datetime] = None
        self.has_entered: bool = False
        self.has_exited: bool = False
        self.session_seq: int = 1
        self.last_seen_time: Optional[datetime] = None

class EventExtractor:
    def __init__(self, store_id: str, camera_id: str, reid_manager: ReIDManager, zone_manager: ZoneManager):
        self.store_id = store_id
        self.camera_id = camera_id
        self.reid_manager = reid_manager
        self.zone_manager = zone_manager
        self.visitor_states: Dict[str, VisitorState] = {}
        
    def _create_event(self, event_type: EventType, visitor_id: str, timestamp: datetime, 
                      confidence: float, zone_id: Optional[str] = None, 
                      dwell_ms: int = 0, queue_depth: Optional[int] = None) -> EventSchema:
        state = self.visitor_states[visitor_id]
        
        event = EventSchema(
            event_id=str(uuid.uuid4()),
            store_id=self.store_id,
            camera_id=self.camera_id,
            visitor_id=visitor_id,
            event_type=event_type,
            timestamp=timestamp,
            zone_id=zone_id,
            dwell_ms=dwell_ms,
            is_staff=self.reid_manager.is_staff(state.track_id),
            confidence=confidence,
            metadata=EventMetadata(
                queue_depth=queue_depth,
                sku_zone=zone_id,
                session_seq=state.session_seq
            )
        )
        state.session_seq += 1
        return event

    def process_detections(self, detections: sv.Detections, frame_timestamp: datetime) -> List[EventSchema]:
        """
        Takes tracking output for a single frame and generates behavioural events.
        """
        emitted_events = []
        
        # Calculate current queue depth (number of people in 'BILLING' zone)
        current_queue_depth = 0
        
        for i in range(len(detections)):
            # ByteTrack/sv returns (x1, y1, x2, y2)
            xyxy = detections.xyxy[i]
            track_id = detections.tracker_id[i] if detections.tracker_id is not None else None
            confidence = float(detections.confidence[i])
            
            if track_id is None:
                continue
                
            # Get bottom center of bbox for zone placement
            x_center = (xyxy[0] + xyxy[2]) / 2.0
            y_bottom = xyxy[3]
            
            visitor_id = self.reid_manager.get_visitor_id(track_id)
            if visitor_id not in self.visitor_states:
                self.visitor_states[visitor_id] = VisitorState(visitor_id, track_id)
            
            state = self.visitor_states[visitor_id]
            state.last_seen_time = frame_timestamp
            
            zone_id = self.zone_manager.get_zone(x_center, y_bottom)
            
            if zone_id == "BILLING":
                current_queue_depth += 1

            # Handle ENTRY logic
            if not state.has_entered:
                # If they were seen before and exited, it's a REENTRY
                if state.has_exited:
                    emitted_events.append(self._create_event(EventType.REENTRY, visitor_id, frame_timestamp, confidence))
                    state.has_exited = False
                else:
                    emitted_events.append(self._create_event(EventType.ENTRY, visitor_id, frame_timestamp, confidence))
                state.has_entered = True

            # Handle ZONE transitions
            if zone_id != state.current_zone:
                # Exit previous zone
                if state.current_zone is not None:
                    dwell = int((frame_timestamp - state.zone_entry_time).total_seconds() * 1000)
                    
                    if state.current_zone == "BILLING":
                        # Simplistic abandon logic: left billing before POS correlation (handled downstream)
                        emitted_events.append(self._create_event(EventType.BILLING_QUEUE_ABANDON, visitor_id, frame_timestamp, confidence, state.current_zone, dwell))
                    else:
                        emitted_events.append(self._create_event(EventType.ZONE_EXIT, visitor_id, frame_timestamp, confidence, state.current_zone, dwell))
                
                # Enter new zone
                state.current_zone = zone_id
                state.zone_entry_time = frame_timestamp
                
                if zone_id is not None:
                    if zone_id == "BILLING":
                        emitted_events.append(self._create_event(EventType.BILLING_QUEUE_JOIN, visitor_id, frame_timestamp, confidence, zone_id, queue_depth=current_queue_depth))
                    else:
                        emitted_events.append(self._create_event(EventType.ZONE_ENTER, visitor_id, frame_timestamp, confidence, zone_id))

        # Handle EXIT logic (simplified: if not seen for X seconds, consider exited)
        # In a real implementation, you'd check bounds crossing.
        
        return emitted_events
