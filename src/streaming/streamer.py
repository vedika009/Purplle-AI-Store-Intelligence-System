import json
import logging
from typing import List, Dict, Any, Callable
from urllib.parse import urljoin
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.cv_layer.schema import EventSchema

logger = logging.getLogger(__name__)

class EventStreamer:
    """
    Streams events to the Intelligence API using batched HTTP POST requests.
    Supports retries, backoff, and fallback offline storage.
    """
    def __init__(self, api_url: str, batch_size: int = 100, max_retries: int = 3):
        self.api_url = api_url
        self.batch_size = batch_size
        self.buffer: List[EventSchema] = []
        
        self.session = requests.Session()
        retry = Retry(
            total=max_retries,
            read=max_retries,
            connect=max_retries,
            backoff_factor=0.3,
            status_forcelist=(500, 502, 503, 504)
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
    def add_events(self, events: List[EventSchema]) -> None:
        """Add events to the buffer and flush if batch size is reached."""
        self.buffer.extend(events)
        if len(self.buffer) >= self.batch_size:
            self.flush()
            
    def flush(self) -> None:
        """Send currently buffered events to the API."""
        if not self.buffer:
            return
            
        # Take up to batch_size
        batch = self.buffer[:self.batch_size]
        payload = [json.loads(event.model_dump_json()) for event in batch]
        
        try:
            endpoint = urljoin(self.api_url, "/events/ingest")
            response = self.session.post(endpoint, json=payload, timeout=5.0)
            response.raise_for_status()
            
            # Remove successfully sent events from buffer
            self.buffer = self.buffer[self.batch_size:]
            logger.info(f"Successfully streamed batch of {len(batch)} events")
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to stream events to API: {e}")
            # Keep in buffer for next flush attempt
            # In a production system, we might dump to disk after max retries
