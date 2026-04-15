from __future__ import annotations
from typing import Optional
from ..utils.errors import SemanticError


class Scope:
    def __init__(self, name: str, parent: Optional["Scope"] = None):
        self.name = name
        self.parent = parent
        self._symbols: dict = {}

    def define(self, name: str, type_) -> None:
        self._symbols[name] = type_

    def lookup_local(self, name: str):
        return self._symbols.get(name)

    def lookup(self, name: str):
        if name in self._symbols:
            return self._symbols[name]
        if self.parent:
            return self.parent.lookup(name)
        return None


class ClassInfo:
    def __init__(self, name, bases, fields, methods, constructors, type_params=()):
        self.name = name
        self.bases = bases
        self.fields = fields  # dict: field_name -> type
        # methods dict: method_name -> {arity -> (FunctionDef, defining_class)}
        self.methods = {}
        for m_name, arities in methods.items():
            self.methods[m_name] = {}
            for arity, m_def in arities.items():
                if isinstance(m_def, tuple):
                    self.methods[m_name][arity] = m_def
                else:
                    self.methods[m_name][arity] = (m_def, name)
        self.constructors = constructors
        self.type_params = type_params
class EnumInfo:
    def __init__(self, name, variants):
        self.name = name
        self.variants = variants  # dict: variant_name -> value_expr


class TraitInfo:
    def __init__(self, name, bases, methods):
        self.name = name
        self.bases = bases
        # methods dict: method_name -> {arity -> (TypedSignature)}
        self.methods = methods


class SymbolTable:
    def __init__(self, config=None):
        from ..config import CompilerConfig
        self.config = config or CompilerConfig()
        self._global = Scope("global")
        self._current = self._global
        self._stack: list[Scope] = [self._global]
        self._functions: dict = {}
        self._classes: dict = {}  # name -> ClassInfo
        self._enums: dict = {}  # name -> EnumInfo
        self._traits: dict = {}  # name -> TraitInfo
        self._current_class: Optional[str] = None
        
        # Plugin Manager
        from ..plugins import PluginManager
        self.pm = PluginManager(self)
        
        self._register_std_traits()

    def _register_std_traits(self):
        # Arithmetic
        self.define_trait("Add", [], {"add": {1: (None, None)}})
        self.define_trait("Sub", [], {"sub": {1: (None, None)}})
        self.define_trait("Mul", [], {"mul": {1: (None, None)}})
        self.define_trait("Div", [], {"div": {1: (None, None)}})
        # Comparison
        self.define_trait("PartialEq", [], {"eq": {1: (None, None)}})
        self.define_trait("PartialOrd", [], {"lt": {1: (None, None)}})
        # Container
        self.define_trait("Index", [], {"index": {1: (None, None)}})
        self.define_trait("IndexMut", [], {"index_mut": {1: (None, None)}})
        # Built-in
        self.define_trait("Hash", [], {"hash": {1: (None, None)}})
        self.define_trait("Display", [], {"fmt": {1: (None, None)}})
        self.define_trait("Debug", [], {"fmt": {1: (None, None)}})
        self.define_trait("Clone", [], {"clone": {0: (None, None)}})

    @property
    def current_scope(self) -> Scope:
        return self._current

    def enter_scope(self, name: str) -> None:
        new_scope = Scope(name, parent=self._current)
        self._stack.append(new_scope)
        self._current = new_scope

    def exit_scope(self) -> None:
        if len(self._stack) <= 1:
            raise RuntimeError("Cannot exit global scope")
        self._stack.pop()
        self._current = self._stack[-1]

    def define(self, name: str, type_) -> None:
        self._current.define(name, type_)

    def define_function(self, name: str, param_types: list, return_type, is_async: bool = False, type_params: tuple = ()) -> None:
        self._functions[name] = (param_types, return_type, is_async, type_params)

    def lookup(self, name: str):
        return self._current.lookup(name)

    def lookup_function(self, name: str):
        return self._functions.get(name)

    def is_global_scope(self) -> bool:
        return self._current is self._global

    def define_class(self, name, bases, fields, methods, constructors, type_params=()) -> None:
        self._classes[name] = ClassInfo(name, bases, fields, methods, constructors, type_params)

    def lookup_class(self, name: str):
        return self._classes.get(name)

    def define_enum(self, name: str, variants: dict) -> None:
        self._enums[name] = EnumInfo(name, variants)

    def lookup_enum(self, name: str) -> Optional[EnumInfo]:
        return self._enums.get(name)

    def define_trait(self, name: str, bases: list, methods: dict) -> None:
        self._traits[name] = TraitInfo(name, bases, methods)

    def lookup_trait(self, name: str) -> Optional[TraitInfo]:
        return self._traits.get(name)

    def register_external_name(self, name: str, type_: ExternalPythonType) -> None:
        """Register a name that is satisfied by an external Python module."""
        self._global.define(name, type_)

    def get_field_type(self, class_name: str, field: str):
        cls = self._classes.get(class_name)
        if cls and field in cls.fields:
            return cls.fields[field]
        if cls:
            for base_name in cls.bases:
                field_type = self.get_field_type(base_name, field)
                if field_type:
                    return field_type
        return None

    def lookup_method(self, target_name: str, method: str, arity: int):
        # Check classes
        cls = self._classes.get(target_name)
        if cls and method in cls.methods:
            arities = cls.methods[method]
            if arity in arities:
                return arities[arity]
        
        if cls:
            for base_name in cls.bases:
                result = self.lookup_method(base_name, method, arity)
                if result:
                    return result
        
        # Check traits
        trait = self._traits.get(target_name)
        if trait and method in trait.methods:
            arities = trait.methods[method]
            if arity in arities:
                return arities[arity]

        return None

    def lookup_constructor(self, class_name: str, arity: int):
        cls = self._classes.get(class_name)
        if cls and arity in cls.constructors:
            return cls.constructors[arity]
        if cls:
            for base_name in cls.bases:
                ctor = self.lookup_constructor(base_name, arity)
                if ctor:
                    return ctor
        return None

    def get_current_class(self) -> Optional[str]:
        return self._current_class

    def set_current_class(self, name: Optional[str]) -> None:
        self._current_class = name
