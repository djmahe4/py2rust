import json
import os
from datetime import datetime, timezone

class PatternStore:
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = os.path.join(os.getcwd(), ".py2rust", "patterns.jsonl")
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    def save_pattern(self, pattern: dict):
        record = {
            "timestamp": pattern.get("timestamp", datetime.now(timezone.utc).isoformat()),
            "pattern_id": pattern.get("pattern_id"),
            "trigger_pattern": pattern.get("trigger_pattern"),
            "target_rust": pattern.get("target_rust"),
            "replacement_rust": pattern.get("replacement_rust"),
            "evidence_count": pattern.get("evidence_count", 1),
            "confidence": pattern.get("confidence", 0.0)
        }
        with open(self.db_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def get_patterns(self) -> list[dict]:
        if not os.path.exists(self.db_path):
            return []
            
        records = []
        with open(self.db_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except Exception:
                        pass
        return records
