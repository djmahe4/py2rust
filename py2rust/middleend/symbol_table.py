from __future__ import annotations
from typing import Optional
from ..utils.errors import SemanticError


class Scope:
    def __init__(self, name: str, parent: Optional['Scope'] = None):
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


class SymbolTable:
    def __init__(self):
        self._global = Scope("global")
        self._current = self._global
        self._stack: list[Scope] = [self._global]
        self._functions: dict = {}

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
