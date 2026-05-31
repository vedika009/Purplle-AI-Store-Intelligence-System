from enum import Enum
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field

class AnomalyType(str, Enum):
    QUEUE_SPIKE = "QUEUE_SPIKE"
    CONVERSION_DROP = "CONVERSION_DROP"
    DEAD_ZONE = "DEAD_ZONE"

class Severity(str, Enum):
    INFO = "INFO"
    WARN = "WARN"
    CRITICAL = "CRITICAL"

class Anomaly(BaseModel):
    id: str = Field(..., description="Unique anomaly ID")
    store_id: str = Field(..., description="Store where anomaly occurred")
    anomaly_type: AnomalyType
    severity: Severity
    detected_at: datetime
    description: str
    suggested_action: str
    zone_id: Optional[str] = Field(None, description="Affected zone, if applicable")
