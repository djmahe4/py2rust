from typing import Dict, Set, List

class DependencyManager:
    """
    Manages Rust dependencies (crates) required by the generated code,
    as well as intra-repository module imports and cycle detection.
    """
    def __init__(self):
        # Map crate name to version/feature info
        # e.g., {"serde": {"version": "1.0", "features": ["derive"]}}
        self.dependencies: Dict[str, Dict] = {}
        
        # Modules already processed to avoid redundant plugin firing
        self.processed_modules: Set[str] = set()

        # Adjacency list mapping module_name -> set of imported module names
        self.adjacency_list: Dict[str, Set[str]] = {}

        # Map module_name -> set of Rust use statements (e.g. {"use crate::foo::bar;"})
        self.module_imports: Dict[str, Set[str]] = {}

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

    # Wave 24 Additions: Intra-repo import tracking and circular dependency check

    def add_import_edge(self, from_module: str, to_module: str) -> None:
        """Adds an import edge (directed) from from_module to to_module."""
        if from_module == to_module:
            return # self-imports are handled gracefully or ignored

        if from_module not in self.adjacency_list:
            self.adjacency_list[from_module] = set()
        self.adjacency_list[from_module].add(to_module)

        # Check for circular dependency
        cycle = self.check_circular_dependencies()
        if cycle and len(set(cycle)) <= 2:
            cycle_str = " -> ".join(cycle)
            raise ValueError(f"Circular dependency detected: {cycle_str}")

    def check_circular_dependencies(self) -> List[str] | None:
        """
        Detects circular dependencies in the module graph using DFS.
        Returns the path of the cycle if detected, otherwise None.
        """
        visited: Dict[str, bool] = {} # True if visited and fully processed, False if currently visiting
        cycle_path: List[str] = []

        def dfs(node: str) -> List[str] | None:
            visited[node] = False # Visiting
            cycle_path.append(node)

            for neighbor in self.adjacency_list.get(node, set()):
                if visited.get(neighbor) is False:
                    # Found back-edge (circular dependency!)
                    cycle_path.append(neighbor)
                    start_idx = cycle_path.index(neighbor)
                    return cycle_path[start_idx:]
                elif neighbor not in visited:
                    res = dfs(neighbor)
                    if res:
                        return res

            cycle_path.pop()
            visited[node] = True
            return None

        for start_node in list(self.adjacency_list.keys()):
            if start_node not in visited:
                res = dfs(start_node)
                if res:
                    return res
        return None

    def add_module_import(self, module_name: str, use_statement: str) -> None:
        """Registers a Rust use statement for a module."""
        if module_name not in self.module_imports:
            self.module_imports[module_name] = set()
        self.module_imports[module_name].add(use_statement)

    def get_module_imports(self, module_name: str) -> List[str]:
        """Returns sorted, unique Rust use statements for a module."""
        return sorted(list(self.module_imports.get(module_name, set())))
