import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional
import supervision as sv

from src.cv_layer.schema import EventSchema, EventType, EventMetadata
from src.cv_layer.tracker import ReIDManager
from src.cv_layer.zone_mapper import ZoneManager
from src.streaming.pos_correlator import POSCorrelator

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
        self.last_dwell_emit_time: Optional[datetime] = None

class EventExtractor:
    def __init__(self, store_id: str, camera_id: str, reid_manager: ReIDManager, zone_manager: ZoneManager, pos_correlator: Optional[POSCorrelator] = None):
        self.store_id = store_id
        self.camera_id = camera_id
        self.reid_manager = reid_manager
        self.zone_manager = zone_manager
        self.pos_correlator = pos_correlator
        self.visitor_states: Dict[str, VisitorState] = {}
        
        # Calculate the boundary of defined layout zones to auto-scale raw detection coordinates
        self.max_x = 400.0
        self.max_y = 400.0
        zones = getattr(self.zone_manager, "zones", None)
        if isinstance(zones, dict) and zones:
            all_x = []
            all_y = []
            for poly in zones.values():
                bounds = poly.bounds  # (minx, miny, maxx, maxy)
                all_x.append(bounds[2])
                all_y.append(bounds[3])
            if all_x:
                self.max_x = max(all_x)
            if all_y:
                self.max_y = max(all_y)
        
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

    def process_detections(self, detections: sv.Detections, frame_timestamp: datetime, frame_size: Optional[tuple] = None) -> List[EventSchema]:
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
            
            # Auto-scale coordinates if frame_size is specified
            if frame_size:
                width, height = frame_size
                x_center = (x_center / width) * self.max_x
                y_bottom = (y_bottom / height) * self.max_y
            
            visitor_id = self.reid_manager.get_visitor_id(track_id)
            if visitor_id not in self.visitor_states:
                self.visitor_states[visitor_id] = VisitorState(visitor_id, track_id)
            
            state = self.visitor_states[visitor_id]
            state.last_seen_time = frame_timestamp
            
            zone_id = self.zone_manager.get_zone(x_center, y_bottom)
            
            # Auto-mark staff if seen in STAFF_ONLY zone
            if zone_id == "STAFF_ONLY" or (zone_id and "staff" in zone_id.lower()):
                self.reid_manager.mark_staff(track_id)
            
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

            # Handle ZONE transitions and ZONE_DWELL
            if zone_id != state.current_zone:
                # Exit previous zone
                if state.current_zone is not None:
                    dwell = int((frame_timestamp - state.zone_entry_time).total_seconds() * 1000)
                    
                    if state.current_zone == "BILLING":
                        abandoned = True
                        if self.pos_correlator and self.pos_correlator.check_correlation(self.store_id, frame_timestamp):
                            abandoned = False
                            
                        if abandoned:
                            emitted_events.append(self._create_event(EventType.BILLING_QUEUE_ABANDON, visitor_id, frame_timestamp, confidence, state.current_zone, dwell))
                        else:
                            emitted_events.append(self._create_event(EventType.ZONE_EXIT, visitor_id, frame_timestamp, confidence, state.current_zone, dwell))
                    else:
                        emitted_events.append(self._create_event(EventType.ZONE_EXIT, visitor_id, frame_timestamp, confidence, state.current_zone, dwell))
                
                # Enter new zone
                state.current_zone = zone_id
                state.zone_entry_time = frame_timestamp
                state.last_dwell_emit_time = frame_timestamp
                
                if zone_id is not None:
                    if zone_id == "BILLING":
                        emitted_events.append(self._create_event(EventType.BILLING_QUEUE_JOIN, visitor_id, frame_timestamp, confidence, zone_id, queue_depth=current_queue_depth))
                    else:
                        emitted_events.append(self._create_event(EventType.ZONE_ENTER, visitor_id, frame_timestamp, confidence, zone_id))
            else:
                # Continuing in the same zone
                if zone_id is not None:
                    if state.last_dwell_emit_time is None:
                        state.last_dwell_emit_time = state.zone_entry_time
                    dwell_since_last_emit = (frame_timestamp - state.last_dwell_emit_time).total_seconds()
                    if dwell_since_last_emit >= 30.0:
                        total_dwell = int((frame_timestamp - state.zone_entry_time).total_seconds() * 1000)
                        emitted_events.append(self._create_event(
                            EventType.ZONE_DWELL,
                            visitor_id,
                            frame_timestamp,
                            confidence,
                            zone_id,
                            dwell_ms=total_dwell
                        ))
                        state.last_dwell_emit_time = frame_timestamp

        # Handle EXIT logic (if not seen for exit_timeout, consider exited)
        from datetime import timedelta
        exit_timeout = timedelta(seconds=10)
        
        for visitor_id, state in list(self.visitor_states.items()):
            if state.has_entered and not state.has_exited:
                if frame_timestamp - state.last_seen_time > exit_timeout:
                    # 1. Close current zone dwell
                    if state.current_zone is not None:
                        dwell = int((state.last_seen_time - state.zone_entry_time).total_seconds() * 1000)
                        
                        if state.current_zone == "BILLING":
                            abandoned = True
                            if self.pos_correlator and self.pos_correlator.check_correlation(self.store_id, state.last_seen_time):
                                abandoned = False
                                
                            if abandoned:
                                emitted_events.append(self._create_event(EventType.BILLING_QUEUE_ABANDON, visitor_id, state.last_seen_time, 0.8, state.current_zone, dwell))
                            else:
                                emitted_events.append(self._create_event(EventType.ZONE_EXIT, visitor_id, state.last_seen_time, 0.8, state.current_zone, dwell))
                        else:
                            emitted_events.append(self._create_event(EventType.ZONE_EXIT, visitor_id, state.last_seen_time, 0.8, state.current_zone, dwell))
                        
                        state.current_zone = None
                        
                    # 2. Emit EXIT event
                    emitted_events.append(self._create_event(
                        EventType.EXIT, 
                        visitor_id, 
                        state.last_seen_time, 
                        confidence=0.8
                    ))
                    state.has_exited = True
                    state.has_entered = False
        
        return emitted_events
