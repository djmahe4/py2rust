import importlib
import inspect
import sys
from typing import Dict, Optional, Type
from ..utils.errors import SemanticError
from ..utils.visitor import NodeTransformer

class BasePlugin:
    """Base class for all py2rust plugins."""
    @property
    def module_name(self) -> str:
        raise NotImplementedError

    def register(self, st) -> None:
        """Register symbols in the SymbolTable."""
        pass

    def transform_ast(self, node, checker):
        """Perform AST transformations if needed."""
        return node

class PluginManager(NodeTransformer):
    def __init__(self, st):
        self.st = st
        self.plugins: Dict[str, BasePlugin] = {}
        # Auto-load core plugins
        self.load_plugin("enum")
        self.load_plugin("typing")
        self.load_plugin("json")
        self.load_plugin("csv")
        self.load_plugin("collections")
        self.load_plugin("heapq")

    def load_plugin(self, module_name: str) -> Optional[BasePlugin]:
        if module_name in self.plugins:
            return self.plugins[module_name]

        mapping = {"unittest.mock": "mock"}
        plugin_name = mapping.get(module_name, module_name)

        try:
            plugin_module = importlib.import_module(f".{plugin_name}_plugin", package=__package__)
            for name, obj in inspect.getmembers(plugin_module):
                if inspect.isclass(obj) and issubclass(obj, BasePlugin) and obj is not BasePlugin:
                    plugin = obj()
                    if plugin.module_name == module_name or mapping.get(module_name) == plugin_name:
                        self.plugins[module_name] = plugin
                        plugin.register(self.st)
                        return plugin
        except ImportError:
            if module_name not in ("enum", "typing") and getattr(self.st.config, "mock_mode", False):
                try:
                    plugin_module = importlib.import_module(".python_wrapper_plugin", package=__package__)
                    for name, obj in inspect.getmembers(plugin_module):
                        if inspect.isclass(obj) and issubclass(obj, BasePlugin) and obj is not BasePlugin:
                            plugin = obj()
                            self.plugins[module_name] = plugin
                            plugin._target_module = module_name
                            plugin.register(self.st)
                            return plugin
                except ImportError:
                    pass
        return None

    def add_plugin(self, plugin: BasePlugin) -> None:
        """Manually add a plugin instance."""
        self.plugins[plugin.module_name] = plugin
        plugin.register(self.st)

    def visit(self, node):
        """Run all plugins on the current node, then recurse."""
        context = getattr(self, "_current_context", None)
        
        # Plugins transform FIRST (top-down)
        for name, plugin in self.plugins.items():
            node = plugin.transform_ast(node, context)
        
        # Now recurse into fields
        return super().visit(node)

    def transform_ast(self, node, context):
        """Main entry point for transformation."""
        self._current_context = context
        try:
            return self.visit(node)
        finally:
            self._current_context = None

    def transform_module(self, module, context):
        from ..frontend.ast_nodes import EnumDef, FunctionDef
        import dataclasses

        new_classes = []
        new_enums = list(module.enums)
        for cls in module.classes:
            transformed = self.transform_ast(cls, context)
            if isinstance(transformed, EnumDef):
                new_enums.append(transformed)
            else:
                new_classes.append(transformed)

        new_functions = []
        for func in module.functions:
            new_functions.append(self.transform_ast(func, context))

        new_stmts = []
        for stmt in module.statements:
            new_stmts.append(self.transform_ast(stmt, context))

        return dataclasses.replace(
            module, 
            classes=tuple(new_classes), 
            enums=tuple(new_enums),
            functions=tuple(new_functions),
            statements=tuple(new_stmts)
        )
