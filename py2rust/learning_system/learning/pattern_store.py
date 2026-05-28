import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

class PatternStore:
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = os.path.join(os.getcwd(), ".py2rust", "patterns.db")
        
        # Detect jsonl path for migration
        jsonl_path = None
        if db_path.endswith(".jsonl"):
            jsonl_path = db_path
            db_path = db_path[:-6] + ".db"
        else:
            potential_jsonl = db_path.replace(".db", ".jsonl")
            if os.path.exists(potential_jsonl):
                jsonl_path = potential_jsonl
        
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        self._init_db()
        
        if jsonl_path and os.path.exists(jsonl_path):
            self._migrate_jsonl(jsonl_path)

    # ------------------------------------------------------------------
    # Context manager support: ensures connection is closed before
    # TemporaryDirectory (or any other cleanup) tries to delete the file.
    # On Windows, SQLite holds a file lock until the connection is closed.
    # ------------------------------------------------------------------
    def close(self):
        """No-op – connections are short-lived per operation; provided for
        symmetry so callers can do ``store.close()`` before cleanup."""
        pass  # all connections are closed in _use_conn()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    @contextmanager
    def _use_conn(self):
        """Open a connection, yield it, then **always** close it.

        Unlike ``with sqlite3.connect(...) as conn:``, which only commits/
        rolls back on exit, this context manager guarantees the OS-level
        file handle is released — critical on Windows where an open handle
        blocks directory deletion.
        """
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        with self._use_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS patterns (
                    pattern_id TEXT PRIMARY KEY,
                    timestamp TEXT,
                    trigger_pattern TEXT,
                    target_rust TEXT,
                    replacement_rust TEXT,
                    evidence_count INTEGER DEFAULT 1,
                    confidence REAL DEFAULT 0.0
                )
            """)

    def _migrate_jsonl(self, jsonl_path: str):
        # Read from jsonl
        records = []
        try:
            # Check if it is a binary/sqlite file or a text jsonl file first
            with open(jsonl_path, "rb") as f:
                header = f.read(15)
                if header.startswith(b"SQLite format 3"):
                    return  # already an SQLite file, skip migration
            
            with open(jsonl_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                          try:
                              records.append(json.loads(line))
                          except Exception:
                              pass
        except Exception:
            return

        # Write to sqlite
        if records:
            with self._use_conn() as conn:
                for record in records:
                    conn.execute("""
                        INSERT OR REPLACE INTO patterns 
                        (pattern_id, timestamp, trigger_pattern, target_rust, replacement_rust, evidence_count, confidence)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        record.get("pattern_id"),
                        record.get("timestamp"),
                        record.get("trigger_pattern"),
                        record.get("target_rust"),
                        record.get("replacement_rust"),
                        record.get("evidence_count", 1),
                        record.get("confidence", 0.0)
                    ))
        
        # Delete or clean up jsonl file after successful migration
        try:
            os.remove(jsonl_path)
        except Exception:
            pass

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
        with self._use_conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO patterns 
                (pattern_id, timestamp, trigger_pattern, target_rust, replacement_rust, evidence_count, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                record["pattern_id"],
                record["timestamp"],
                record["trigger_pattern"],
                record["target_rust"],
                record["replacement_rust"],
                record["evidence_count"],
                record["confidence"]
            ))

    def get_patterns(self) -> list[dict]:
        with self._use_conn() as conn:
            cursor = conn.execute("SELECT * FROM patterns")
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
