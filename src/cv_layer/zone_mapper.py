import json
from typing import Dict, Any, List
from shapely.geometry import Point, Polygon

class ZoneManager:
    def __init__(self, layout_path: str, camera_id: str):
        """
        Loads the store layout and parses zones for the specific camera view.
        """
        self.camera_id = camera_id
        self.zones: Dict[str, Polygon] = {}
        self._load_layout(layout_path)

    def _load_layout(self, layout_path: str):
        # We simulate loading layout json for the specific camera
        # Expected structure: 
        # {"CAM_ENTRY_01": {"ENTRY_DOOR": [[x,y], [x,y], ...], "SKINCARE": [...]}}
        try:
            with open(layout_path, 'r') as f:
                layout = json.load(f)
                
            if self.camera_id in layout:
                for zone_id, points in layout[self.camera_id].items():
                    self.zones[zone_id] = Polygon(points)
        except FileNotFoundError:
            # Handle graceful degradation if no layout config exists yet
            pass

    def get_zone(self, x: float, y: float) -> str | None:
        """
        Returns the zone_id a given point (bottom center of bounding box) is in.
        Returns None if not in any defined zone.
        """
        point = Point(x, y)
        for zone_id, poly in self.zones.items():
            if poly.intersects(point):
                return zone_id
        return None
