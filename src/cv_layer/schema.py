from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field

class EventType(str, Enum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"
    ZONE_ENTER = "ZONE_ENTER"
    ZONE_EXIT = "ZONE_EXIT"
    ZONE_DWELL = "ZONE_DWELL"
    BILLING_QUEUE_JOIN = "BILLING_QUEUE_JOIN"
    BILLING_QUEUE_ABANDON = "BILLING_QUEUE_ABANDON"
    REENTRY = "REENTRY"

class EventMetadata(BaseModel):
    queue_depth: Optional[int] = Field(None, description="Populated for BILLING_QUEUE_JOIN")
    sku_zone: Optional[str] = Field(None, description="Zone label from store_layout.json")
    session_seq: int = Field(..., description="Ordinal position of this event in visitor session")

class EventSchema(BaseModel):
    event_id: str = Field(..., description="Globally unique UUID v4")
    store_id: str = Field(..., description="From store_layout.json")
    camera_id: str = Field(..., description="Which camera produced this event")
    visitor_id: str = Field(..., description="Re-ID token, unique per visit session")
    event_type: EventType = Field(..., description="Specific behavioural event")
    timestamp: datetime = Field(..., description="ISO-8601 UTC timestamp")
    zone_id: Optional[str] = Field(None, description="Null for ENTRY/EXIT events")
    dwell_ms: int = Field(0, description="Duration in ms; 0 for instantaneous events")
    is_staff: bool = Field(False, description="True if classified as staff")
    confidence: float = Field(..., description="Detection confidence, 0.0 to 1.0")
    metadata: EventMetadata
