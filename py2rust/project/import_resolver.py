from __future__ import annotations
from pathlib import Path
from py2rust.project.package_scanner import PackageScanner

class ImportResolver:
    def __init__(
        self,
        repo_root: Path,
        sys_path: list[Path] | None = None,
        exclude_patterns: list[str] | None = None,
        package_dir: str | None = None,
    ) -> None:
        self.repo_root = repo_root.resolve()
        self.sys_path = [Path(p).resolve() for p in (sys_path or [])]
        self.exclude_patterns = exclude_patterns or []
        self.package_dir = package_dir

        # Scan local repository modules
        scanner = PackageScanner(self.repo_root, self.exclude_patterns)
        self.local_modules = scanner.scan(self.package_dir)

        # Scan modules on the sys.path
        self.sys_modules: dict[str, Path] = {}
        for path in self.sys_path:
            if path.exists() and path.is_dir() and path.resolve() != self.repo_root:
                sys_scanner = PackageScanner(path, self.exclude_patterns)
                # Scan flat layout of sys_path directories
                scanned = sys_scanner.scan()
                for mod_name, mod_path in scanned.items():
                    if mod_name not in self.sys_modules:
                        self.sys_modules[mod_name] = mod_path

        # Combine all modules for resolving (local has priority)
        self.all_modules = {**self.sys_modules, **self.local_modules}

    def is_intra_repo(self, module_name: str) -> bool:
        """
        Returns True if the module_name (or its top-level package prefix)
        belongs to the scanned local repository.
        """
        if module_name in self.local_modules:
            return True
        # Also check prefix, e.g. if my_pkg.utils is in local_modules,
        # then my_pkg is intra-repo.
        parts = module_name.split(".")
        for i in range(1, len(parts) + 1):
            prefix = ".".join(parts[:i])
            if prefix in self.local_modules:
                return True
        return False

    def get_module_for_file(self, file_path: Path) -> str | None:
        """
        Resolves an absolute file path back to its Python module name in the repository.
        """
        target = file_path.resolve()
        for mod_name, mod_path in self.local_modules.items():
            if mod_path.resolve() == target:
                return mod_name
        return None

    def resolve_relative_import(self, current_module: str, level: int, from_module_name: str | None = None) -> str:
        """
        Translates a relative import (level > 0) into an absolute module name.
        PEP 328: level=1 is sibling, level=2 is parent, etc.
        """
        if level <= 0:
            raise ValueError("Level must be greater than 0 for relative imports.")

        parts = current_module.split(".")
        # A module like 'a.b.c' has parts ['a', 'b', 'c'].
        # level=1 ('.') -> parent package of a.b.c is a.b (strip 1 part)
        # level=2 ('..') -> parent package's parent is a (strip 2 parts)
        if level > len(parts):
            raise ValueError(
                f"Relative import level {level} exceeds current module depth of {len(parts)} (module: '{current_module}')"
            )

        parent_parts = parts[:-level]
        if from_module_name:
            parent_parts.extend(from_module_name.split("."))

        return ".".join(parent_parts)

    def resolve_import(self, current_module: str, name: str | None, level: int = 0) -> str | None:
        """
        Resolves either an absolute or a relative import.
        Returns the absolute module name.
        """
        if level > 0:
            try:
                return self.resolve_relative_import(current_module, level, name)
            except ValueError:
                return None
        return name
