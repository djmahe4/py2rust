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
        result = self._symbols.get(name)
        if result is not None:
            return result
        if self.parent:
            return self.parent.lookup(name)
        return None


class ClassInfo:
    def __init__(self, name, base, fields, methods, constructors):
        self.name = name
        self.base = base
        self.fields = fields  # dict: field_name -> type
        self.methods = methods  # dict: method_name -> {arity -> FunctionDef}
        self.constructors = constructors  # {arity -> FunctionDef}


class SymbolTable:
    def __init__(self):
        self._global = Scope("global")
        self._current = self._global
        self._stack: list[Scope] = [self._global]
        self._functions: dict = {}
        self._classes: dict = {}  # name -> ClassInfo
        self._current_class: Optional[str] = None

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

    def define_function(self, name: str, param_types: list, return_type) -> None:
        self._functions[name] = (param_types, return_type)

    def lookup(self, name: str):
        return self._current.lookup(name)

    def lookup_function(self, name: str):
        return self._functions.get(name)

    def is_global_scope(self) -> bool:
        return self._current is self._global

    def define_class(self, name, base, fields, methods, constructors) -> None:
        self._classes[name] = ClassInfo(name, base, fields, methods, constructors)

    def lookup_class(self, name: str):
        return self._classes.get(name)

    def get_field_type(self, class_name: str, field: str):
        cls = self._classes.get(class_name)
        if cls and field in cls.fields:
            return cls.fields[field]
        if cls and cls.base:
            return self.get_field_type(cls.base, field)
        return None

    def lookup_method(self, class_name: str, method: str, arity: int):
        cls = self._classes.get(class_name)
        if cls and method in cls.methods:
            arities = cls.methods[method]
            if arity in arities:
                return arities[arity]
        if cls and cls.base:
            return self.lookup_method(cls.base, method, arity)
        return None

    def lookup_constructor(self, class_name: str, arity: int):
        cls = self._classes.get(class_name)
        if cls and arity in cls.constructors:
            return cls.constructors[arity]
        if cls and cls.base:
            return self.lookup_constructor(cls.base, arity)
        return None

    def get_current_class(self) -> Optional[str]:
        return self._current_class

    def set_current_class(self, name: Optional[str]) -> None:
        self._current_class = name
