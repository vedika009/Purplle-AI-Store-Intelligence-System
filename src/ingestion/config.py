from pydantic import BaseModel, Field
from typing import List, Tuple

class CameraConfig(BaseModel):
    camera_id: str
    source: str
    target_fps: int = Field(default=3, ge=1, le=30)
    enabled: bool = True

class IngestionConfig(BaseModel):
    output_dir: str = "./data/processed_frames"
    target_resolution: Tuple[int, int] = (640, 640)

class AppConfig(BaseModel):
    store_id: str
    ingestion: IngestionConfig = Field(default_factory=IngestionConfig)
    cameras: List[CameraConfig]

    @classmethod
    def load_from_yaml(cls, yaml_path: str) -> "AppConfig":
        import yaml
        with open(yaml_path, "r") as f:
            data = yaml.safe_load(f)
        return cls(**data)
