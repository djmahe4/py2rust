import importlib
import inspect
from typing import Optional
from . import BasePlugin
from ..frontend.ast_nodes import ExternalPythonType, Import, ImportFrom, Alias

class PythonWrapperPlugin(BasePlugin):
    """
    Plugin that intercepts imports of external Python modules
    and provides dynamic wrappers for runtime execution via pyo3.
    """
    
    def __init__(self):
        super().__init__()
        self._target_module = None

    @property
    def module_name(self) -> str:
        return self._target_module or "python_wrapper"
    
    def register(self, st):
        # When specifically registered for a module, we can analyze it
        if self._target_module:
            try:
                mod = importlib.import_module(self._target_module)
                # Register the module itself
                st.register_external_name(self._target_module, ExternalPythonType(module=self._target_module))
                
                # Optionally register members if small enough, or just leave it to dynamic lookup
                # For now, let's keep it dynamic to avoid huge symbol tables
            except ImportError:
                # If cannot import locally, just register as external anyway (MagicMock style)
                st.register_external_name(self._target_module, ExternalPythonType(module=self._target_module))

    def transform_ast(self, node, checker):
        symbol_table = checker.st
        if isinstance(node, Import):
            for alias in node.names:
                # If name is not found in plugins or local files, wrap it
                if not self._is_local_or_plugin(alias.name):
                    symbol_table.register_external_name(
                        alias.asname or alias.name,
                        ExternalPythonType(module=alias.name)
                    )
            return node
        elif isinstance(node, ImportFrom):
            if not node.module:
                return node
            if not self._is_local_or_plugin(node.module):
                for alias in node.names:
                    symbol_table.register_external_name(
                        alias.asname or alias.name,
                        ExternalPythonType(module=node.module, name=alias.name)
                    )
            return node
        return node

    def _is_local_or_plugin(self, module_name):
        if module_name in ("typing", "enum", "math", "sys", "os", "io"):
            return True
        # TODO: cross-reference with existing source files in IR
        return False
