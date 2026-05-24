import sqlite3
import os
import hashlib
from datetime import datetime, timezone
from typing import Optional


class ValidationStore:
    def __init__(self, db_path: str = None):
        if db_path is None:
            # Default to validations.db
            db_path = os.path.join(os.getcwd(), ".py2rust", "validations.db")
        elif db_path.endswith(".jsonl"):
            # Migrate db_path from validations.jsonl to validations.db
            db_path = db_path.replace(".jsonl", ".db")
            
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS validation_cache (
                    id TEXT PRIMARY KEY,
                    symbol_name TEXT NOT NULL,
                    python_hash TEXT NOT NULL,
                    rust_hash TEXT NOT NULL,
                    compiler_hash TEXT NOT NULL,
                    verdict TEXT NOT NULL CHECK(verdict IN ('PASS', 'FAIL')),
                    confidence REAL DEFAULT 0.0,
                    reasoning TEXT,
                    suggested_fix TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    python_source TEXT,
                    generated_rust TEXT,
                    is_hitl INTEGER DEFAULT 0
                );
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_hashes 
                ON validation_cache (python_hash, rust_hash, compiler_hash);
            """)

    def save_validation(self, record: dict):
        py_src = record.get("python_source") or record.get("python_code") or ""
        rust_src = record.get("generated_rust") or record.get("rust_code") or ""
        symbol = record.get("symbol_name") or "unknown"
        verdict = record.get("verdict", "FAIL")
        confidence = record.get("confidence", 0.0)
        reasoning = record.get("reasoning", "")
        suggested_fix = record.get("suggested_fix", "")
        is_hitl = record.get("is_hitl", 0)
        
        py_hash = hashlib.sha256(py_src.encode("utf-8")).hexdigest()
        rust_hash = hashlib.sha256(rust_src.encode("utf-8")).hexdigest()
        comp_hash = hashlib.sha256(record.get("compiler_hash", "default").encode("utf-8")).hexdigest()
        comp_id = hashlib.sha256((py_hash + rust_hash + comp_hash).encode("utf-8")).hexdigest()
        
        ts = record.get("timestamp", datetime.now(timezone.utc).isoformat())
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO validation_cache 
                (id, symbol_name, python_hash, rust_hash, compiler_hash, verdict, confidence, reasoning, suggested_fix, timestamp, python_source, generated_rust, is_hitl)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (comp_id, symbol, py_hash, rust_hash, comp_hash, verdict, confidence, reasoning, suggested_fix, ts, py_src, rust_src, is_hitl))

    def get_cached_validation(self, python_source: str, generated_rust: str, compiler_config_str: str = "default") -> Optional[dict]:
        py_hash = hashlib.sha256(python_source.encode("utf-8")).hexdigest()
        rust_hash = hashlib.sha256(generated_rust.encode("utf-8")).hexdigest()
        comp_hash = hashlib.sha256(compiler_config_str.encode("utf-8")).hexdigest()
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT * FROM validation_cache
                    WHERE python_hash = ? AND rust_hash = ? AND compiler_hash = ?
                """, (py_hash, rust_hash, comp_hash))
                row = cursor.fetchone()
                if row:
                    return dict(row)
        except Exception:
            pass
        return None

    def get_validations(self) -> list[dict]:
        records = []
        if not os.path.exists(self.db_path):
            return []
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("SELECT * FROM validation_cache ORDER BY timestamp DESC")
                for row in cursor.fetchall():
                    records.append(dict(row))
        except Exception:
            pass
        return records
