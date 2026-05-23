import json
import os
from datetime import datetime, timezone

class ValidationStore:
    def __init__(self, db_path: str = None):
        if db_path is None:
            # Default to a local directory or inside the app context
            db_path = os.path.join(os.getcwd(), ".py2rust", "validations.jsonl")
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    def save_validation(self, record: dict):
        record_with_time = {
            "timestamp": record.get("timestamp", datetime.now(timezone.utc).isoformat()),
            "symbol_name": record.get("symbol_name"),
            "python_source": record.get("python_source"),
            "generated_rust": record.get("generated_rust"),
            "verdict": record.get("verdict"),
            "confidence": record.get("confidence", 0.0),
            "reasoning": record.get("reasoning", "")
        }
        
        with open(self.db_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record_with_time) + "\n")

    def get_validations(self) -> list[dict]:
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
