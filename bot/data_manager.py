import json
import os
from typing import Any

class DataManager:
    @staticmethod
    def load_json(file_path: str) -> Any:
        if not os.path.exists(file_path):
            return None
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def save_json(file_path: str, data: Any) -> None:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    @staticmethod
    def load_or_create(file_path: str, default: Any) -> Any:
        data = DataManager.load_json(file_path)
        if data is None:
            DataManager.save_json(file_path, default)
            return default
        return data
