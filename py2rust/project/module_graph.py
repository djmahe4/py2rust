from __future__ import annotations
from pathlib import Path
from typing import Dict, Set, List
from py2rust.frontend.parser import parse
from py2rust.project.import_resolver import ImportResolver
from py2rust.frontend.ast_nodes import Import, ImportFrom

class ModuleGraph:
    def __init__(self, resolver: ImportResolver) -> None:
        self.resolver = resolver
        # Map module_name -> file_path
        self.modules: Dict[str, Path] = {}
        # Map module_name -> set of imported module names
        self.dependencies: Dict[str, Set[str]] = {}
        # Map module_name -> parsed AST Module node
        self.parsed_modules: Dict[str, object] = {}

    def add_module(self, name: str, file_path: Path) -> None:
        self.modules[name] = file_path.resolve()
        if name not in self.dependencies:
            self.dependencies[name] = set()

    def build_graph(self) -> None:
        """
        Parses all registered modules to extract their imports and build the dependency graph.
        """
        for mod_name, file_path in self.modules.items():
            try:
                source = file_path.read_text(encoding="utf-8")
                ast_module = parse(source, filename=str(file_path))
                self.parsed_modules[mod_name] = ast_module
                
                # Extract imports
                for imp in ast_module.imports:
                    if isinstance(imp, Import):
                        for alias in imp.names:
                            resolved = alias.name
                            if self.resolver.is_intra_repo(resolved):
                                for local_name in self.resolver.local_modules:
                                    if resolved == local_name or local_name.startswith(resolved + "."):
                                        self.dependencies[mod_name].add(local_name)
                    elif isinstance(imp, ImportFrom):
                        if imp.module or imp.level > 0:
                            if imp.level > 0:
                                try:
                                    base_mod_name = self.resolver.resolve_relative_import(mod_name, imp.level, imp.module)
                                except ValueError:
                                    continue
                            else:
                                base_mod_name = imp.module

                            for alias in imp.names:
                                if base_mod_name:
                                    full_target = f"{base_mod_name}.{alias.name}"
                                else:
                                    full_target = alias.name

                                # Find exact local module matching
                                if full_target in self.resolver.local_modules:
                                    self.dependencies[mod_name].add(full_target)
                                elif base_mod_name in self.resolver.local_modules:
                                    self.dependencies[mod_name].add(base_mod_name)
                                elif base_mod_name:
                                    if self.resolver.is_intra_repo(base_mod_name):
                                        self.dependencies[mod_name].add(base_mod_name)
            except Exception:
                # If parsing fails or file doesn't exist, we skip
                pass

    def topological_sort(self) -> List[str]:
        """
        Sorts the modules topologically using Kahn's algorithm.
        If a cycle of length <= 2 is detected, raises ValueError.
        If a cycle of length > 2 is detected, logs/warns and breaks it, continuing topological sort.
        """
        while True:
            # First, construct in-degree map and adj list of active nodes
            adj: Dict[str, Set[str]] = {node: set() for node in self.modules}
            in_degree: Dict[str, int] = {node: 0 for node in self.modules}

            # For topological sort, if 'u' imports 'v', then 'v' must come BEFORE 'u'.
            # So we have a directed edge v -> u.
            # in_degree[u] increases.
            for u, neighbors in self.dependencies.items():
                for v in neighbors:
                    if v in self.modules and v != u:
                        if u not in adj[v]:
                            adj[v].add(u)
                            in_degree[u] += 1

            # Kahn's algorithm
            # Find all nodes with in_degree 0
            queue = [node for node in self.modules if in_degree[node] == 0]
            # Sort queue for determinism
            queue.sort()

            order = []
            while queue:
                queue.sort()
                u = queue.pop(0)
                order.append(u)

                for v in sorted(adj[u]):
                    in_degree[v] -= 1
                    if in_degree[v] == 0:
                        queue.append(v)

            if len(order) == len(self.modules):
                return order

            # There is a cycle!
            remaining_nodes = [node for node in self.modules if node not in order]
            
            # DFS to find a cycle among remaining nodes
            visited: Dict[str, int] = {} # 0=unvisited, 1=visiting, 2=visited
            cycle_path: List[str] = []

            def dfs(node: str) -> List[str] | None:
                visited[node] = 1
                cycle_path.append(node)
                for dep in sorted(self.dependencies.get(node, set())):
                    if dep in remaining_nodes:
                        if visited.get(dep, 0) == 1:
                            cycle_path.append(dep)
                            start_idx = cycle_path.index(dep)
                            return cycle_path[start_idx:]
                        elif visited.get(dep, 0) == 0:
                            res = dfs(dep)
                            if res:
                                return res
                cycle_path.pop()
                visited[node] = 2
                return None

            cycle = None
            for node in sorted(remaining_nodes):
                if visited.get(node, 0) == 0:
                    cycle = dfs(node)
                    if cycle:
                        break

            if cycle:
                unique_cycle = list(dict.fromkeys(cycle[:-1]))
                if len(unique_cycle) <= 2:
                    cycle_str = " -> ".join(cycle)
                    raise ValueError(f"Circular dependency detected: {cycle_str}")
                else:
                    # Cycle of length > 2 is broken!
                    # Break it by removing the edge between the first two elements of the cycle
                    u_mod = unique_cycle[0]
                    v_mod = unique_cycle[1]
                    if v_mod in self.dependencies[u_mod]:
                        self.dependencies[u_mod].remove(v_mod)
                    # Loop continues iteratively
                    continue

            raise ValueError("Module graph contains cycles that could not be resolved.")
