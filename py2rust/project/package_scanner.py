from __future__ import annotations
from pathlib import Path
from typing import Set

class PackageScanner:
    def __init__(self, repo_root: Path, exclude_patterns: list[str] | None = None) -> None:
        self.repo_root = repo_root.resolve()
        self.exclude_patterns = exclude_patterns or []

    def is_excluded(self, path: Path) -> bool:
        rel_path = path.resolve().relative_to(self.repo_root)
        parts = rel_path.parts
        
        # Check standard ignores
        for part in parts:
            if part.startswith(".") or part in ("__pycache__", "venv", ".venv", "build", "dist", "tests", "test"):
                return True
                
        # Check explicit exclude patterns
        for pattern in self.exclude_patterns:
            if path.match(pattern) or rel_path.match(pattern):
                return True
                
        return False

    def scan(self, package_dir: str | None = None) -> dict[str, Path]:
        """
        Scans for all .py files in the repository.
        Returns a dict mapping module name (e.g. 'foo.bar') to Path object.
        """
        modules: dict[str, Path] = {}
        
        # Determine the base search directories
        search_dirs: list[Path] = []
        
        if package_dir:
            custom_dir = self.repo_root / package_dir
            if custom_dir.exists() and custom_dir.is_dir():
                search_dirs.append(custom_dir)
        else:
            # Look for src/ directory first
            src_dir = self.repo_root / "src"
            if src_dir.exists() and src_dir.is_dir():
                search_dirs.append(src_dir)
            else:
                search_dirs.append(self.repo_root)

        for search_dir in search_dirs:
            for py_path in search_dir.rglob("*.py"):
                if py_path.is_file() and not self.is_excluded(py_path):
                    # Construct module name relative to the package base
                    # If it's a src layout, the package base is the src_dir
                    # Otherwise, package base is search_dir
                    
                    # Let's find the correct base for module naming
                    if (search_dir / "__init__.py").exists() and search_dir != self.repo_root:
                        # If the search directory has an __init__.py, it is a package itself.
                        # We want its name to be part of the module paths, so base is its parent.
                        module_base = search_dir.parent
                    else:
                        module_base = search_dir
                    
                    try:
                        rel_parts = py_path.relative_to(module_base).with_suffix("").parts
                        
                        # Handle '__init__' files
                        if rel_parts and rel_parts[-1] == "__init__":
                            rel_parts = rel_parts[:-1]
                            if not rel_parts:
                                # This is the top-level __init__.py of the module base folder itself, skip or map to empty/main
                                continue
                                
                        if rel_parts:
                            mod_name = ".".join(rel_parts)
                            modules[mod_name] = py_path
                    except ValueError:
                        continue
                        
        return modules
