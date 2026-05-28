from __future__ import annotations
import json
import hashlib
from pathlib import Path
from typing import Optional, Dict

class BuildCache:
    def __init__(self, cache_file: Path):
        self.cache_file = Path(cache_file)
        self.data: Dict[str, dict] = {}
        self.load()

    def load(self) -> None:
        if self.cache_file.exists():
            try:
                content = self.cache_file.read_text(encoding="utf-8")
                self.data = json.loads(content) if content.strip() else {}
            except Exception:
                self.data = {}
        else:
            self.data = {}

    def save(self) -> None:
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            self.cache_file.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
        except Exception:
            pass

    @staticmethod
    def get_file_hash(path: Path) -> str:
        path = Path(path)
        if not path.exists():
            return ""
        try:
            content = path.read_text(encoding="utf-8")
            return hashlib.sha256(content.encode("utf-8")).hexdigest()
        except Exception:
            return ""

    def get_entry(self, module_name: str) -> Optional[dict]:
        return self.data.get(module_name)

    def set_entry(
        self,
        module_name: str,
        file_path: Path,
        content_hash: str,
        dependency_hashes: Dict[str, str],
        rust_code: str,
    ) -> None:
        self.data[module_name] = {
            "file_path": str(file_path),
            "content_hash": content_hash,
            "dependency_hashes": dependency_hashes,
            "rust_code": rust_code,
        }
        self.save()

    def clear(self) -> None:
        self.data = {}
        if self.cache_file.exists():
            try:
                self.cache_file.unlink()
            except Exception:
                pass
