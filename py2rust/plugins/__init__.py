import importlib
import inspect
from typing import Dict, Optional, Type
from ..utils.errors import SemanticError

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

class PluginManager:
    def __init__(self, st):
        self.st = st
        self.plugins: Dict[str, BasePlugin] = {}
        # Auto-load core plugins
        self.load_plugin("enum")
        self.load_plugin("typing")

    def load_plugin(self, module_name: str) -> Optional[BasePlugin]:
        if module_name in self.plugins:
            return self.plugins[module_name]

        # Map complex module names to simple plugin names
        mapping = {
            "unittest.mock": "mock",
        }
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
            # Fallback for dynamic wrapping of unknown modules
            if module_name not in ("enum", "typing") and getattr(self.st.config, "mock_mode", False):
                try:
                    plugin_module = importlib.import_module(".python_wrapper_plugin", package=__package__)
                    for name, obj in inspect.getmembers(plugin_module):
                        if inspect.isclass(obj) and issubclass(obj, BasePlugin) and obj is not BasePlugin:
                            plugin = obj()
                            self.plugins[module_name] = plugin
                            # Note: The wrapper plugin needs the actual module name it's wrapping
                            plugin._target_module = module_name
                            plugin.register(self.st)
                            return plugin
                except ImportError:
                    pass
        return None

    def transform_ast(self, node, context):
        for plugin in self.plugins.values():
            node = plugin.transform_ast(node, context)
        return node

    def transform_module(self, module, context):
        """Transform a Module by running all plugins over its classes/functions."""
        from ..frontend.ast_nodes import EnumDef
        import dataclasses

        new_classes = []
        new_enums = list(module.enums)
        for cls in module.classes:
            transformed = self.transform_ast(cls, context)
            if isinstance(transformed, EnumDef):
                new_enums.append(transformed)
            else:
                new_classes.append(transformed)

        return dataclasses.replace(
            module, classes=tuple(new_classes), enums=tuple(new_enums)
        )
