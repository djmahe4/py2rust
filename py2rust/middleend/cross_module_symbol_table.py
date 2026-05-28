from __future__ import annotations
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .symbol_table import SymbolTable, ClassInfo, EnumInfo, TraitInfo

class CrossModuleSymbolTable:
    def __init__(self):
        # Maps module name (e.g. "package.math_utils") to its SymbolTable
        self.modules: dict[str, SymbolTable] = {}

    def register_module(self, module_name: str, symbol_table: SymbolTable) -> None:
        self.modules[module_name] = symbol_table

    def has_module(self, module_name: str) -> bool:
        return module_name in self.modules

    def get_module(self, module_name: str) -> Optional[SymbolTable]:
        return self.modules.get(module_name)

    def lookup_symbol(
        self, module_name: str, symbol_name: str, category: Optional[str] = None
    ) -> any:
        """
        Looks up a symbol inside the specified module.
        If category is provided, searches only that category:
          'functions', 'classes', 'enums', 'traits', 'globals'
        Otherwise searches all of them in order.
        """
        st = self.modules.get(module_name)
        if not st:
            return None

        if category == "functions":
            return st._functions.get(symbol_name)
        elif category == "classes":
            return st._classes.get(symbol_name)
        elif category == "enums":
            return st._enums.get(symbol_name)
        elif category == "traits":
            return st._traits.get(symbol_name)
        elif category == "globals":
            return st._global.lookup_local(symbol_name)

        # Search in all categories in priority order
        if symbol_name in st._functions:
            return st._functions[symbol_name]
        if symbol_name in st._classes:
            return st._classes[symbol_name]
        if symbol_name in st._enums:
            return st._enums[symbol_name]
        if symbol_name in st._traits:
            return st._traits[symbol_name]
        
        return st._global.lookup_local(symbol_name)
