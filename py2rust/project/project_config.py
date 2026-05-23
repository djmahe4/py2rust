from __future__ import annotations
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class ProjectConfig:
    name: str = "compiled_project"
    version: str = "0.1.0"
    dependencies: dict[str, str] = field(default_factory=dict)
    entry_point: str | None = None
    package_dir: str | None = None
    exclude: list[str] = field(default_factory=list)
    sys_path: list[str] = field(default_factory=list)

    @classmethod
    def load_from_toml(cls, toml_path: Path) -> ProjectConfig:
        if not toml_path.exists():
            return cls()
        
        try:
            with toml_path.open("rb") as f:
                data = tomllib.load(f)
        except Exception:
            return cls()

        name = "compiled_project"
        version = "0.1.0"
        dependencies = {}
        entry_point = None
        package_dir = None
        exclude = []
        sys_path = []

        # Parse standard [project] table
        if "project" in data:
            proj = data["project"]
            if isinstance(proj, dict):
                name = proj.get("name", name)
                version = proj.get("version", version)
                if "dependencies" in proj and isinstance(proj["dependencies"], list):
                    # We might want to list them
                    pass

        # Parse custom [tool.py2rust] settings if any
        if "tool" in data and "py2rust" in data["tool"]:
            tool_cfg = data["tool"]["py2rust"]
            if isinstance(tool_cfg, dict):
                name = tool_cfg.get("name", name)
                version = tool_cfg.get("version", version)
                entry_point = tool_cfg.get("entry_point", entry_point)
                package_dir = tool_cfg.get("package_dir", package_dir)
                if "dependencies" in tool_cfg and isinstance(tool_cfg["dependencies"], dict):
                    dependencies.update(tool_cfg["dependencies"])
                if "exclude" in tool_cfg and isinstance(tool_cfg["exclude"], list):
                    exclude = [str(x) for x in tool_cfg["exclude"]]
                if "sys_path" in tool_cfg and isinstance(tool_cfg["sys_path"], list):
                    sys_path = [str(x) for x in tool_cfg["sys_path"]]

        return cls(
            name=name,
            version=version,
            dependencies=dependencies,
            entry_point=entry_point,
            package_dir=package_dir,
            exclude=exclude,
            sys_path=sys_path
        )
