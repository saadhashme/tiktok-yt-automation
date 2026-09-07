import os
import yaml
from typing import Dict, List, Any, Optional

class Config:
    def __init__(self, config_path: str = "channels.yaml"):
        self.config_path = config_path
        self.channels: List[Dict[str, Any]] = []
        self.load_config()

    def load_config(self):
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Configuration file {self.config_path} not found.")
        with open(self.config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            self.channels = data.get("channels", [])

    def get_channel(self, channel_id: str) -> Optional[Dict[str, Any]]:
        for ch in self.channels:
            if ch.get("id") == channel_id:
                return ch
        return None

    def get_all_channels(self) -> List[Dict[str, Any]]:
        return self.channels
