from typing import Dict, Set

class DependencyManager:
    """
    Manages Rust dependencies (crates) required by the generated code.
    Allows plugins to register their required crates during the translation process.
    """
    def __init__(self):
        # Map crate name to version/feature info
        # e.g., {"serde": {"version": "1.0", "features": ["derive"]}}
        self.dependencies: Dict[str, Dict] = {}
        
        # Modules already processed to avoid redundant plugin firing
        self.processed_modules: Set[str] = set()

    def add_dependency(self, crate_name: str, version: str = None, features: list = None):
        """Adds or updates a dependency."""
        if crate_name not in self.dependencies:
            self.dependencies[crate_name] = {}
        
        if version:
            self.dependencies[crate_name]["version"] = version
        
        if features:
            existing_features = self.dependencies[crate_name].get("features", [])
            # Use set to avoid duplicates
            current_features = set(existing_features) | set(features)
            self.dependencies[crate_name]["features"] = sorted(list(current_features))

    def get_cargo_dependencies(self) -> str:
        """Generates the [dependencies] section for Cargo.toml."""
        lines = ["[dependencies]"]
        for crate, info in sorted(self.dependencies.items()):
            feature_str = ""
            if "features" in info:
                features = ", ".join(f'"{f}"' for f in info["features"])
                feature_str = f', features = [{features}]'
            
            version = info.get("version", "1.0") # Default to 1.0 if not specified
            lines.append(f'{crate} = {{ version = "{version}"{feature_str} }}')
        
        return "\n".join(lines)

    def mark_processed(self, module_name: str):
        self.processed_modules.add(module_name)

    def is_processed(self, module_name: str) -> bool:
        return module_name in self.processed_modules

    def generate_cargo_toml(self, project_name: str = "py2rust_generated") -> str:
        """Generates a complete Cargo.toml file content."""
        lines = [
            "[package]",
            f'name = "{project_name}"',
            'version = "0.1.0"',
            'edition = "2021"',
            "",
            self.get_cargo_dependencies()
        ]
        return "\n".join(lines)
