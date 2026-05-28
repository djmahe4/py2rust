from __future__ import annotations
from typing import Optional
from ..frontend.ast_nodes import (
    IntType,
    FloatType,
    BoolType,
    StrType,
    ListType,
    DictType,
    ClassType,
    TupleType,
    EnumType,
    OptionalType,
    UnionType,
    SliceType,
    UnitType,
    IteratorType,
    IterableType,
    GeneratorType,
    SetType,
    UnknownType,
    ExternalPythonType,
    TypeVarType,
)

_MUTEX_CLASS_NAMES = frozenset({
    "Mutex", "Lock", "RwLock", "Semaphore", "Condition",
    "threading.Lock", "threading.RLock", "threading.Semaphore"
})

def _is_mutex_like_name(name: str) -> bool:
    """Return True if the class name is a known mutex/lock synchronisation primitive."""
    return name in _MUTEX_CLASS_NAMES or any(
        name.endswith(suffix) for suffix in ("Lock", "Mutex", "RwLock", "Semaphore", "Guard")
    )

def _is_mutex_primitive(name: str) -> bool:
    """Check if the name represents a mutex-like primitive."""
    return _is_mutex_like_name(name)

def _is_sync_primitive(name: str) -> bool:
    """Check if the name represents any synchronization primitive."""
    if _is_mutex_like_name(name):
        return True
    return name in {"Event", "threading.Event", "Barrier", "threading.Barrier"}

def _types_compatible(a, b, invariant=False) -> bool:
    if isinstance(a, UnknownType) or isinstance(b, UnknownType):
        return True
    if isinstance(a, TypeVarType) or isinstance(b, TypeVarType):
        return True

    # Handle Optional/Union type checks
    if isinstance(a, UnionType):
        return any(_types_compatible(v, b, invariant=invariant) for v in a.variants)
    if isinstance(b, UnionType):
        return any(_types_compatible(a, v, invariant=invariant) for v in b.variants)

    if isinstance(a, OptionalType):
        if isinstance(b, OptionalType):
            return _types_compatible(a.inner_type, b.inner_type, invariant=invariant)
        if isinstance(b, UnitType):  # None matches Optional[T]
            return True
        return _types_compatible(a.inner_type, b, invariant=invariant)
    if isinstance(b, OptionalType):
        if isinstance(a, UnitType):  # None matches Optional[T]
            return True
        return _types_compatible(a, b.inner_type, invariant=invariant)

    if type(a) is type(b):
        if isinstance(a, ListType) and isinstance(b, ListType):
            return _types_compatible(a.element_type, b.element_type, invariant=True)
        if isinstance(a, DictType) and isinstance(b, DictType):
            return _types_compatible(
                a.key_type, b.key_type, invariant=True
            ) and _types_compatible(a.value_type, b.value_type, invariant=True)
        if isinstance(a, SetType) and isinstance(b, SetType):
            return _types_compatible(a.element_type, b.element_type, invariant=True)
        if isinstance(a, IteratorType) and isinstance(b, IteratorType):
            return _types_compatible(a.element_type, b.element_type, invariant=True)
        if isinstance(a, IterableType) and isinstance(b, IterableType):
            return _types_compatible(a.element_type, b.element_type, invariant=True)
        if isinstance(a, GeneratorType) and isinstance(b, GeneratorType):
            return (_types_compatible(a.yield_type, b.yield_type, invariant=True) and
                    _types_compatible(a.send_type, b.send_type, invariant=True) and
                    _types_compatible(a.return_type, b.return_type, invariant=True))
        return True

    # GeneratorType compatibility
    if isinstance(a, IteratorType) and isinstance(b, GeneratorType):
        return _types_compatible(a.element_type, b.yield_type, invariant=True)
    if isinstance(a, IterableType) and isinstance(b, GeneratorType):
        return _types_compatible(a.element_type, b.yield_type, invariant=True)
    if isinstance(a, GeneratorType) and isinstance(b, IteratorType):
        return _types_compatible(a.yield_type, b.element_type, invariant=True)
    if isinstance(a, GeneratorType) and isinstance(b, IterableType):
        return _types_compatible(a.yield_type, b.element_type, invariant=True)
    if isinstance(a, IterableType) and isinstance(b, IteratorType):
        return _types_compatible(a.element_type, b.element_type, invariant=True)

    if isinstance(a, FloatType) and isinstance(b, IntType):
        return not invariant
    if isinstance(a, ExternalPythonType) or isinstance(b, ExternalPythonType):
        return True
    if isinstance(a, (EnumType, ClassType)) and isinstance(b, (EnumType, ClassType)):
        return getattr(a, "name", None) == getattr(b, "name", None)
    return False

def _get_yield_item_type(expected_type):
    if isinstance(expected_type, IteratorType):
        return expected_type.element_type
    if isinstance(expected_type, IterableType):
        return expected_type.element_type
    if isinstance(expected_type, GeneratorType):
        return expected_type.yield_type
    return None

def _get_iterable_item_type(it_type):
    if isinstance(it_type, ListType):
        return it_type.element_type
    if isinstance(it_type, IteratorType):
        return it_type.element_type
    if isinstance(it_type, IterableType):
        return it_type.element_type
    if isinstance(it_type, GeneratorType):
        return it_type.yield_type
    if isinstance(it_type, StrType):
        return StrType()
    if isinstance(it_type, DictType):
        return it_type.key_type
    return None
